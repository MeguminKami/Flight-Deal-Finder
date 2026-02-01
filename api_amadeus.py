"""Amadeus Self-Service Flights client.

Purpose
- Provide an Amadeus-first search provider for the UI.
- Raise `APIError` on actionable auth/request/rate-limit errors so the UI can fall back.

This client focuses on the Amadeus Self-Service Flight Cheapest Date Search API:
https://developers.amadeus.com/self-service/category/flights/api-doc/flight-cheapest-date-search/api-reference

Environment variables (loaded via config.py):
- AMADEUS_CLIENT_ID
- AMADEUS_CLIENT_SECRET

Notes
- This code intentionally avoids making unnecessary calls.
- It caches OAuth tokens and API responses via the app cache layer.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from airports import get_airport_db
from cache import get_cache
from config import load_config
from models import FlightDeal


def _safe_resp_text(text: str, limit: int = 1000) -> str:
    """Return a compact/truncated response text for debugging in raised errors."""

    text = (text or "").strip()
    if len(text) > limit:
        return text[:limit] + "…(truncated)"
    return text


class APIError(RuntimeError):
    """Actionable provider error (safe to show to users)."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, provider: str = "Amadeus"):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


@dataclass
class AmadeusConfig:
    base_url: str = "https://test.api.amadeus.com"  # Default to test API
    timeout: float = 15.0
    max_retries: int = 3
    backoff_factor: float = 0.8
    cache_ttl_seconds: int = 6 * 60 * 60
    verify_ssl: bool = True
    # light pacing to reduce 429s
    min_delay_seconds: float = 0.15

    @staticmethod
    def from_env() -> 'AmadeusConfig':
        """Create config from environment variables."""
        import os
        env = os.getenv('AMADEUS_API_ENV', 'test').lower()
        base_url = "https://api.amadeus.com" if env == 'production' else "https://test.api.amadeus.com"
        return AmadeusConfig(base_url=base_url)


