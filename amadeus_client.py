"""
Amadeus Flights API Client

Replaces Travelpayouts with a 2-step approach:
A) EXPLORE: Cheap, cached, minimal requests for discovering destinations
B) CONFIRM: Optional, capped requests for getting bookable offers

Implements OAuth2 authentication, caching, rate limiting, and strict call budgets.
"""

import os
import time
import random
import logging
import hashlib
import json
import threading
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

import requests

from cache import get_cache
from models import FlightDeal
from airports import get_airport_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================================================
# ERROR CODES
# ============================================================================

class AmadeusErrorCode(Enum):
    """Structured error codes for Amadeus API errors."""
    AMADEUS_AUTH_FAILED = "AMADEUS_AUTH_FAILED"
    AMADEUS_RATE_LIMITED = "AMADEUS_RATE_LIMITED"
    AMADEUS_QUOTA_EXCEEDED = "AMADEUS_QUOTA_EXCEEDED"
    AMADEUS_BAD_REQUEST = "AMADEUS_BAD_REQUEST"
    AMADEUS_UPSTREAM_ERROR = "AMADEUS_UPSTREAM_ERROR"
    AMADEUS_TIMEOUT = "AMADEUS_TIMEOUT"
    AMADEUS_NETWORK_ERROR = "AMADEUS_NETWORK_ERROR"


class AmadeusAPIError(Exception):
    """Custom exception for Amadeus API errors."""
    def __init__(self, code: AmadeusErrorCode, message: str, details: dict = None):
        self.code = code
        self.message = message
        self.details = details or {}
        super().__init__(f"{code.value}: {message}")


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class AmadeusConfig:
    """Configuration for Amadeus API client."""
    client_id: str
    client_secret: str
    base_url: str = "https://test.api.amadeus.com"
    mode: str = "test"  # "test" or "prod"
    default_currency: str = "EUR"
    timeout: int = 15
    max_retries: int = 2
    backoff_base: float = 1.0
    backoff_jitter: float = 0.5
    # Rate limiting for TEST environment
    global_rate_limit: float = 1.0  # seconds between requests
    # Explore cache TTL (6-24 hours)
    explore_cache_ttl_hours: int = 12
    # Confirm cache TTL (5-15 minutes)
    confirm_cache_ttl_minutes: int = 10
    # Confirm call caps
    max_confirm_calls_per_session: int = 3
    confirm_cap_window_minutes: int = 10


# ============================================================================
# REGION MAPPING FOR EUROPE FILTER
# ============================================================================

EUROPE_COUNTRY_CODES = {
    "AL", "AD", "AT", "BY", "BE", "BA", "BG", "HR", "CY", "CZ",
    "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IS", "IE", "IT",
    "XK", "LV", "LI", "LT", "LU", "MT", "MD", "MC", "ME", "NL",
    "MK", "NO", "PL", "PT", "RO", "RU", "SM", "RS", "SK", "SI",
    "ES", "SE", "CH", "TR", "UA", "GB", "VA"
}


def is_european_destination(country_code: str) -> bool:
    """Check if a country code is in Europe."""
    return country_code.upper() in EUROPE_COUNTRY_CODES


# ============================================================================
# TOKEN MANAGER
# ============================================================================

class TokenManager:
    """Manages OAuth2 token lifecycle with caching and early refresh."""

    def __init__(self, config: AmadeusConfig):
        self.config = config
        self._token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._lock = threading.Lock()

    def get_token(self) -> str:
        """Get a valid access token, refreshing if needed."""
        with self._lock:
            if self._is_token_valid():
                return self._token
            return self._fetch_new_token()

    def _is_token_valid(self) -> bool:
        """Check if current token is valid with 60s buffer."""
        if not self._token or not self._expires_at:
            return False
        # Refresh 60 seconds early
        return datetime.utcnow() < (self._expires_at - timedelta(seconds=60))

    def _fetch_new_token(self) -> str:
        """Fetch a new access token from Amadeus."""
        url = f"{self.config.base_url}/v1/security/oauth2/token"

        try:
            response = requests.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.config.client_id,
                    "client_secret": self.config.client_secret
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=self.config.timeout
            )

            if response.status_code == 200:
                data = response.json()
                self._token = data["access_token"]
                expires_in = data.get("expires_in", 1799)  # Default ~30 min
                self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)
                logger.info(f"Amadeus token acquired, expires in {expires_in}s")
                return self._token

            elif response.status_code == 401:
                raise AmadeusAPIError(
                    AmadeusErrorCode.AMADEUS_AUTH_FAILED,
                    "Invalid client credentials",
                    {"status": response.status_code}
                )
            else:
                raise AmadeusAPIError(
                    AmadeusErrorCode.AMADEUS_AUTH_FAILED,
                    f"Token fetch failed: {response.status_code}",
                    {"status": response.status_code, "body": response.text[:200]}
                )

        except requests.exceptions.Timeout:
            raise AmadeusAPIError(
                AmadeusErrorCode.AMADEUS_TIMEOUT,
                "Token request timed out"
            )
        except requests.exceptions.RequestException as e:
            raise AmadeusAPIError(
                AmadeusErrorCode.AMADEUS_NETWORK_ERROR,
                f"Network error during auth: {str(e)}"
            )

    def invalidate(self):
        """Invalidate the current token (e.g., on 401)."""
        with self._lock:
            self._token = None
            self._expires_at = None


