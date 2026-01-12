# Flight Deal Finder 🛫

A local Python application to discover the cheapest round-trip flights using cached data from the Travelpayouts/Aviasales API. Perfect for travel inspiration and deal hunting!

## Features

✈️ **Smart Search**
- Search by specific airport, continent, or worldwide
- Flexible date ranges (search entire months)
- Trip duration filtering (min/max days)
- Multi-destination support

💰 **Best Prices**
- Finds the cheapest deals from cached search data
- Automatic deduplication
- Sorted by price, transfers, and date
- EUR currency display

🎨 **Modern UI**
- Clean monochrome design (black/white/grays)
- 1024×768 optimized layout
- Pagination (10 results per page)
- Real-time search progress
- Flag emojis for all airports

⚡ **Performance**
- Local SQLite caching (6-hour TTL)
- Rate limiting (2 req/sec)
- Retry logic with exponential backoff
- Concurrent search support

## What It Can and Cannot Do

### ✓ Can
- Find cheap deals from recent cached search data
- Inspire travel plans with real price data
- Filter by destination scope and trip length
- Show flight details (dates, transfers, airlines)

### ✗ Cannot
- Guarantee availability or final prices
- Book flights (you must verify on booking sites)
- Show real-time live prices
- Handle one-way trips (round-trip only)

## Requirements

