'''
Travelpayouts/Aviasales Data API client.
Handles API requests with retry logic, rate limiting, and caching.
'''
import requests
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging
from cache import get_cache
from models import FlightDeal
from airports import get_airport_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class APIConfig:
    '''Configuration for API client.'''
    token: str
    base_url: str = "http://api.travelpayouts.com"
    timeout: int = 10
    max_retries: int = 3
    rate_limit_delay: float = 0.5
    backoff_factor: float = 2.0


class TravelpayoutsClient:
    '''Client for Travelpayouts Data API with caching and rate limiting.'''

    def __init__(self, config: APIConfig):
        self.config = config
        self.cache = get_cache()
        self.airport_db = get_airport_db()
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent': 'FlightDealFinder/1.0'
        })

    def _rate_limit(self):
        '''Enforce rate limiting between requests.'''
        elapsed = time.time() - self.last_request_time
        if elapsed < self.config.rate_limit_delay:
            time.sleep(self.config.rate_limit_delay - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: dict) -> Optional[dict]:
        '''
        Make an API request with retries and exponential backoff.

        Args:
            endpoint: API endpoint path
            params: Query parameters

        Returns:
            Response data or None on failure
        '''
        params['token'] = self.config.token
        url = f"{self.config.base_url}{endpoint}"

        for attempt in range(self.config.max_retries):
            try:
                self._rate_limit()

                response = self.session.get(
                    url,
                    params=params,
                    timeout=self.config.timeout
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    wait_time = self.config.backoff_factor ** attempt
                    logger.warning(f"Rate limited (429). Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                elif response.status_code >= 500:
                    wait_time = self.config.backoff_factor ** attempt
                    logger.warning(f"Server error ({response.status_code}). Retrying in {wait_time}s...")
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(f"API error {response.status_code}: {response.text}")
                    return None

            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{self.config.max_retries})")
                if attempt < self.config.max_retries - 1:
                    time.sleep(self.config.backoff_factor ** attempt)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed: {e}")
                return None

        logger.error(f"Max retries exceeded for {endpoint}")
        return None

    def get_latest_prices(
        self,
        origin: str,
        destination: str,
        period: str,
        currency: str = "EUR",
        one_way: bool = False,
        limit: int = 1000
    ) -> Optional[dict]:
        '''
        Get latest prices for a period.

        Args:
            origin: Origin IATA code
            destination: Destination IATA code
            period: Period in YYYY-MM format
            currency: Currency code (default: EUR)
            one_way: True for one-way, False for round-trip
            limit: Max results to return

        Returns:
            API response data or None
        '''
        endpoint = "/aviasales/v3/get_latest_prices"
        params = {
            'origin': origin,
            'destination': destination,
            'beginning_of_period': period,
            'period_type': 'month',
            'currency': currency,
            'one_way': str(one_way).lower(),
            'limit': limit
        }

        cached = self.cache.get(endpoint, params)
        if cached is not None:
            logger.info(f"Cache hit for {origin}-{destination} {period}")
            return cached

        logger.info(f"Fetching {origin}-{destination} {period}")
        data = self._make_request(endpoint, params)

        if data is not None:
            self.cache.set(endpoint, params, data)

        return data

    def search_deals(
        self,
        origin: str,
        destinations: List[str],
        start_date: datetime,
        end_date: datetime,
        min_days: int,
        max_days: int,
        max_results: int = 1000,
        progress_callback = None
    ) -> List[FlightDeal]:
        '''
        Search for flight deals across multiple destinations and periods.

        Args:
            origin: Origin IATA code
            destinations: List of destination IATA codes
            start_date: Start of search period
            end_date: End of search period
            min_days: Minimum trip duration
            max_days: Maximum trip duration
            max_results: Maximum results to return
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of FlightDeal objects sorted by price
        '''
        deals = []
        origin_airport = self.airport_db.get_airport(origin)

        if not origin_airport:
            logger.error(f"Unknown origin airport: {origin}")
            return []

        periods = self._generate_periods(start_date, end_date)

        total_queries = len(destinations) * len(periods)
        current_query = 0

        for destination in destinations:
            if destination == origin:
                continue

            dest_airport = self.airport_db.get_airport(destination)
            if not dest_airport:
                logger.warning(f"Unknown destination: {destination}")
                continue

            for period in periods:
                current_query += 1

                if progress_callback:
                    progress_callback(
                        current_query,
                        total_queries,
                        f"Searching {origin} → {destination} ({period})"
                    )

                result = self.get_latest_prices(
                    origin=origin,
                    destination=destination,
                    period=period,
                    currency="EUR",
                    one_way=False
                )

                if result and 'data' in result:
                    for item in result['data']:
                        deal = self._parse_deal(item, origin_airport, dest_airport)
                        if deal and min_days <= deal.trip_duration <= max_days:
                            deals.append(deal)

        deals = self._deduplicate_deals(deals)
        deals = sorted(deals, key=lambda d: (
            d.price_eur,
            d.transfers if d.transfers is not None else 999,
            d.depart_date
        ))

        return deals[:max_results]

    def _generate_periods(self, start_date: datetime, end_date: datetime) -> List[str]:
        '''Generate list of month periods (YYYY-MM) between dates.'''
        periods = []
        current = start_date.replace(day=1)
        end = end_date.replace(day=1)

        while current <= end:
            periods.append(current.strftime('%Y-%m'))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return periods

    def _parse_deal(
        self,
        data: dict,
        origin_airport,
        dest_airport
    ) -> Optional[FlightDeal]:
        '''Parse API response data into FlightDeal object.'''
        try:
            price = float(data.get('value', data.get('price', 0)))

            depart_date = data.get('departure_at', data.get('depart_date', ''))
            return_date = data.get('return_at', data.get('return_date', ''))

            if not depart_date or not return_date or price <= 0:
                return None

            expires_at_str = data.get('expires_at')
            expires_at = None
            if expires_at_str:
                try:
                    expires_at = datetime.fromisoformat(
                        expires_at_str.replace('Z', '+00:00')
                    )
                except:
                    pass

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
                transfers=(int(data.get('transfers', data.get('number_of_changes'))) if data.get('transfers', data.get('number_of_changes')) is not None else None),
                airline=data.get('airline'),
                flight_number=data.get('flight_number'),
                deep_link=data.get('link') or data.get('deep_link'),
                found_at=datetime.utcnow(),
                expires_at=expires_at,
                raw_payload=data
            )

            return deal

        except Exception as e:
            logger.warning(f"Failed to parse deal: {e}")
            return None

    def _deduplicate_deals(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        '''Remove duplicate deals (same route and dates).'''
        seen = set()
        unique_deals = []

        for deal in deals:
            key = (
                deal.origin_iata,
                deal.dest_iata,
                deal.depart_date[:10],
                deal.return_date[:10]
            )

            if key not in seen:
                seen.add(key)
                unique_deals.append(deal)

        return unique_deals