# ============================================================================
# CONFIRM CALL TRACKER
# ============================================================================

class ConfirmCallTracker:
    """Tracks confirm calls per session/client to enforce caps."""

    def __init__(self, max_calls: int, window_minutes: int):
        self.max_calls = max_calls
        self.window_minutes = window_minutes
        self._calls: Dict[str, List[datetime]] = {}
        self._lock = threading.Lock()

    def can_make_call(self, client_id: str = "default") -> Tuple[bool, int]:
        """
        Check if a confirm call can be made.
        Returns (allowed, remaining_calls).
        """
        with self._lock:
            self._cleanup_old_calls(client_id)
            calls = self._calls.get(client_id, [])
            remaining = self.max_calls - len(calls)
            return remaining > 0, max(0, remaining)

    def record_call(self, client_id: str = "default"):
        """Record a confirm call."""
        with self._lock:
            if client_id not in self._calls:
                self._calls[client_id] = []
            self._calls[client_id].append(datetime.utcnow())

    def _cleanup_old_calls(self, client_id: str):
        """Remove calls older than the window."""
        if client_id not in self._calls:
            return
        cutoff = datetime.utcnow() - timedelta(minutes=self.window_minutes)
        self._calls[client_id] = [c for c in self._calls[client_id] if c > cutoff]

    def get_remaining(self, client_id: str = "default") -> int:
        """Get remaining confirm calls for a client."""
        _, remaining = self.can_make_call(client_id)
        return remaining


# ============================================================================
# AMADEUS FLIGHTS CLIENT
# ============================================================================

