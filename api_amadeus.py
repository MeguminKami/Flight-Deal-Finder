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
    base_url: str = "https://test.api.amadeus.com"
    timeout: float = 15.0
    max_retries: int = 3
    backoff_factor: float = 0.8
    cache_ttl_seconds: int = 6 * 60 * 60
    verify_ssl: bool = True
    # light pacing to reduce 429s
    min_delay_seconds: float = 0.15


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
        self.config = config or AmadeusConfig()
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
        origin = self._normalize_iata(origin)
        if not origin:
            return []

        origin_airport = self.airport_db.get_airport(origin)
        if not origin_airport:
            return []

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

                    # date filtering
                    try:
                        depart_dt = datetime.fromisoformat(deal.depart_date[:10])
                        return_dt = datetime.fromisoformat(deal.return_date[:10])
                    except Exception:
                        continue

                    if not (start_date <= depart_dt <= end_date):
                        continue

                    trip_days = (return_dt - depart_dt).days
                    if not (min_days <= trip_days <= max_days):
                        continue

                    # Fill computed duration if model doesn't compute it
                    # (models.FlightDeal defines trip_duration property currently)
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
        if not cfg.has_amadeus:
            raise APIError("Amadeus credentials missing (AMADEUS_CLIENT_ID/AMADEUS_CLIENT_SECRET)")

        with self._token_lock:
            if self._access_token and time.time() < (self._token_expires_at - 30):
                return self._access_token

            url = f"{self.config.base_url}/v1/security/oauth2/token"
            data = {
                "grant_type": "client_credentials",
                "client_id": cfg.amadeus_client_id,
                "client_secret": cfg.amadeus_client_secret,
            }

            self._rate_limit()
            try:
                resp = self._session.post(url, data=data, timeout=self.config.timeout, verify=self.config.verify_ssl)
            except requests.exceptions.RequestException as e:
                raise APIError(f"Amadeus token request failed: {e}")

            if resp.status_code != 200:
                raise APIError(
                    f"Amadeus token request failed (HTTP {resp.status_code}): {_safe_resp_text(resp.text)}",
                    status_code=resp.status_code,
                )

            payload = resp.json() if resp.text else {}
            token = payload.get("access_token")
            expires_in = int(payload.get("expires_in") or 0)
            if not token or expires_in <= 0:
                raise APIError("Amadeus token response missing access_token")

            self._access_token = token
            self._token_expires_at = time.time() + expires_in
            return token

    def _request_json(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        token = self._get_access_token()
        url = f"{self.config.base_url}{path}"
        headers = {"Authorization": f"Bearer {token}"}

        for attempt in range(self.config.max_retries):
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
            except requests.exceptions.RequestException as e:
                # network issue → actionable
                raise APIError(f"Amadeus request failed: {e}")

            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception:
                    return {}

            # actionable failures (should trigger fallback)
            if resp.status_code in (400, 401, 403, 429):
                raise APIError(
                    f"Amadeus rejected the request (HTTP {resp.status_code}): {_safe_resp_text(resp.text)}",
                    status_code=resp.status_code,
                )

            # 5xx: retry then eventually raise
            if resp.status_code >= 500:
                time.sleep(self.config.backoff_factor ** attempt)
                continue

            # other codes treat as empty
            return {}

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
        params: Dict[str, Any] = {
            "origin": origin,
            "destination": destination,
            "departureDate": period,  # "YYYY-MM-DD" or "YYYY-MM-DD,YYYY-MM-DD"
            "oneWay": "false",
            "currency": currency,
        }
        if min_days is not None and max_days is not None:
            params["duration"] = f"{min_days},{max_days}"

        cached = self.cache.get(endpoint, params)
        if cached is not None:
            return cached

        data = self._request_json("GET", endpoint, params=params)
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

    def _normalize_iata(self, code: str) -> str:
        code = (code or "").strip().upper()
        if len(code) == 3 and code.isalpha():
            return code
        # fallback: if user provided something odd, try lookup by db (not expensive)
        a = self.airport_db.get_airport(code)
        return a.iata if a else ""

    def _generate_periods(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Generate month-sized departureDate ranges for Amadeus flight-dates.

        Each element is formatted as "YYYY-MM-DD,YYYY-MM-DD" (inclusive bounds)
        and clamped to the provided start/end window.
        """

        if end_date < start_date:
            return []

        periods: List[str] = []

        # iterate month-by-month
        cur = start_date.replace(day=1)
        end_month = end_date.replace(day=1)

        while cur <= end_month:
            next_month = cur.replace(day=28)  # safe base
            # move to first of next month
            if cur.month == 12:
                next_month = next_month.replace(year=cur.year + 1, month=1)
            else:
                next_month = next_month.replace(month=cur.month + 1)
            next_month = next_month.replace(day=1)

            month_start = cur
            month_end = next_month - timedelta(days=1)

            range_start = max(start_date, month_start)
            range_end = min(end_date, month_end)
            if range_start <= range_end:
                periods.append(f"{range_start:%Y-%m-%d},{range_end:%Y-%m-%d}")

            cur = next_month

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