class AmadeusClient:
    """Amadeus API client.

    Public contract used by app.py:
    - search_deals(origin, destinations, start_date, end_date, min_days, max_days, ...)

    Returns:
    - List[FlightDeal]

    Raises:
    - APIError on actionable request/auth/rate-limit errors.
    """

    def __init__(self, config: Optional[AmadeusConfig] = None):
        self.config = config or AmadeusConfig.from_env()
        self.cache = get_cache()
        self.airport_db = get_airport_db()

        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/vnd.amadeus+json",
            "User-Agent": "FlightDealFinder/2.0",
        })

        self._token_lock = threading.Lock()
        self._access_token: Optional[str] = None
        self._token_expires_at: float = 0.0

        self._rate_lock = threading.Lock()
        self._last_request_ts: float = 0.0

    # ------------------------------
    # Public API
    # ------------------------------

    def search_deals(
        self,
        *,
        origin: str,
        destinations: List[str],
        start_date: datetime,
        end_date: datetime,
        min_days: int,
        max_days: int,
        max_results: int = 500,
        progress_callback=None,
        cancel_flag: Optional[dict] = None,
    ) -> List[FlightDeal]:
        print(f"\n[AMADEUS DEBUG] ===== SEARCH DEALS CALLED =====")
        print(f"[AMADEUS DEBUG] Origin: {origin}")
        print(f"[AMADEUS DEBUG] Destinations: {len(destinations)} airports")
        print(f"[AMADEUS DEBUG] Date range: {start_date.date()} to {end_date.date()}")
        print(f"[AMADEUS DEBUG] Duration: {min_days}-{max_days} days")
        print(f"[AMADEUS DEBUG] Using API: {self.config.base_url}")

        # Validate date range for test API
        if "test.api.amadeus.com" in self.config.base_url:
            days_until_departure = (start_date - datetime.now()).days
            if days_until_departure > 365:
                print(f"[AMADEUS DEBUG] WARNING: Test API may not support dates more than 365 days in future")
                print(f"[AMADEUS DEBUG] WARNING: Current search is {days_until_departure} days ahead")
                print(f"[AMADEUS DEBUG] WARNING: Consider using dates within next 12 months for test API")

        origin = self._normalize_iata(origin)
        if not origin:
            print(f"[AMADEUS DEBUG] ERROR: Invalid origin IATA")
            return []

        origin_airport = self.airport_db.get_airport(origin)
        if not origin_airport:
            print(f"[AMADEUS DEBUG] ERROR: Origin airport not found in database")
            return []

        print(f"[AMADEUS DEBUG] Origin airport: {origin_airport.city} ({origin})")

        # Keep it efficient: query by destination and month-sized date ranges (not per-day).
        periods = self._generate_periods(start_date, end_date)
        total = max(1, len(destinations) * len(periods))
        current = 0

        deals: List[FlightDeal] = []

        for dest in destinations:
            if cancel_flag and cancel_flag.get('cancelled'):
                break

            dest = self._normalize_iata(dest)
            if not dest or dest == origin:
                continue

            dest_airport = self.airport_db.get_airport(dest)
            if not dest_airport:
                continue

            for period in periods:
                if cancel_flag and cancel_flag.get('cancelled'):
                    break

                current += 1
                if progress_callback:
                    progress_callback(current, total, f"Amadeus {origin}→{dest} ({period})")

                # Use API-supported params:
                # - departureDate can be a single ISO date OR a comma-separated list/range.
                #   We pass month-clamped ranges like "YYYY-MM-DD,YYYY-MM-DD".
                # - currency (not currencyCode)
                # - duration can be set to min,max
                data = self._get_cheapest_date_search(
                    origin=origin,
                    destination=dest,
                    period=period,
                    currency="EUR",
                    min_days=min_days,
                    max_days=max_days,
                )

                for item in self._extract_flights(data):
                    deal = self._to_flight_deal(item, origin_airport, dest_airport)
                    if not deal:
                        continue

                    # Strict date and duration filtering
                    # APIs may return results outside of requested ranges, so we must manually filter
                    try:
                        depart_dt = datetime.fromisoformat(deal.depart_date[:10])
                        return_dt = datetime.fromisoformat(deal.return_date[:10])
                    except Exception:
                        # Invalid date format, skip this deal
                        continue

                    # Filter 1: Departure date must be within the specified date range
                    if not (start_date <= depart_dt <= end_date):
                        continue

                    # Filter 2: Trip duration must be within min_days and max_days
                    trip_days = (return_dt - depart_dt).days
                    if not (min_days <= trip_days <= max_days):
                        continue

                    # Filter 3: Return date should not be unreasonably far in the future
                    # (though this is implicitly covered by the duration check)
                    if return_dt < depart_dt:
                        continue

                    deals.append(deal)

        deals = self._deduplicate(deals)
        deals.sort(key=lambda d: (d.price_eur, d.transfers if d.transfers is not None else 999, d.depart_date))
        return deals[:max_results]

    # ------------------------------
    # OAuth + HTTP
    # ------------------------------

    def _rate_limit(self) -> None:
        with self._rate_lock:
            now = time.time()
            elapsed = now - self._last_request_ts
            if elapsed < self.config.min_delay_seconds:
                time.sleep(self.config.min_delay_seconds - elapsed)
            self._last_request_ts = time.time()

    def _get_access_token(self) -> str:
        cfg = load_config()
        print(f"[AMADEUS DEBUG] Loading config...")
        print(f"[AMADEUS DEBUG] Has Amadeus credentials: {cfg.has_amadeus}")
        print(f"[AMADEUS DEBUG] Client ID (masked): {cfg.amadeus_client_id[:8]}...{cfg.amadeus_client_id[-4:] if cfg.amadeus_client_id else 'EMPTY'}")

        if not cfg.has_amadeus:
            print(f"[AMADEUS DEBUG] ERROR: Credentials missing!")
            raise APIError("Amadeus credentials missing (AMADEUS_CLIENT_ID/AMADEUS_CLIENT_SECRET)")

        with self._token_lock:
            if self._access_token and time.time() < (self._token_expires_at - 30):
                print(f"[AMADEUS DEBUG] Using cached token (expires in {int(self._token_expires_at - time.time())}s)")
                return self._access_token

            url = f"{self.config.base_url}/v1/security/oauth2/token"
            print(f"[AMADEUS DEBUG] Requesting token from: {url}")
            print(f"[AMADEUS DEBUG] Using Client ID: {cfg.amadeus_client_id[:8]}...")

            data = {
                "grant_type": "client_credentials",
                "client_id": cfg.amadeus_client_id,
                "client_secret": cfg.amadeus_client_secret,
            }

            self._rate_limit()
            try:
                print(f"[AMADEUS DEBUG] Sending POST request...")
                resp = self._session.post(url, data=data, timeout=self.config.timeout, verify=self.config.verify_ssl)
                print(f"[AMADEUS DEBUG] Response status code: {resp.status_code}")
                print(f"[AMADEUS DEBUG] Response headers: {dict(resp.headers)}")
                print(f"[AMADEUS DEBUG] Response body (first 500 chars): {resp.text[:500]}")
            except requests.exceptions.RequestException as e:
                print(f"[AMADEUS DEBUG] ERROR: Request exception: {type(e).__name__}: {e}")
                raise APIError(f"Amadeus token request failed: {e}")

            if resp.status_code != 200:
                print(f"[AMADEUS DEBUG] ERROR: Non-200 status code!")
                raise APIError(
                    f"Amadeus token request failed (HTTP {resp.status_code}): {_safe_resp_text(resp.text)}",
                    status_code=resp.status_code,
                )

            payload = resp.json() if resp.text else {}
            print(f"[AMADEUS DEBUG] Token response payload keys: {payload.keys() if payload else 'empty'}")
            token = payload.get("access_token")
            expires_in = int(payload.get("expires_in") or 0)
            print(f"[AMADEUS DEBUG] Token extracted: {'YES' if token else 'NO'}, expires_in: {expires_in}")

            if not token or expires_in <= 0:
                print(f"[AMADEUS DEBUG] ERROR: Invalid token response!")
                raise APIError("Amadeus token response missing access_token")

            self._access_token = token
            self._token_expires_at = time.time() + expires_in
            print(f"[AMADEUS DEBUG] Token successfully cached! Expires at: {time.ctime(self._token_expires_at)}")
            return self._access_token

    def _request_json(self, method: str, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        print(f"[AMADEUS DEBUG] Making {method} request to {endpoint}")
        print(f"[AMADEUS DEBUG] Params: {params}")
        token = self._get_access_token()
        url = f"{self.config.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {token}"}
        print(f"[AMADEUS DEBUG] Full URL: {url}")
        print(f"[AMADEUS DEBUG] Using bearer token: {token[:20]}...")

        for attempt in range(self.config.max_retries):
            print(f"[AMADEUS DEBUG] Attempt {attempt + 1}/{self.config.max_retries}")
            self._rate_limit()
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    timeout=self.config.timeout,
                    verify=self.config.verify_ssl,
                )
                print(f"[AMADEUS DEBUG] Response status: {resp.status_code}")
                print(f"[AMADEUS DEBUG] Response body (first 500 chars): {resp.text[:500]}")
            except requests.exceptions.RequestException as e:
                # network issue → actionable
                print(f"[AMADEUS DEBUG] ERROR: Request exception: {type(e).__name__}: {e}")
                raise APIError(f"Amadeus request failed: {e}")

            if resp.status_code == 200:
                try:
                    result = resp.json()
                    print(f"[AMADEUS DEBUG] SUCCESS: Got valid JSON response")
                    return result
                except Exception:
                    return {}

            # actionable failures (should trigger fallback)
            if resp.status_code in (400, 401, 403, 429):
                error_msg = self._parse_error_message(resp)
                print(f"[AMADEUS DEBUG] ERROR: Actionable failure - HTTP {resp.status_code}: {error_msg}")
                raise APIError(
                    f"Amadeus rejected the request (HTTP {resp.status_code}): {error_msg}",
                    status_code=resp.status_code,
                )

            # 5xx: retry then eventually raise
            if resp.status_code >= 500:
                error_msg = self._parse_error_message(resp)
                print(f"[AMADEUS DEBUG] WARNING: Server error HTTP {resp.status_code}: {error_msg}")
                if attempt < self.config.max_retries - 1:
                    print(f"[AMADEUS DEBUG] Retrying in {self.config.backoff_factor ** attempt:.2f}s...")
                    time.sleep(self.config.backoff_factor ** attempt)
                    continue
                else:
                    # Last attempt failed - provide detailed error
                    print(f"[AMADEUS DEBUG] All retries exhausted with error: {error_msg}")
                    raise APIError(f"Amadeus server error: {error_msg}", status_code=resp.status_code)

            # other codes treat as empty
            print(f"[AMADEUS DEBUG] WARNING: Unexpected status {resp.status_code}, returning empty dict")
            return {}

        print(f"[AMADEUS DEBUG] ERROR: All retry attempts exhausted!")
        raise APIError("Amadeus is temporarily unavailable. Please try again later.")

    # ------------------------------
    # Amadeus endpoints
    # ------------------------------

    def _get_cheapest_date_search(
        self,
        *,
        origin: str,
        destination: str,
        period: str,
        currency: str,
        min_days: Optional[int] = None,
        max_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        # cache key matches our cache API (endpoint + params)
        endpoint = "/v1/shopping/flight-dates"

        # Extract single date from period for better compatibility with test API
        # Test API often fails with date ranges, so use single date
        start_date_str = period.split(',')[0] if ',' in period else period

        params: Dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "departureDate": start_date_str,  # Use single date for test API compatibility
            "oneWay": "false",
            "currency": currency,
        }

        # Try without duration first for better test API compatibility
        # Duration parameter can cause 500 errors on test API for some routes
        cached = self.cache.get(endpoint, params)
        if cached is not None:
            return cached

        # First attempt: without duration parameter (more compatible)
        data = self._request_json("GET", endpoint, params=params)

        # If we got data, cache and return it
        if data and data.get("data"):
            self.cache.set(endpoint, params, data)
            return data

        # If no data and we have duration constraints, try with duration parameter
        if min_days is not None and max_days is not None:
            params_with_duration = params.copy()
            params_with_duration["duration"] = f"{min_days},{max_days}"

            cached_with_duration = self.cache.get(endpoint, params_with_duration)
            if cached_with_duration is not None:
                return cached_with_duration

            try:
                data_with_duration = self._request_json("GET", endpoint, params=params_with_duration)
                if data_with_duration:
                    self.cache.set(endpoint, params_with_duration, data_with_duration)
                    return data_with_duration
            except APIError:
                # If duration parameter causes error, fall back to data without it
                pass

        # Cache the result (even if empty) to avoid repeated failed requests
        self.cache.set(endpoint, params, data)
        return data

    # ------------------------------
    # Parsing
    # ------------------------------

    def _extract_flights(self, payload: Dict[str, Any]) -> List[Dict[str, Any]]:
        # Response shape: { data: [ { type:'flight-date', origin, destination, departureDate, returnDate, price: { total } , links... } ] }
        data = payload.get("data")
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
        return []

    def _to_flight_deal(self, item: Dict[str, Any], origin_airport, dest_airport) -> Optional[FlightDeal]:
        try:
            depart_date = item.get("departureDate") or ""
            return_date = item.get("returnDate") or ""
            price_obj = item.get("price") or {}
            total = price_obj.get("total")
            if not depart_date or not return_date or total is None:
                return None

            price = float(total)
            if price <= 0:
                return None

            # Amadeus flight-dates doesn't provide number of stops; leave transfers None
            return FlightDeal(
                origin_iata=origin_airport.iata,
                dest_iata=dest_airport.iata,
                origin_city=origin_airport.city,
                dest_city=dest_airport.city,
                origin_flag=origin_airport.flag_emoji,
                dest_flag=dest_airport.flag_emoji,
                depart_date=depart_date,
                return_date=return_date,
                price_eur=price,
                transfers=None,
                airline=None,
                flight_number=None,
                deep_link=None,
                found_at=datetime.utcnow(),
                expires_at=None,
                raw_payload=item,
            )
        except Exception:
            return None

    # ------------------------------
    # Helpers
    # ------------------------------

    def _parse_error_message(self, resp: requests.Response) -> str:
        """Parse Amadeus error response to extract meaningful error message."""
        try:
            error_data = resp.json()
            if isinstance(error_data, dict) and "errors" in error_data:
                errors = error_data["errors"]
                if isinstance(errors, list) and len(errors) > 0:
                    first_error = errors[0]
                    if isinstance(first_error, dict):
                        title = first_error.get("title", "")
                        detail = first_error.get("detail", "")
                        code = first_error.get("code", "")
                        msg_parts = []
                        if code:
                            msg_parts.append(f"Code {code}")
                        if title:
                            msg_parts.append(title)
                        if detail:
                            msg_parts.append(detail)
                        if msg_parts:
                            return " - ".join(msg_parts)
            return _safe_resp_text(resp.text)
        except Exception:
            return _safe_resp_text(resp.text)

    def _normalize_iata(self, code: str) -> str:
        code = (code or "").strip().upper()
        if len(code) == 3 and code.isalpha():
            return code
        # fallback: if user provided something odd, try lookup by db (not expensive)
        a = self.airport_db.get_airport(code)
        return a.iata if a else ""

    def _generate_periods(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Generate 2-week departureDate intervals for Amadeus flight-dates.

        Returns single dates representing the start of each 2-week period.
        This provides good coverage while minimizing API calls for test environment.
        """

        if end_date < start_date:
            return []

        periods: List[str] = []

        # Use 14-day intervals for good coverage with fewer API calls
        cur = start_date

        while cur <= end_date:
            # Store just the start date for this period
            periods.append(f"{cur:%Y-%m-%d}")
            # Move forward by 14 days for next period
            cur = cur + timedelta(days=14)

        return periods

    def _deduplicate(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        seen = set()
        out: List[FlightDeal] = []
        for d in deals:
            key = (d.origin_iata, d.dest_iata, d.depart_date[:10], d.return_date[:10])
            if key in seen:
                continue
            seen.add(key)
            out.append(d)
        return out
