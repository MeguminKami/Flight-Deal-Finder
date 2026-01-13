# ✈️ Flight Deal Finder

A **local, friendly flight-deal explorer** that helps you discover cheap round‑trip trips using **cached airfare data** (not live airline pricing). It’s designed to **inspire travel ideas** and surface “wow, that’s cheap” routes quickly — then you verify and book on your preferred site.

---

## What this app does

- **Search flight deals** from an origin airport to:
  - a **specific airport**
  - **all airports worldwide**
  - a **continent**
  - a **country**
- Filter trips by **date range** and **trip length** (min/max days).
- See results as clean “deal cards” with:
  - route, dates, trip duration
  - whether it’s **direct** or has stops
  - price (EUR)
- Open one‑click links to:
  - **Google Flights** (to validate and explore options)
  - **Booking** (quick destination + date handoff for planning)

---

## Important: prices are not real‑time

This app uses **cached search data** from the Travelpayouts/Aviasales ecosystem. That means:

- prices are typically **2–7 days old**
- some routes may have **no results** (because there wasn’t recent search activity)
- prices can change — **always confirm before buying**

Think of it like a **radar for travel inspiration**, not a live booking engine.

---

## Privacy

- Runs **100% locally** on your computer.
- The only external calls are to the **Travelpayouts API** to fetch flight price data.
- No tracking, no analytics.

---

## Getting started (simple)

### 1) Get an API token
You’ll need a **Travelpayouts token**.

### 2) Add the token
Set `TRAVELPAYOUTS_TOKEN` in *one* of these places:

1. **Environment variable**: `TRAVELPAYOUTS_TOKEN`
2. **User config file**: `config.env` inside your user config folder  
3. **Portable config**: `config.env` next to the app/executable  

A `config.env` file looks like this:

```
TRAVELPAYOUTS_TOKEN=YOUR_TOKEN_HERE
```

### 3) Run the app
If you’re running from source, the simplest launch is:

```
python app.py
```

The app opens in your browser (local server), usually on port **8080**.

---

## Using the app

1. Pick your **origin airport** (start typing to search).
2. Choose where you want to explore:
   - **Specific airport**
   - **Entire world**
   - **By continent**
   - **By country**
3. Select your **start and end dates**.
4. Choose **min/max trip length** in days.
5. Hit **Search Flights**.
6. Browse deals and open:
   - **Google Flights** to verify and compare
   - **Booking** for quick planning

Tip: If you start a big worldwide search and want to stop, hit **Stop Search**.

---

## Caching (why it feels fast)

To avoid re-fetching the same data repeatedly, the app stores recent API responses in a lightweight local cache:

- stored on disk using **SQLite**
- automatically expires after a short time (TTL)
- includes a “System Information” view where you can check cache stats and clear it

This keeps repeated searches snappy and reduces API calls.

---

## What’s inside (high level)

- **App UI**: A modern web interface with light/dark theme and pagination.
- **Flight data client**: Talks to the Travelpayouts API with rate limiting and retries.
- **Airport database**: Local `airports.json` file that powers dropdowns and flags.
- **Cache**: Local SQLite database to reuse responses safely.

---

## Troubleshooting

**“API token not configured”**  
Add `TRAVELPAYOUTS_TOKEN` using one of the methods above and restart the app.

**No results / empty routes**  
Try:
- expanding date range
- choosing a different destination or popular city
- searching a continent/country instead of a single airport

**Prices differ on booking sites**  
Normal — the data is cached. Use the Google Flights link to confirm.

---

## Disclaimer

This project helps you **discover** potential deals. It does not guarantee availability or pricing. Always confirm details on the airline/booking site before purchasing.

---

## Credits

Built with ❤️ using:
- **Python**
- **NiceGUI**
- **Travelpayouts / Aviasales cached flight data**
- Helpful planning links via **Google Flights** and **Booking**

---

Happy exploring — and may the cheap flights find you ✨