class AmadeusFlightsClient:
    """
    Amadeus Flights API client with 2-step approach:
    - EXPLORE: Discover destinations with minimal API calls
    - CONFIRM: Get bookable offers (capped)
    """

    def __init__(self, config: AmadeusConfig):
        self.config = config
        self.cache = get_cache()
        self.airport_db = get_airport_db()
        self.token_manager = TokenManager(config)
        self.confirm_tracker = ConfirmCallTracker(
            config.max_confirm_calls_per_session,
            config.confirm_cap_window_minutes
        )

        # Global rate limiter
        self._last_request_time = 0
        self._rate_lock = threading.Lock()

        # Request tracking for debugging
        self._request_count = 0
        self._request_lock = threading.Lock()

        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "FlightDealFinder/2.0"
        })

    # ========================================================================
    # RATE LIMITING
    # ========================================================================

    def _rate_limit(self):
        """Enforce global rate limit (TEST mode protection)."""
        with self._rate_lock:
            elapsed = time.time() - self._last_request_time
            wait_time = self.config.global_rate_limit - elapsed
            if wait_time > 0:
                time.sleep(wait_time)
            self._last_request_time = time.time()

    def _increment_request_count(self) -> int:
        """Increment and return request count for logging."""
        with self._request_lock:
            self._request_count += 1
            return self._request_count

    # ========================================================================
    # HTTP REQUEST HELPER
    # ========================================================================

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict = None,
        json_body: dict = None,
        max_retries: int = None
    ) -> dict:
        """
        Make an authenticated request to Amadeus API with retry logic.

        Only retries on 5xx and network errors.
        For 429: single retry after delay, then fail fast.
        """
        max_retries = max_retries if max_retries is not None else self.config.max_retries
        url = f"{self.config.base_url}{endpoint}"
        request_id = self._increment_request_count()

        for attempt in range(max_retries + 1):
            try:
                self._rate_limit()

                token = self.token_manager.get_token()
                headers = {"Authorization": f"Bearer {token}"}

                logger.info(f"[REQ-{request_id}] {method} {endpoint} (attempt {attempt + 1})")

                if method.upper() == "GET":
                    response = self.session.get(
                        url,
                        params=params,
                        headers=headers,
                        timeout=self.config.timeout
                    )
                else:  # POST
                    response = self.session.post(
                        url,
                        params=params,
                        json=json_body,
                        headers=headers,
                        timeout=self.config.timeout
                    )

                # Success
                if response.status_code == 200:
                    logger.info(f"[REQ-{request_id}] Success")
                    return response.json()

                # Rate limited
                if response.status_code == 429:
                    logger.warning(f"[REQ-{request_id}] Rate limited (429)")
                    # Check for Retry-After header
                    retry_after = response.headers.get("Retry-After", "2")
                    try:
                        wait_time = min(int(retry_after), 5)  # Cap at 5s
                    except ValueError:
                        wait_time = 2

                    if attempt == 0:
                        # One retry for rate limit
                        logger.info(f"[REQ-{request_id}] Waiting {wait_time}s before retry")
                        time.sleep(wait_time)
                        continue
                    else:
                        # Don't retry aggressively
                        raise AmadeusAPIError(
                            AmadeusErrorCode.AMADEUS_RATE_LIMITED,
                            "Rate limit exceeded - stopping further requests",
                            {"retry_after": wait_time}
                        )

                # Quota exceeded (usually different from rate limit)
                if response.status_code == 403:
                    error_data = response.json() if response.text else {}
                    raise AmadeusAPIError(
                        AmadeusErrorCode.AMADEUS_QUOTA_EXCEEDED,
                        "API quota exceeded",
                        {"details": error_data}
                    )

                # Auth failed
                if response.status_code == 401:
                    self.token_manager.invalidate()
                    if attempt == 0:
                        # Retry once with new token
                        continue
                    raise AmadeusAPIError(
                        AmadeusErrorCode.AMADEUS_AUTH_FAILED,
                        "Authentication failed after retry"
                    )

                # Bad request
                if response.status_code == 400:
                    error_data = response.json() if response.text else {}
                    raise AmadeusAPIError(
                        AmadeusErrorCode.AMADEUS_BAD_REQUEST,
                        f"Bad request: {response.text[:200]}",
                        {"details": error_data}
                    )

                # Server error - retry with backoff
                if response.status_code >= 500:
                    if attempt < max_retries:
                        wait_time = self._calculate_backoff(attempt)
                        logger.warning(f"[REQ-{request_id}] Server error {response.status_code}, retrying in {wait_time:.1f}s")
                        time.sleep(wait_time)
                        continue
                    raise AmadeusAPIError(
                        AmadeusErrorCode.AMADEUS_UPSTREAM_ERROR,
                        f"Server error: {response.status_code}",
                        {"status": response.status_code}
                    )

                # Other errors
                raise AmadeusAPIError(
                    AmadeusErrorCode.AMADEUS_UPSTREAM_ERROR,
                    f"Unexpected status: {response.status_code}",
                    {"status": response.status_code, "body": response.text[:200]}
                )

            except requests.exceptions.Timeout:
                if attempt < max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(f"[REQ-{request_id}] Timeout, retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue
                raise AmadeusAPIError(
                    AmadeusErrorCode.AMADEUS_TIMEOUT,
                    "Request timed out after retries"
                )

            except requests.exceptions.RequestException as e:
                if attempt < max_retries:
                    wait_time = self._calculate_backoff(attempt)
                    logger.warning(f"[REQ-{request_id}] Network error, retrying in {wait_time:.1f}s")
                    time.sleep(wait_time)
                    continue
                raise AmadeusAPIError(
                    AmadeusErrorCode.AMADEUS_NETWORK_ERROR,
                    f"Network error: {str(e)}"
                )

        # Should not reach here, but just in case
        raise AmadeusAPIError(
            AmadeusErrorCode.AMADEUS_UPSTREAM_ERROR,
            "Max retries exceeded"
        )

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter."""
        base = self.config.backoff_base * (2 ** attempt)
        jitter = random.uniform(0, self.config.backoff_jitter)
        return base + jitter

    # ========================================================================
    # CACHE HELPERS
    # ========================================================================

    def _make_cache_key(self, prefix: str, params: dict) -> str:
        """Generate a cache key from prefix and parameters."""
        sorted_params = json.dumps(params, sort_keys=True)
        key_string = f"{prefix}:{sorted_params}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _get_explore_cached(self, cache_key: str) -> Optional[dict]:
        """Get cached explore results."""
        return self.cache.get("amadeus_explore", {"key": cache_key})

    def _set_explore_cached(self, cache_key: str, data: dict):
        """Cache explore results with configured TTL."""
        # Note: We're using the existing cache which has 6h TTL
        # For longer TTL, we'd need to modify the cache or use a separate table
        self.cache.set("amadeus_explore", {"key": cache_key}, data)

    def _get_confirm_cached(self, cache_key: str) -> Optional[dict]:
        """Get cached confirm results."""
        return self.cache.get("amadeus_confirm", {"key": cache_key})

    def _set_confirm_cached(self, cache_key: str, data: dict):
        """Cache confirm results briefly."""
        self.cache.set("amadeus_confirm", {"key": cache_key}, data)

    # ========================================================================
    # USE CASE 1: EXPLORE DEALS (Minimal Calls)
    # ========================================================================

    def get_explore_deals(
        self,
        origin: str,
        month: str,
        currency: str = "EUR",
        region_hint: str = "Europe",
        adults: int = 1,
        progress_callback=None
    ) -> List[FlightDeal]:
        """
        Explore cheap destinations from an origin for a given month.

        Uses Amadeus Flight Inspiration Search API which returns multiple
        destinations in a single call.

        Args:
            origin: Origin IATA code (e.g., "OPO")
            month: Month in "YYYY-MM" format (e.g., "2026-05")
            currency: Currency code (default: EUR)
            region_hint: Region to filter (default: "Europe")
            adults: Number of adults (for pricing reference)
            progress_callback: Optional callback(current, total, message)

        Returns:
            List of FlightDeal objects with indicative prices

        Call Budget: 1-3 Amadeus requests for entire month query
        """
        logger.info(f"Explore deals: {origin} for {month}, region={region_hint}")

        # Build cache key
        cache_params = {
            "origin": origin,
            "month": month,
            "currency": currency,
            "region": region_hint,
            "adults": adults
        }
        cache_key = self._make_cache_key("explore", cache_params)

        # Check cache first
        cached = self._get_explore_cached(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for explore {origin}/{month}")
            return self._parse_explore_response(cached, origin, region_hint)

        # Parse month to get date range
        try:
            year, month_num = map(int, month.split("-"))
            # Get first and last day of month
            first_day = datetime(year, month_num, 1)
            if month_num == 12:
                last_day = datetime(year + 1, 1, 1) - timedelta(days=1)
            else:
                last_day = datetime(year, month_num + 1, 1) - timedelta(days=1)
        except ValueError:
            logger.error(f"Invalid month format: {month}")
            return []

        # Strategy: Use Flight Offers Search for specific destinations
        # The Flight Inspiration Search endpoint is unreliable in TEST mode
        # Instead, we query popular destinations with minimal calls

        all_deals = []

        # Get list of destinations to check based on region hint
        destinations_to_check = self._get_popular_destinations(origin, region_hint)

        # Sample 1-2 dates in the month to minimize calls
        sample_dates = []
        mid_month = datetime(year, month_num, 15)
        if mid_month >= datetime.now():
            sample_dates.append(mid_month.strftime("%Y-%m-%d"))
        elif first_day >= datetime.now():
            sample_dates.append(first_day.strftime("%Y-%m-%d"))

        if not sample_dates:
            # Month is in the past
            logger.warning(f"Month {month} is in the past")
            return []

        departure_date = sample_dates[0]
        return_date = (datetime.strptime(departure_date, "%Y-%m-%d") + timedelta(days=7)).strftime("%Y-%m-%d")

        logger.info(f"Searching {len(destinations_to_check)} destinations for {departure_date}")

        # Batch destinations to minimize calls (1 call can check multiple in parallel via async)
        # But we'll do sequential calls with rate limiting for simplicity
        # Limit to MAX 3 destination calls to respect budget
        destinations_to_check = destinations_to_check[:3]

        for idx, dest in enumerate(destinations_to_check):
            if progress_callback:
                progress_callback(
                    idx,
                    len(destinations_to_check),
                    f"Checking flights to {dest}..."
                )

            try:
                # Use Flight Offers Search (more reliable than Inspiration)
                response = self._make_request(
                    "POST",
                    "/v2/shopping/flight-offers",
                    json_body={
                        "currencyCode": currency,
                        "originDestinations": [
                            {
                                "id": "1",
                                "originLocationCode": origin,
                                "destinationLocationCode": dest,
                                "departureDateTimeRange": {
                                    "date": departure_date
                                }
                            },
                            {
                                "id": "2",
                                "originLocationCode": dest,
                                "destinationLocationCode": origin,
                                "departureDateTimeRange": {
                                    "date": return_date
                                }
                            }
                        ],
                        "travelers": [
                            {"id": "1", "travelerType": "ADULT"}
                        ],
                        "sources": ["GDS"],
                        "searchCriteria": {
                            "maxFlightOffers": 3,  # Just get top 3 cheapest
                            "flightFilters": {
                                "cabinRestrictions": [
                                    {
                                        "cabin": "ECONOMY",
                                        "coverage": "MOST_SEGMENTS",
                                        "originDestinationIds": ["1", "2"]
                                    }
                                ]
                            }
                        }
                    }
                )

                if response and "data" in response:
                    # Parse offers into deals
                    offers = self._parse_flight_offers(response, origin, dest, departure_date, return_date)
                    all_deals.extend(offers)

            except AmadeusAPIError as e:
                logger.warning(f"Search failed for {origin}->{dest}: {e}")
                if e.code == AmadeusErrorCode.AMADEUS_RATE_LIMITED:
                    logger.error("Rate limited - stopping explore calls")
                    break
                continue

        if progress_callback:
            progress_callback(len(destinations_to_check), len(destinations_to_check), "Processing results...")

        # Cache results
        if all_deals:
            self._set_explore_cached(cache_key, {"deals": [d.__dict__ for d in all_deals]})

        # Sort by price
        all_deals = sorted(all_deals, key=lambda d: d.price_eur)

        logger.info(f"Found {len(all_deals)} deals")
        return all_deals

    def _get_popular_destinations(self, origin: str, region_hint: str) -> List[str]:
        """Get popular destinations based on origin and region hint."""
        # Popular European destinations from major hubs
        europe_popular = ["LHR", "CDG", "FCO", "BCN", "AMS", "FRA", "MAD", "MUC", "ZRH", "VIE"]

        # Remove origin from list
        destinations = [d for d in europe_popular if d != origin]

        # If specific region, filter or adjust
        if region_hint == "Europe" or not region_hint:
            return destinations[:5]  # Top 5 European

        return destinations[:3]

    def _parse_flight_offers(
        self,
        response: dict,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: str
    ) -> List[FlightDeal]:
        """Parse Flight Offers Search response into FlightDeal objects."""
        deals = []

        origin_airport = self.airport_db.get_airport(origin)
        dest_airport = self.airport_db.get_airport(destination)

        if not origin_airport or not dest_airport:
            return []

        data = response.get("data", [])
        dictionaries = response.get("dictionaries", {})
        carriers = dictionaries.get("carriers", {})

        for offer in data:
            try:
                # Extract price
                price_info = offer.get("price", {})
                price = float(price_info.get("grandTotal", price_info.get("total", 0)))
                if price <= 0:
                    continue

                # Extract itineraries
                itineraries = offer.get("itineraries", [])
                if not itineraries:
                    continue

                # Outbound flight
                outbound = itineraries[0]
                outbound_segments = outbound.get("segments", [])
                if not outbound_segments:
                    continue

                actual_departure = outbound_segments[0].get("departure", {}).get("at", departure_date)
                num_stops = len(outbound_segments) - 1

                # Get carrier info
                carrier_code = outbound_segments[0].get("carrierCode", "")
                airline = carriers.get(carrier_code, carrier_code)

                # Return flight
                actual_return = return_date
                if len(itineraries) > 1:
                    inbound = itineraries[1]
                    inbound_segments = inbound.get("segments", [])
                    if inbound_segments:
                        actual_return = inbound_segments[0].get("departure", {}).get("at", return_date)

                deal = FlightDeal(
                    origin_iata=origin,
                    dest_iata=destination,
                    origin_city=origin_airport.city,
                    dest_city=dest_airport.city,
                    origin_flag=origin_airport.flag_emoji,
                    dest_flag=dest_airport.flag_emoji,
                    depart_date=actual_departure[:10] if len(actual_departure) >= 10 else actual_departure,
                    return_date=actual_return[:10] if len(actual_return) >= 10 else actual_return,
                    price_eur=price,
                    transfers=num_stops,
                    airline=airline,
                    flight_number=None,
                    deep_link=None,
                    found_at=datetime.utcnow(),
                    expires_at=None,
                    raw_payload=offer
                )
                deals.append(deal)

            except Exception as e:
                logger.warning(f"Failed to parse offer: {e}")
                continue

        return deals

    def _parse_explore_response(
        self,
        response: dict,
        origin: str,
        region_hint: str
    ) -> List[FlightDeal]:
        """Parse cached explore response back into FlightDeal objects."""
        # Check if this is cached deal data
        if "deals" in response:
            deals = []
            for deal_dict in response["deals"]:
                try:
                    deal = FlightDeal(**{k: v for k, v in deal_dict.items() if k != 'raw_payload'})
                    deal.raw_payload = deal_dict.get('raw_payload', {})
                    deals.append(deal)
                except Exception as e:
                    logger.warning(f"Failed to restore cached deal: {e}")
            return deals

        # Legacy format from inspiration search (if it ever works)
        deals = []
        seen_destinations = {}  # Track best price per destination+date

        origin_airport = self.airport_db.get_airport(origin)
        if not origin_airport:
            logger.warning(f"Unknown origin airport: {origin}")
            return []

        data = response.get("data", [])

        for item in data:
            try:
                destination = item.get("destination", "")
                if not destination:
                    continue

                dest_airport = self.airport_db.get_airport(destination)
                if not dest_airport:
                    continue

                # Apply region filter
                if region_hint == "Europe":
                    if not is_european_destination(dest_airport.country_code):
                        continue

                # Extract price
                price_info = item.get("price", {})
                price = float(price_info.get("total", 0))
                if price <= 0:
                    continue

                # Extract dates
                departure_date = item.get("departureDate", "")
                return_date = item.get("returnDate", "")

                if not departure_date:
                    continue

                # Deduplicate - keep cheapest per destination+departure
                key = (destination, departure_date)
                if key in seen_destinations:
                    if price >= seen_destinations[key]:
                        continue
                seen_destinations[key] = price

                # Build FlightDeal object
                deal = FlightDeal(
                    origin_iata=origin,
                    dest_iata=destination,
                    origin_city=origin_airport.city,
                    dest_city=dest_airport.city,
                    origin_flag=origin_airport.flag_emoji,
                    dest_flag=dest_airport.flag_emoji,
                    depart_date=departure_date,
                    return_date=return_date if return_date else departure_date,
                    price_eur=price,
                    transfers=None,  # Inspiration search doesn't provide this
                    airline=item.get("links", {}).get("flightOffers", ""),
                    flight_number=None,
                    deep_link=None,
                    found_at=datetime.utcnow(),
                    expires_at=None,
                    raw_payload=item
                )
                deals.append(deal)

            except Exception as e:
                logger.warning(f"Failed to parse explore item: {e}")
                continue

        # Sort by price
        deals = sorted(deals, key=lambda d: (d.price_eur, d.depart_date))

        logger.info(f"Parsed {len(deals)} explore deals from response")
        return deals

    # ========================================================================
    # USE CASE 2: CONFIRM OFFERS (Capped)
    # ========================================================================

    def get_confirm_offers(
        self,
        origin: str,
        destination: str,
        date: str,
        adults: int = 1,
        currency: str = "EUR",
        client_id: str = "default"
    ) -> List[FlightDeal]:
        """
        Get bookable flight offers for a specific route and date.

        This method is CAPPED to prevent runaway API calls.
        Max 3 calls per client/session within a 10-minute window.

        Args:
            origin: Origin IATA code
            destination: Destination IATA code
            date: Departure date (YYYY-MM-DD)
            adults: Number of adult passengers (default: 1)
            currency: Currency code (default: EUR)
            client_id: Client identifier for rate limiting

        Returns:
            List of FlightDeal objects with bookable offers

        Raises:
            AmadeusAPIError: If cap exceeded or API error
        """
        logger.info(f"Confirm offers: {origin}->{destination} on {date}")

        # Check confirm call cap
        can_call, remaining = self.confirm_tracker.can_make_call(client_id)
        if not can_call:
            logger.warning(f"Confirm call cap exceeded for client {client_id}")
            raise AmadeusAPIError(
                AmadeusErrorCode.AMADEUS_RATE_LIMITED,
                f"Confirm call limit reached (max {self.config.max_confirm_calls_per_session} per {self.config.confirm_cap_window_minutes} minutes)",
                {"remaining_calls": 0}
            )

        # Build cache key
        cache_params = {
            "origin": origin,
            "destination": destination,
            "date": date,
            "adults": adults,
            "currency": currency
        }
        cache_key = self._make_cache_key("confirm", cache_params)

        # Check cache first
        cached = self._get_confirm_cached(cache_key)
        if cached is not None:
            logger.info(f"Cache hit for confirm {origin}->{destination}/{date}")
            return self._parse_confirm_response(cached, origin, destination)

        # Record the call BEFORE making it (to prevent race conditions)
        self.confirm_tracker.record_call(client_id)
        logger.info(f"Confirm call recorded. Remaining for {client_id}: {remaining - 1}")

        try:
            # Flight Offers Search
            # POST /v2/shopping/flight-offers
            response = self._make_request(
                "POST",
                "/v2/shopping/flight-offers",
                json_body={
                    "currencyCode": currency,
                    "originDestinations": [
                        {
                            "id": "1",
                            "originLocationCode": origin,
                            "destinationLocationCode": destination,
                            "departureDateTimeRange": {
                                "date": date
                            }
                        }
                    ],
                    "travelers": [
                        {"id": str(i + 1), "travelerType": "ADULT"}
                        for i in range(adults)
                    ],
                    "sources": ["GDS"],
                    "searchCriteria": {
                        "maxFlightOffers": 10,  # Limit to avoid pagination
                        "flightFilters": {
                            "cabinRestrictions": [
                                {
                                    "cabin": "ECONOMY",
                                    "coverage": "MOST_SEGMENTS",
                                    "originDestinationIds": ["1"]
                                }
                            ]
                        }
                    }
                }
            )

            # Cache the response
            if response and "data" in response:
                self._set_confirm_cached(cache_key, response)

            return self._parse_confirm_response(response, origin, destination)

        except AmadeusAPIError:
            raise
        except Exception as e:
            logger.error(f"Confirm offers failed: {e}")
            raise AmadeusAPIError(
                AmadeusErrorCode.AMADEUS_UPSTREAM_ERROR,
                f"Failed to fetch offers: {str(e)}"
            )

    def _parse_confirm_response(
        self,
        response: dict,
        origin: str,
        destination: str
    ) -> List[FlightDeal]:
        """Parse Flight Offers Search response into FlightDeal objects."""
        deals = []

        origin_airport = self.airport_db.get_airport(origin)
        dest_airport = self.airport_db.get_airport(destination)

        if not origin_airport or not dest_airport:
            return []

        data = response.get("data", [])
        dictionaries = response.get("dictionaries", {})
        carriers = dictionaries.get("carriers", {})

        for offer in data:
            try:
                # Extract price
                price_info = offer.get("price", {})
                price = float(price_info.get("grandTotal", price_info.get("total", 0)))
                if price <= 0:
                    continue

                # Extract itineraries
                itineraries = offer.get("itineraries", [])
                if not itineraries:
                    continue

                # Outbound flight
                outbound = itineraries[0]
                outbound_segments = outbound.get("segments", [])
                if not outbound_segments:
                    continue

                departure_date = outbound_segments[0].get("departure", {}).get("at", "")
                num_stops = len(outbound_segments) - 1

                # Get carrier info
                carrier_code = outbound_segments[0].get("carrierCode", "")
                airline = carriers.get(carrier_code, carrier_code)
                flight_number = f"{carrier_code}{outbound_segments[0].get('number', '')}"

                # Return flight (if round-trip)
                return_date = departure_date  # Default to same day
                if len(itineraries) > 1:
                    inbound = itineraries[1]
                    inbound_segments = inbound.get("segments", [])
                    if inbound_segments:
                        return_date = inbound_segments[0].get("departure", {}).get("at", "")

                deal = FlightDeal(
                    origin_iata=origin,
                    dest_iata=destination,
                    origin_city=origin_airport.city,
                    dest_city=dest_airport.city,
                    origin_flag=origin_airport.flag_emoji,
                    dest_flag=dest_airport.flag_emoji,
                    depart_date=departure_date[:10] if len(departure_date) >= 10 else departure_date,
                    return_date=return_date[:10] if len(return_date) >= 10 else return_date,
                    price_eur=price,
                    transfers=num_stops,
                    airline=airline,
                    flight_number=flight_number,
                    deep_link=None,  # Would need booking API
                    found_at=datetime.utcnow(),
                    expires_at=None,
                    raw_payload=offer
                )
                deals.append(deal)

            except Exception as e:
                logger.warning(f"Failed to parse confirm offer: {e}")
                continue

        # Sort by price
        deals = sorted(deals, key=lambda d: (d.price_eur, d.transfers or 999))

        logger.info(f"Parsed {len(deals)} confirm offers")
        return deals

    # ========================================================================
    # COMPATIBILITY LAYER (Drop-in replacement for TravelpayoutsClient)
    # ========================================================================

    def search_deals(
        self,
        origin: str,
        destinations: List[str],
        start_date: datetime,
        end_date: datetime,
        min_days: int,
        max_days: int,
        max_results: int = 1000,
        progress_callback=None,
        cancel_flag: dict = None
    ) -> List[FlightDeal]:
        """
        Compatibility method matching TravelpayoutsClient.search_deals signature.

        IMPORTANT: This uses minimal API calls.
        - For specific destinations: 1 call per destination (max 3)
        - For "all" destinations: uses explore mode with popular destinations
        """
        logger.info(f"Search deals (compat): {origin} to {len(destinations)} destinations")

        if cancel_flag and cancel_flag.get('cancelled', False):
            return []

        # Check if this is a specific destination search or broad exploration
        is_specific_search = (
            destinations and
            len(destinations) <= 5 and
            not any(d.startswith('__ALL') for d in destinations)
        )

        all_deals = []

        if is_specific_search:
            # Direct search for specific destinations - more reliable
            all_deals = self._search_specific_destinations(
                origin=origin,
                destinations=destinations,
                start_date=start_date,
                end_date=end_date,
                min_days=min_days,
                max_days=max_days,
                progress_callback=progress_callback,
                cancel_flag=cancel_flag
            )
        else:
            # Broad exploration using popular destinations
            months = self._generate_months(start_date, end_date)
            total_months = len(months)

            for idx, month in enumerate(months):
                if cancel_flag and cancel_flag.get('cancelled', False):
                    break

                if progress_callback:
                    progress_callback(
                        idx,
                        total_months,
                        f"Searching {month}..."
                    )

                try:
                    month_deals = self.get_explore_deals(
                        origin=origin,
                        month=month,
                        currency=self.config.default_currency,
                        region_hint="Europe",
                        progress_callback=None
                    )

                    # Filter by trip duration
                    month_deals = [
                        d for d in month_deals
                        if min_days <= d.trip_duration <= max_days
                    ]

                    all_deals.extend(month_deals)

                except AmadeusAPIError as e:
                    logger.warning(f"Search for {month} failed: {e}")
                    if e.code == AmadeusErrorCode.AMADEUS_RATE_LIMITED:
                        break
                    continue

            if progress_callback:
                progress_callback(total_months, total_months, "Finalizing...")

        # Deduplicate and sort
        all_deals = self._deduplicate_deals(all_deals)
        all_deals = sorted(all_deals, key=lambda d: (
            d.price_eur,
            d.transfers if d.transfers is not None else 999,
            d.depart_date
        ))

        return all_deals[:max_results]

    def _search_specific_destinations(
        self,
        origin: str,
        destinations: List[str],
        start_date: datetime,
        end_date: datetime,
        min_days: int,
        max_days: int,
        progress_callback=None,
        cancel_flag: dict = None
    ) -> List[FlightDeal]:
        """
        Search for specific destinations with minimal API calls.
        Uses 1 call per destination, max 3 destinations.
        """
        all_deals = []

        # Limit to 3 destinations to respect call budget
        destinations = destinations[:3]

        # Pick a representative date in the middle of the range
        mid_date = start_date + (end_date - start_date) / 2
        departure_date = mid_date.strftime("%Y-%m-%d")

        # Calculate return date based on min/max days
        avg_days = (min_days + max_days) // 2
        return_date = (mid_date + timedelta(days=avg_days)).strftime("%Y-%m-%d")

        logger.info(f"Searching {len(destinations)} specific destinations: {destinations}")

        for idx, dest in enumerate(destinations):
            if cancel_flag and cancel_flag.get('cancelled', False):
                break

            if dest == origin:
                continue

            if progress_callback:
                progress_callback(
                    idx,
                    len(destinations),
                    f"Searching {origin} → {dest}..."
                )

            # Build cache key for this specific search
            cache_params = {
                "origin": origin,
                "destination": dest,
                "departure": departure_date,
                "return": return_date
            }
            cache_key = self._make_cache_key("specific_search", cache_params)

            # Check cache
            cached = self._get_explore_cached(cache_key)
            if cached is not None:
                logger.info(f"Cache hit for {origin}->{dest}")
                try:
                    for deal_dict in cached.get("deals", []):
                        deal = FlightDeal(**{k: v for k, v in deal_dict.items() if k != 'raw_payload'})
                        deal.raw_payload = deal_dict.get('raw_payload', {})
                        all_deals.append(deal)
                except Exception as e:
                    logger.warning(f"Failed to restore cached deals: {e}")
                continue

            try:
                response = self._make_request(
                    "POST",
                    "/v2/shopping/flight-offers",
                    json_body={
                        "currencyCode": self.config.default_currency,
                        "originDestinations": [
                            {
                                "id": "1",
                                "originLocationCode": origin,
                                "destinationLocationCode": dest,
                                "departureDateTimeRange": {
                                    "date": departure_date
                                }
                            },
                            {
                                "id": "2",
                                "originLocationCode": dest,
                                "destinationLocationCode": origin,
                                "departureDateTimeRange": {
                                    "date": return_date
                                }
                            }
                        ],
                        "travelers": [
                            {"id": "1", "travelerType": "ADULT"}
                        ],
                        "sources": ["GDS"],
                        "searchCriteria": {
                            "maxFlightOffers": 5
                        }
                    }
                )

                if response and "data" in response:
                    deals = self._parse_flight_offers(
                        response, origin, dest, departure_date, return_date
                    )
                    all_deals.extend(deals)

                    # Cache the results
                    if deals:
                        self._set_explore_cached(cache_key, {"deals": [d.__dict__ for d in deals]})

            except AmadeusAPIError as e:
                logger.warning(f"Search failed for {origin}->{dest}: {e}")
                if e.code == AmadeusErrorCode.AMADEUS_RATE_LIMITED:
                    logger.error("Rate limited - stopping search")
                    break
                continue

        if progress_callback:
            progress_callback(len(destinations), len(destinations), "Done")

        return all_deals

    def _generate_months(self, start_date: datetime, end_date: datetime) -> List[str]:
        """Generate list of month strings (YYYY-MM) between dates."""
        months = []
        current = start_date.replace(day=1)
        end = end_date.replace(day=1)

        while current <= end:
            months.append(current.strftime('%Y-%m'))
            if current.month == 12:
                current = current.replace(year=current.year + 1, month=1)
            else:
                current = current.replace(month=current.month + 1)

        return months

    def _deduplicate_deals(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        """Remove duplicate deals (same route and dates)."""
        seen = set()
        unique_deals = []

        for deal in deals:
            key = (
                deal.origin_iata,
                deal.dest_iata,
                deal.depart_date[:10],
                deal.return_date[:10] if deal.return_date else ""
            )
            if key not in seen:
                seen.add(key)
                unique_deals.append(deal)

        return unique_deals

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================

    def get_remaining_confirm_calls(self, client_id: str = "default") -> int:
        """Get the number of remaining confirm calls for a client."""
        return self.confirm_tracker.get_remaining(client_id)

    def get_request_stats(self) -> dict:
        """Get request statistics."""
        return {
            "total_requests": self._request_count,
            "confirm_tracker": {
                "max_calls": self.config.max_confirm_calls_per_session,
                "window_minutes": self.config.confirm_cap_window_minutes
            }
        }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

_client_instance: Optional[AmadeusFlightsClient] = None


def get_amadeus_client() -> Optional[AmadeusFlightsClient]:
    """Get or create the global Amadeus client instance."""
    global _client_instance

    if _client_instance is not None:
        return _client_instance

    # Load configuration from environment
    client_id = os.getenv("AMADEUS_CLIENT_ID", "")
    client_secret = os.getenv("AMADEUS_CLIENT_SECRET", "")

    if not client_id or not client_secret:
        logger.warning("Amadeus credentials not configured")
        return None

    base_url = os.getenv("AMADEUS_BASE_URL", "https://test.api.amadeus.com")
    mode = os.getenv("AMADEUS_MODE", "test")
    currency = os.getenv("DEFAULT_CURRENCY", "EUR")

    config = AmadeusConfig(
        client_id=client_id,
        client_secret=client_secret,
        base_url=base_url,
        mode=mode,
        default_currency=currency
    )

    _client_instance = AmadeusFlightsClient(config)
    return _client_instance


def create_amadeus_client(config: AmadeusConfig) -> AmadeusFlightsClient:
    """Create a new Amadeus client with specific configuration."""
    return AmadeusFlightsClient(config)

