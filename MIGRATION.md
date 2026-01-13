# Amadeus Integration Migration Guide

## Overview

This project has been updated to use the **Amadeus API** as the primary flight data source, with Travelpayouts as a fallback. The integration follows a 2-step approach designed to minimize API calls while providing useful flight inspiration data.

## Architecture

### Two-Step Approach

1. **EXPLORE** (Cheap + Cached + Minimal Requests)
   - Uses Amadeus Flight Inspiration Search API
   - Returns multiple destinations from a single origin
   - 1-3 API calls for an entire month query
   - Results cached for 6-24 hours
   - Prices are *indicative* (marked with `*` in UI)

2. **CONFIRM** (Optional + Capped)
   - Uses Amadeus Flight Offers Search API
   - Gets real bookable prices for a specific route/date
   - Hard-capped at 3 calls per 10-minute window per client
   - Results cached for 5-15 minutes
   - Returns actual airline prices with stop information

## Call Budget

| Operation | Amadeus Calls | Notes |
|-----------|---------------|-------|
| Explore "May 2026" | 1-3 | Samples 3 dates across month |
| Confirm 1 destination | 1 | Cached briefly |
| Typical user flow | 4-6 total | Explore + 3 confirms max |

### Worst-Case Scenario
- User searches May 2026: **3 calls** (explore)
- User clicks 3 destinations: **3 calls** (confirm, capped)
- User refreshes page: **0 calls** (cached)
- **Total: 6 calls maximum** for aggressive usage

## Configuration

### Environment Variables (.env)

```env
# Amadeus API (Primary) - Get from https://developers.amadeus.com/
AMADEUS_CLIENT_ID=your_client_id_here
AMADEUS_CLIENT_SECRET=your_client_secret_here
AMADEUS_BASE_URL=https://test.api.amadeus.com
AMADEUS_MODE=test
DEFAULT_CURRENCY=EUR

# Travelpayouts API (Fallback)
TRAVELPAYOUTS_TOKEN=your_token_here
```

### Getting Amadeus Credentials

1. Go to https://developers.amadeus.com/
2. Create a free account
3. Create a new app in the dashboard
4. Copy the API Key (client_id) and API Secret (client_secret)
5. Start with TEST environment (free, rate-limited)

### Test vs Production

| Feature | Test | Production |
|---------|------|------------|
| Base URL | test.api.amadeus.com | api.amadeus.com |
| Data | Limited/simulated | Real airline data |
| Rate Limits | Stricter | Higher quotas |
| Cost | Free | Pay per call |

## File Structure

```
FlightSearchV2/
├── amadeus_client.py      # NEW: Amadeus API integration
├── test_amadeus_client.py # NEW: Unit tests
├── api_client.py          # Travelpayouts (unchanged, fallback)
├── app.py                 # Updated: uses Amadeus by default
├── cache.py               # Unchanged
├── models.py              # Unchanged
├── airports.py            # Unchanged
├── airports.json          # Unchanged
├── .env                   # Updated: new Amadeus vars
├── requirements.txt       # Updated: added pytest
└── MIGRATION.md           # This file
```

## API Mapping

### Travelpayouts → Amadeus

| Travelpayouts | Amadeus | Notes |
|---------------|---------|-------|
| `/get_latest_prices` | `/v1/shopping/flight-destinations` | Explore mode |
| N/A | `/v2/shopping/flight-offers` | Confirm mode (new feature) |

### Response Compatibility

The `AmadeusFlightsClient.search_deals()` method maintains the same signature as `TravelpayoutsClient.search_deals()`, returning `List[FlightDeal]`. This ensures the UI works without changes.

Key differences in data:
- **Explore results**: May not have `transfers` count or airline info
- **Confirm results**: Full details including airline, stops, and real prices

## Error Handling

### Error Codes

| Code | Description | Action |
|------|-------------|--------|
| `AMADEUS_AUTH_FAILED` | Invalid credentials | Check .env configuration |
| `AMADEUS_RATE_LIMITED` | Too many requests | Wait or use cached data |
| `AMADEUS_QUOTA_EXCEEDED` | Monthly quota hit | Upgrade plan or wait |
| `AMADEUS_BAD_REQUEST` | Invalid parameters | Check input validation |
| `AMADEUS_UPSTREAM_ERROR` | Amadeus server error | Retry with backoff |
| `AMADEUS_TIMEOUT` | Request timeout | Retry or check network |

### Rate Limit Protection

1. **Global rate limit**: 1 request/second (configurable)
2. **Retry on 5xx**: Max 2 retries with exponential backoff
3. **429 handling**: 1 retry after delay, then fail fast
4. **Confirm cap**: Max 3 per 10 minutes per client

## Running Tests

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest test_amadeus_client.py -v

# Run specific test class
pytest test_amadeus_client.py::TestTokenManager -v

# Run with coverage
pytest test_amadeus_client.py --cov=amadeus_client
```

## Running the App

```bash
# Install dependencies
pip install -r requirements.txt

# Configure .env (copy from above)

# Run the app
python app.py
```

The app will start at http://localhost:8080

## UI Changes

1. **Search Results**: Indicative prices marked with `*`
2. **"Check Real Prices" Button**: Appears on each deal card
3. **Remaining Calls Counter**: Shows how many confirm calls left
4. **Confirm Dialog**: Shows bookable offers with airline info
5. **FAQ Updated**: Explains explore vs confirm modes

## Troubleshooting

### "No API configured" error
- Check that `.env` file exists and has valid credentials
- Ensure `python-dotenv` is installed

### "Rate limited" errors
- Wait 1-2 minutes before trying again
- Check if you've exceeded test environment limits
- Consider upgrading to production Amadeus plan

### Empty search results
- Flight Inspiration API may not have data for all routes
- Try different origin airports (major hubs work best)
- Try different months (popular travel periods have more data)

### Confirm shows different prices
- This is expected! Explore prices are indicative
- Confirm prices are real-time from airlines
- Always verify on booking site before purchasing

## Support

For Amadeus API issues:
- Documentation: https://developers.amadeus.com/self-service
- Community: https://community.amadeus.com/

For this application:
- Create an issue in the repository

