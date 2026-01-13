"""
Tests for Amadeus Flights API Client

Tests cover:
- Token fetch + refresh
- Caching behavior
- Confirm call cap enforcement
- Handling 429 and 5xx errors
"""

import pytest
import time
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import json

# Import the module under test
from amadeus_client import (
    AmadeusFlightsClient,
    AmadeusConfig,
    AmadeusAPIError,
    AmadeusErrorCode,
    TokenManager,
    ConfirmCallTracker,
    is_european_destination,
    EUROPE_COUNTRY_CODES
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def config():
    """Create a test configuration."""
    return AmadeusConfig(
        client_id="test_client_id",
        client_secret="test_client_secret",
        base_url="https://test.api.amadeus.com",
        mode="test",
        default_currency="EUR",
        timeout=5,
        max_retries=2,
        global_rate_limit=0.1,  # Fast for tests
        max_confirm_calls_per_session=3,
        confirm_cap_window_minutes=10
    )


@pytest.fixture
def mock_airport_db():
    """Create a mock airport database."""
    with patch('amadeus_client.get_airport_db') as mock:
        db = Mock()

        # Mock airport objects
        opo_airport = Mock()
        opo_airport.iata = "OPO"
        opo_airport.city = "Porto"
        opo_airport.country_code = "PT"
        opo_airport.flag_emoji = "🇵🇹"

        lis_airport = Mock()
        lis_airport.iata = "LIS"
        lis_airport.city = "Lisbon"
        lis_airport.country_code = "PT"
        lis_airport.flag_emoji = "🇵🇹"

        cdg_airport = Mock()
        cdg_airport.iata = "CDG"
        cdg_airport.city = "Paris"
        cdg_airport.country_code = "FR"
        cdg_airport.flag_emoji = "🇫🇷"

        jfk_airport = Mock()
        jfk_airport.iata = "JFK"
        jfk_airport.city = "New York"
        jfk_airport.country_code = "US"
        jfk_airport.flag_emoji = "🇺🇸"

        def get_airport(iata):
            airports = {
                "OPO": opo_airport,
                "LIS": lis_airport,
                "CDG": cdg_airport,
                "JFK": jfk_airport
            }
            return airports.get(iata)

        db.get_airport = get_airport
        mock.return_value = db
        yield db


@pytest.fixture
def mock_cache():
    """Create a mock cache."""
    with patch('amadeus_client.get_cache') as mock:
        cache = Mock()
        cache_store = {}

        def get(endpoint, params):
            key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
            return cache_store.get(key)

        def set(endpoint, params, value):
            key = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
            cache_store[key] = value

        cache.get = get
        cache.set = set
        cache._store = cache_store  # For inspection in tests
        mock.return_value = cache
        yield cache


# ============================================================================
# TOKEN MANAGER TESTS
# ============================================================================

class TestTokenManager:
    """Tests for OAuth2 token management."""

    def test_fetch_new_token_success(self, config):
        """Test successful token fetch."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "test_token_123",
                "expires_in": 1799
            }
            mock_post.return_value = mock_response

            manager = TokenManager(config)
            token = manager.get_token()

            assert token == "test_token_123"
            mock_post.assert_called_once()

    def test_token_caching(self, config):
        """Test that token is cached and not refetched."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "cached_token",
                "expires_in": 1799
            }
            mock_post.return_value = mock_response

            manager = TokenManager(config)

            # First call fetches
            token1 = manager.get_token()
            # Second call uses cache
            token2 = manager.get_token()

            assert token1 == token2 == "cached_token"
            assert mock_post.call_count == 1  # Only one fetch

    def test_token_refresh_when_expired(self, config):
        """Test that token is refreshed when close to expiry."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "new_token",
                "expires_in": 1800  # 30 min expiry
            }
            mock_post.return_value = mock_response

            manager = TokenManager(config)

            # First call fetches token
            token1 = manager.get_token()
            assert mock_post.call_count == 1

            # Token is valid, should use cached
            token2 = manager.get_token()
            assert mock_post.call_count == 1  # Still 1, used cache

            # Force expiry to be within 60s buffer (triggers refresh)
            manager._expires_at = datetime.utcnow() + timedelta(seconds=30)
            token3 = manager.get_token()

            assert mock_post.call_count == 2  # Refreshed

    def test_auth_failure_raises_error(self, config):
        """Test that 401 raises appropriate error."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 401
            mock_response.text = "Invalid credentials"
            mock_post.return_value = mock_response

            manager = TokenManager(config)

            with pytest.raises(AmadeusAPIError) as exc_info:
                manager.get_token()

            assert exc_info.value.code == AmadeusErrorCode.AMADEUS_AUTH_FAILED

    def test_invalidate_clears_token(self, config):
        """Test that invalidate clears the cached token."""
        with patch('requests.post') as mock_post:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "access_token": "token_1",
                "expires_in": 1799
            }
            mock_post.return_value = mock_response

            manager = TokenManager(config)
            manager.get_token()

            # Invalidate
            manager.invalidate()

            # Change response for next fetch
            mock_response.json.return_value = {
                "access_token": "token_2",
                "expires_in": 1799
            }

            token = manager.get_token()
            assert token == "token_2"
            assert mock_post.call_count == 2