- Python 3.11 or higher
- Travelpayouts API token ([get one here](https://www.travelpayouts.com/developers/api))

## Installation

1. **Clone or download this repository**

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Get your API token**
   - Visit [Travelpayouts Developers](https://www.travelpayouts.com/developers/api)
   - Sign up or log in
   - Navigate to API section
   - Copy your Data API token

4. **Configure your token**
   ```bash
   cp ..env .env
   ```
   Edit `.env` and replace `your_token_here` with your actual token:
   ```
   TRAVELPAYOUTS_TOKEN=your_actual_token
   ```

## Usage

### Run the application

```bash
python app.py
```

Or:

```bash
python -m app
```

The application will start on `http://localhost:8080`

### Search for flights

1. **Select origin airport** (e.g., 🇵🇹 LIS (Lisbon))

2. **Choose destination mode:**
   - **Specific Airport**: Search one destination (e.g., Barcelona)
   - **Continent**: Search all airports in a continent (e.g., Europe)
   - **World**: Search all airports worldwide

3. **Set date range:**
   - Start date: First day of your travel window
   - End date: Last day of your travel window
   - Tip: Use month-long ranges for best results

4. **Set trip duration:**
   - Min days: Minimum trip length (e.g., 3)
   - Max days: Maximum trip length (e.g., 5)

5. **Click "Search Flights"**
   - Progress indicator shows search status
   - Results appear sorted by price
   - Navigate with pagination controls

### Understanding results

Each flight deal shows:
- 🇵🇹 **LIS** → 🇪🇸 **BCN** (origin and destination with flags)
- **€123** (total price for round-trip)
- 🛫 **2026-03-15** (departure date)
- 🛬 **2026-03-18** (return date)
- ⏱️ **3 days** (trip duration)
- 🔀 **Direct** or **1 stop(s)** (transfers)

## Architecture

### Project Structure

```
flight-deal-finder/
├── app.py              # Main application (NiceGUI UI)
├── api_client.py       # Travelpayouts API client
├── models.py           # Data models (FlightDeal, Airport)
├── airports.py         # Airport database management
├── cache.py            # SQLite caching layer
├── airports.json       # Airport dataset (77 airports)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment template
├── .env               # Your API token (create this)
└── README.md          # This file
```

### How It Works

1. **API Integration**
   - Uses `/aviasales/v3/get_latest_prices` endpoint
   - Queries by month periods (YYYY-MM format)
   - Caches responses for 6 hours to reduce API calls
   - Rate limited to 2 requests/second (API limit: 300/minute)

2. **Search Strategy**
   - Breaks date range into month periods
   - For each destination × period combination:
     - Checks cache first
     - Fetches from API if needed
     - Filters by trip duration
   - Deduplicates results (same route + dates)
   - Sorts by: price → transfers → departure date

3. **Caching**
   - SQLite database (`flight_cache.db`)
   - Cache key: hash of (endpoint + parameters)
   - 6-hour time-to-live (data is 2-7 days old anyway)
   - Automatic cleanup of expired entries

4. **Rate Limiting**
   - 0.5s delay between requests (2 req/sec)
   - Exponential backoff on 429 errors
   - Max 3 retries per request
   - 10-second timeout per request

## API Limitations

The Travelpayouts Data API provides:
- **Cached data** from user searches (2-7 days old)
- **Not real-time** prices
- **Limited to popular routes** (depends on search volume)
- **Rate limits**: 300 requests/minute

If searching worldwide (100+ airports), expect:
- Longer search times (2-5 minutes)
- Many API calls (cached after first search)
- Some destinations may have no data

**Recommendation**: Start with continent searches, then drill down to specific airports.

## Troubleshooting

### "API token not configured"
- Check that `.env` file exists in the same directory as `app.py`
- Verify `TRAVELPAYOUTS_TOKEN` is set correctly
- Restart the application

### "No deals found"
- The API only has data for popular routes
- Try wider date ranges (full months work best)
- Try different destinations
- Check that your dates are in the future

### "Rate limit exceeded"
- The cache will prevent repeat requests
- If searching world/continents, be patient
- API allows 300 requests/minute (app limits to 2/sec)

### Search is slow (World/Continent)
- This is normal for large searches (50+ destinations)
- Results are cached for 6 hours
- Progress indicator shows status
- Consider using Specific Airport mode first

### Application won't start
- Verify Python 3.11+ is installed: `python --version`
- Check all dependencies are installed: `pip install -r requirements.txt`
- Check for port conflicts (default: 8080)

## Advanced Usage

### Clearing the cache

The cache file is `flight_cache.db`. To clear it:

```bash
rm flight_cache.db
```

It will be recreated on next search.

### Modifying airport dataset

Edit `airports.json` to add/remove airports. Required fields:
- `iata`: 3-letter IATA code
- `city`: City name
- `country`: Country name
- `country_code`: 2-letter ISO code (for flag emoji)
- `continent`: One of: Europe, North America, South America, Asia, Africa, Oceania
- `airport_name`: Full airport name (optional)

### Customizing cache TTL

In `cache.py`, modify the `ttl_hours` parameter:

```python
cache = APICache(ttl_hours=12)  # 12-hour cache
```

### Changing results per page

In `app.py`, modify:

```python
ITEMS_PER_PAGE = 20  # Show 20 results per page
```

## Known Limitations

1. **API Data Freshness**: Prices are 2-7 days old (API limitation)
2. **Round-trip Only**: One-way trips not supported (API constraint)
3. **Single Passenger**: Always searches for 1 adult
4. **EUR Only**: Currency is fixed to EUR for consistency
5. **No Booking**: This is a search tool only, not a booking engine
6. **Popular Routes**: Obscure routes may have no cached data

## Technical Notes

### Why SQLite for caching?
- Lightweight (no separate database server)
- ACID compliance (safe concurrent access)
- Fast lookups with indexed keys
- Portable (single file)

### Why NiceGUI?
- Python-first (no separate frontend build)
- Modern Quasar components
- Built-in dark theme
- Easy pagination and state management
- Runs locally with zero configuration

### Sorting logic
Results are sorted by:
1. **Price** (ascending) - cheapest first
2. **Transfers** (ascending) - prefer direct flights
3. **Departure date** (ascending) - earlier dates first

This ensures the best deals appear first while maintaining a logical order.

### API endpoint choice
We use `/aviasales/v3/get_latest_prices` because it:
- Supports month-based queries (period_type=month)
- Returns comprehensive flight details
- Has a 300 req/min rate limit (generous)
- Provides expires_at timestamps

Alternative endpoints like `/v2/prices/month-matrix` could work but have lower limits (60/min).

## Contributing

Contributions welcome! Areas for improvement:
- Add more airports to dataset
- Implement airline filtering
- Add export to CSV/JSON
- Create iOS/Android wrapper
- Add email alerts for price drops

## License

MIT License - Use freely for personal or commercial projects.

## Acknowledgments

- **Travelpayouts/Aviasales** for the API
- **NiceGUI** for the excellent Python UI framework
- **Airport data** curated from public sources

## Support

For API issues, contact [Travelpayouts Support](https://support.travelpayouts.com/)

For application bugs, open an issue in this repository.

---

**Happy flight hunting! ✈️🌍**
