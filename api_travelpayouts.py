"""Travelpayouts/Aviasales API client (legacy but reliable).

This is based on the previously working implementation in api_client_old.py.
It exposes the same surface as AmadeusClient: search_deals(...)

This provider is used as a fallback when Amadeus returns a request/auth error.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import requests

from airports import get_airport_db
from cache import get_cache
from models import FlightDeal


class APIError(RuntimeError):
    """Actionable provider error (safe to show to users)."""

    def __init__(self, message: str, *, status_code: Optional[int] = None, provider: str = "Travelpayouts"):
        super().__init__(message)
        self.status_code = status_code
        self.provider = provider


@dataclass
class TravelpayoutsConfig:
    token: str
    base_url: str = "https://api.travelpayouts.com"
    timeout: int = 10
    max_retries: int = 3
    rate_limit_delay: float = 0.5
    backoff_factor: float = 2.0


class TravelpayoutsClient:
    def __init__(self, config: TravelpayoutsConfig):
        if not config.token:
            raise APIError("Travelpayouts token not configured (TRAVELPAYOUTS_TOKEN)", provider="Travelpayouts")

        self.config = config
        self.cache = get_cache()
        self.airport_db = get_airport_db()
        self.last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({'Accept-Encoding': 'gzip, deflate', 'User-Agent': 'FlightDealFinder/1.0'})

    def search_deals(
        self,
        *,
        origin: str,
        destinations: List[str],
        start_date: datetime,
        end_date: datetime,
        min_days: int,
        max_days: int,
        max_results: int = 1000,
        progress_callback=None,
        cancel_flag: Optional[dict] = None,
    ) -> List[FlightDeal]:
        deals: List[FlightDeal] = []

        origin_airport = self.airport_db.get_airport(origin)
        if not origin_airport:
            return []

        periods = self._generate_periods(start_date, end_date)
        total_queries = len(destinations) * len(periods)
        current_query = 0

        for destination in destinations:
            if cancel_flag and cancel_flag.get('cancelled', False):
                break

            if destination == origin:
                continue

            dest_airport = self.airport_db.get_airport(destination)
            if not dest_airport:
                continue

            for period in periods:
                if cancel_flag and cancel_flag.get('cancelled', False):
                    break

                current_query += 1
                if progress_callback:
                    progress_callback(current_query, total_queries, f"Travelpayouts {origin}→{destination} ({period})")

                result = self.get_latest_prices(origin=origin, destination=destination, period=period, currency="EUR", one_way=False)
                if result and 'data' in result:
                    for item in result['data']:
                        deal = self._parse_deal(item, origin_airport, dest_airport)
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

                        # Filter 3: Return date should not be before departure date
                        if return_dt < depart_dt:
                            continue

                        deals.append(deal)

        deals = self._deduplicate_deals(deals)
        deals = sorted(deals, key=lambda d: (d.price_eur, d.transfers if d.transfers is not None else 999, d.depart_date))
        return deals[:max_results]

    # ---- API calls ----

    def get_latest_prices(self, *, origin: str, destination: str, period: str, currency: str, one_way: bool, limit: int = 1000) -> Optional[dict]:
        endpoint = "/aviasales/v3/get_latest_prices"
        params = {
            'origin': origin,
            'destination': destination,
            'beginning_of_period': period,
            'period_type': 'month',
            'currency': currency,
            'one_way': str(one_way).lower(),
            'limit': limit,
        }

        cached = self.cache.get(endpoint, params)
        if cached is not None:
            return cached

        data = self._make_request(endpoint, params)
        if data is not None:
            self.cache.set(endpoint, params, data)
        return data

    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        params = dict(params)
        params['token'] = self.config.token
        url = f"{self.config.base_url}{endpoint}"

        last_status: Optional[int] = None
        last_text: str = ""

        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit()
                response = self.session.get(url, params=params, timeout=self.config.timeout)
                last_status = response.status_code
                last_text = (response.text or "")[:300]

                if response.status_code == 200:
                    return response.json()

                if response.status_code == 401 or response.status_code == 403:
                    raise APIError(
                        "Travelpayouts authorization failed (check TRAVELPAYOUTS_TOKEN).",
                        status_code=response.status_code,
                        provider="Travelpayouts",
                    )

                if response.status_code == 429:
                    wait_time = self.config.backoff_factor ** attempt
                    time.sleep(wait_time)
                    continue

                if response.status_code >= 500:
                    wait_time = self.config.backoff_factor ** attempt
                    time.sleep(wait_time)
                    continue

                # 4xx other than auth: treat as non-fatal (no results)
                return None

            except requests.exceptions.Timeout:
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.backoff_factor ** attempt)
            except requests.exceptions.RequestException as e:
                raise APIError(f"Travelpayouts request failed: {e}", provider="Travelpayouts")

        # Retries exhausted on 429/5xx/timeouts
        if last_status in (429,) or (last_status is not None and last_status >= 500):
            raise APIError(
                f"Travelpayouts is temporarily unavailable (HTTP {last_status}). Try again later.",
                status_code=last_status,
                provider="Travelpayouts",
            )

        return None

    def _rate_limit(self) -> None:
        elapsed = time.time() - self.last_request_time
        if elapsed < self.config.rate_limit_delay:
            time.sleep(self.config.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    # ---- parsing helpers ----

    def _generate_periods(self, start_date: datetime, end_date: datetime) -> List[str]:
        periods: List[str] = []
        current = start_date.replace(day=1)
        end = end_date.replace(day=1)
        while current <= end:
            periods.append(current.strftime('%Y-%m'))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)
        return periods

    def _parse_deal(self, data: dict, origin_airport, dest_airport) -> Optional[FlightDeal]:
        try:
            price = float(data.get('value', data.get('price', 0)))
            depart_date = data.get('departure_at', data.get('depart_date', ''))
            return_date = data.get('return_at', data.get('return_date', ''))

            if not depart_date or not return_date or price <= 0:
                return None

            deal = FlightDeal(
                origin_iata=origin_airport.iata,
                dest_iata=dest_airport.iata,
                origin_city=origin_airport.city,
                dest_city=dest_airport.city,
                origin_flag=origin_airport.flag_emoji,
                dest_flag=dest_airport.flag_emoji,
                depart_date=depart_date,
                return_date=return_date,
                price_eur=price,
                transfers=data.get('transfers', data.get('number_of_changes')),
                airline=data.get('airline'),
                flight_number=data.get('flight_number'),
                deep_link=data.get('link'),
                found_at=datetime.utcnow(),
                expires_at=None,
                raw_payload=data,
            )
            return deal

        except Exception:
            return None

    def _deduplicate_deals(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        seen = set()
        unique: List[FlightDeal] = []
        for d in deals:
            key = (d.origin_iata, d.dest_iata, d.depart_date[:10], d.return_date[:10])
            if key in seen:
                continue
            seen.add(key)
            unique.append(d)
        return unique