# ============================================================================
# CONFIRM CALL TRACKER TESTS
# ============================================================================

class TestConfirmCallTracker:
    """Tests for confirm call rate limiting."""

    def test_initial_state_allows_calls(self):
        """Test that new tracker allows calls."""
        tracker = ConfirmCallTracker(max_calls=3, window_minutes=10)
        can_call, remaining = tracker.can_make_call("client1")

        assert can_call is True
        assert remaining == 3

    def test_tracking_reduces_remaining(self):
        """Test that recording calls reduces remaining count."""
        tracker = ConfirmCallTracker(max_calls=3, window_minutes=10)

        tracker.record_call("client1")
        _, remaining = tracker.can_make_call("client1")
        assert remaining == 2

        tracker.record_call("client1")
        _, remaining = tracker.can_make_call("client1")
        assert remaining == 1

    def test_cap_enforcement(self):
        """Test that cap is enforced after max calls."""
        tracker = ConfirmCallTracker(max_calls=3, window_minutes=10)

        # Make max calls
        for _ in range(3):
            tracker.record_call("client1")

        can_call, remaining = tracker.can_make_call("client1")
        assert can_call is False
        assert remaining == 0

    def test_different_clients_tracked_separately(self):
        """Test that different clients have separate limits."""
        tracker = ConfirmCallTracker(max_calls=3, window_minutes=10)

        # Client 1 uses all calls
        for _ in range(3):
            tracker.record_call("client1")

        # Client 2 should still have calls
        can_call, remaining = tracker.can_make_call("client2")
        assert can_call is True
        assert remaining == 3

    def test_old_calls_expire(self):
        """Test that calls older than window are cleaned up."""
        tracker = ConfirmCallTracker(max_calls=3, window_minutes=1)

        # Record calls
        tracker.record_call("client1")
        tracker.record_call("client1")

        # Manually age the calls
        old_time = datetime.utcnow() - timedelta(minutes=2)
        tracker._calls["client1"] = [old_time, old_time]

        # Check - should cleanup and allow
        can_call, remaining = tracker.can_make_call("client1")
        assert can_call is True
        assert remaining == 3


# ============================================================================
# EUROPE FILTER TESTS
# ============================================================================

class TestEuropeFilter:
    """Tests for Europe region filtering."""

    def test_european_countries(self):
        """Test that European countries are detected."""
        european = ["PT", "ES", "FR", "DE", "IT", "GB", "NL", "BE"]
        for code in european:
            assert is_european_destination(code) is True

    def test_non_european_countries(self):
        """Test that non-European countries are rejected."""
        non_european = ["US", "BR", "CN", "JP", "AU", "ZA", "EG"]
        for code in non_european:
            assert is_european_destination(code) is False

    def test_case_insensitive(self):
        """Test that country codes are case insensitive."""
        assert is_european_destination("pt") is True
        assert is_european_destination("Pt") is True
        assert is_european_destination("PT") is True


# ============================================================================
# AMADEUS CLIENT TESTS
# ============================================================================

class TestAmadeusFlightsClient:
    """Tests for the main Amadeus client."""

    def test_rate_limiting(self, config, mock_airport_db, mock_cache):
        """Test that requests are rate limited."""
        with patch.object(TokenManager, 'get_token', return_value="test_token"):
            with patch('requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session
                mock_session.headers = {}

                # Mock API response
                mock_api_response = Mock()
                mock_api_response.status_code = 200
                mock_api_response.json.return_value = {"data": []}
                mock_session.get.return_value = mock_api_response

                client = AmadeusFlightsClient(config)
                client.token_manager._token = "test_token"
                client.token_manager._expires_at = datetime.utcnow() + timedelta(hours=1)

                start = time.time()

                # Make two requests
                client._make_request("GET", "/test1")
                client._make_request("GET", "/test2")

                elapsed = time.time() - start

                # Should have waited at least the rate limit
                assert elapsed >= config.global_rate_limit

    def test_429_handling_single_retry(self, config, mock_airport_db, mock_cache):
        """Test that 429 is retried once then fails."""
        with patch.object(TokenManager, 'get_token', return_value="test_token"):
            with patch('requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session
                mock_session.headers = {}

                # Always return 429
                mock_response = Mock()
                mock_response.status_code = 429
                mock_response.headers = {"Retry-After": "1"}
                mock_session.get.return_value = mock_response

                client = AmadeusFlightsClient(config)
                client.token_manager._token = "test_token"
                client.token_manager._expires_at = datetime.utcnow() + timedelta(hours=1)

                with pytest.raises(AmadeusAPIError) as exc_info:
                    client._make_request("GET", "/test")

                assert exc_info.value.code == AmadeusErrorCode.AMADEUS_RATE_LIMITED
                # Should have tried twice (initial + 1 retry)
                assert mock_session.get.call_count == 2

    def test_5xx_retry_with_backoff(self, config, mock_airport_db, mock_cache):
        """Test that 5xx errors are retried with backoff."""
        with patch.object(TokenManager, 'get_token', return_value="test_token"):
            with patch('requests.Session') as mock_session_class:
                mock_session = Mock()
                mock_session_class.return_value = mock_session
                mock_session.headers = {}

                # First two calls fail, third succeeds
                mock_fail = Mock()
                mock_fail.status_code = 503

                mock_success = Mock()
                mock_success.status_code = 200
                mock_success.json.return_value = {"data": "success"}

                mock_session.get.side_effect = [mock_fail, mock_fail, mock_success]

                client = AmadeusFlightsClient(config)
                client.token_manager._token = "test_token"
                client.token_manager._expires_at = datetime.utcnow() + timedelta(hours=1)

                result = client._make_request("GET", "/test")

                assert result == {"data": "success"}
                assert mock_session.get.call_count == 3

    def test_confirm_cap_enforcement(self, config, mock_airport_db, mock_cache):
        """Test that confirm calls are capped."""
        with patch.object(AmadeusFlightsClient, '_make_request') as mock_request:
            mock_request.return_value = {
                "data": [],
                "dictionaries": {}
            }

            client = AmadeusFlightsClient(config)

            # Make max allowed calls with different dates to avoid cache hits
            for i in range(config.max_confirm_calls_per_session):
                client.get_confirm_offers(
                    origin="OPO",
                    destination="CDG",
                    date=f"2026-05-0{i+1}",  # Different date each time
                    client_id="test_client"
                )

            # Next call should fail due to cap (not cache)
            with pytest.raises(AmadeusAPIError) as exc_info:
                client.get_confirm_offers(
                    origin="OPO",
                    destination="CDG",
                    date="2026-05-10",  # New date
                    client_id="test_client"
                )

            assert exc_info.value.code == AmadeusErrorCode.AMADEUS_RATE_LIMITED

    def test_explore_caching(self, config, mock_airport_db, mock_cache):
        """Test that explore results are cached."""
        with patch.object(AmadeusFlightsClient, '_make_request') as mock_request:
            mock_request.return_value = {
                "data": [
                    {
                        "destination": "CDG",
                        "price": {"total": "150.00"},
                        "departureDate": "2026-05-15",
                        "returnDate": "2026-05-22"
                    }
                ]
            }

            client = AmadeusFlightsClient(config)

            # First call
            deals1 = client.get_explore_deals(
                origin="OPO",
                month="2026-05",
                region_hint="Europe"
            )

            first_call_count = mock_request.call_count

            # Second call should use cache
            deals2 = client.get_explore_deals(
                origin="OPO",
                month="2026-05",
                region_hint="Europe"
            )

            # No additional API calls
            assert mock_request.call_count == first_call_count
            assert len(deals1) == len(deals2)

    def test_explore_region_filter(self, config, mock_airport_db, mock_cache):
        """Test that explore filters by region."""
        with patch.object(AmadeusFlightsClient, '_make_request') as mock_request:
            mock_request.return_value = {
                "data": [
                    {
                        "destination": "CDG",  # Europe
                        "price": {"total": "150.00"},
                        "departureDate": "2026-05-15"
                    },
                    {
                        "destination": "JFK",  # Not Europe
                        "price": {"total": "500.00"},
                        "departureDate": "2026-05-15"
                    }
                ]
            }

            client = AmadeusFlightsClient(config)

            deals = client.get_explore_deals(
                origin="OPO",
                month="2026-05",
                region_hint="Europe"
            )

            # Only CDG should be returned
            assert len(deals) == 1
            assert deals[0].dest_iata == "CDG"


# ============================================================================
# CALL BUDGET TESTS
# ============================================================================

class TestCallBudget:
    """Tests verifying call budget compliance."""

    def test_explore_call_budget(self, config, mock_airport_db, mock_cache):
        """Test that explore stays within 1-3 calls per month."""
        with patch.object(AmadeusFlightsClient, '_make_request') as mock_request:
            mock_request.return_value = {"data": []}

            client = AmadeusFlightsClient(config)

            # Request for one month
            client.get_explore_deals(
                origin="OPO",
                month="2026-05",
                region_hint="Europe"
            )

            # Should be <= 3 calls
            assert mock_request.call_count <= 3

    def test_search_deals_call_budget(self, config, mock_airport_db, mock_cache):
        """Test that search_deals (compat) uses minimal calls."""
        with patch.object(AmadeusFlightsClient, '_make_request') as mock_request:
            mock_request.return_value = {"data": []}

            client = AmadeusFlightsClient(config)

            # Search with many destinations (should NOT call per destination)
            destinations = ["CDG", "LIS", "BCN", "FCO", "AMS", "FRA", "MUC"]

            client.search_deals(
                origin="OPO",
                destinations=destinations,
                start_date=datetime(2026, 5, 1),
                end_date=datetime(2026, 5, 31),
                min_days=3,
                max_days=7
            )

            # Should NOT be destinations × days calls
            # Should be 1-3 calls total for the month
            assert mock_request.call_count <= 3


# ============================================================================
# EXAMPLE USAGE (Runnable demonstration)
# ============================================================================

def example_usage():
    """
    Example usage of the Amadeus client.

    This demonstrates the typical workflow:
    1. Explore deals for a month (1-3 API calls)
    2. Optionally confirm a specific deal (capped)
    """
    from amadeus_client import get_amadeus_client, AmadeusConfig, create_amadeus_client

    # Option 1: Use environment variables (recommended)
    client = get_amadeus_client()
    if client is None:
        print("Set AMADEUS_CLIENT_ID and AMADEUS_CLIENT_SECRET in .env")
        return

    # Option 2: Create with explicit config
    # config = AmadeusConfig(
    #     client_id="your_client_id",
    #     client_secret="your_client_secret"
    # )
    # client = create_amadeus_client(config)

    # EXPLORE: Get destination ideas (minimal API calls)
    print("=== Exploring deals for May 2026 ===")
    deals = client.get_explore_deals(
        origin="OPO",
        month="2026-05",
        region_hint="Europe"
    )

    print(f"Found {len(deals)} destination ideas")
    for deal in deals[:5]:
        print(f"  {deal.dest_city}: €{deal.price_eur:.0f} ({deal.depart_date})")

    # Check remaining confirm calls
    remaining = client.get_remaining_confirm_calls()
    print(f"\nRemaining confirm calls: {remaining}")

    # CONFIRM: Get bookable offers for a specific route (capped)
    if deals and remaining > 0:
        first_deal = deals[0]
        print(f"\n=== Confirming offers for {first_deal.dest_city} ===")

        offers = client.get_confirm_offers(
            origin="OPO",
            destination=first_deal.dest_iata,
            date=first_deal.depart_date[:10]
        )

        print(f"Found {len(offers)} bookable offers")
        for offer in offers[:3]:
            print(f"  {offer.airline}: €{offer.price_eur:.0f} ({offer.transfers} stops)")

    # Show stats
    stats = client.get_request_stats()
    print(f"\nTotal API requests made: {stats['total_requests']}")


# Run example if executed directly
if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])

    # Or run example
    # example_usage()

