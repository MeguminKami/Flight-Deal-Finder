<div align="center">

# ✈️ Flight Deal Finder

<img src="https://img.shields.io/badge/Platform-Windows%20%7C%20macOS-blue?style=for-the-badge&logo=windows&logoColor=white" alt="Platform"/>
<img src="https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python"/>
<img src="https://img.shields.io/badge/License-MIT-purple?style=for-the-badge" alt="License"/>
<img src="https://img.shields.io/github/v/release/MeguminKami/Flight-Deal-Finder?style=for-the-badge&color=7c5cff" alt="Release"/>

<br/><br/>

**Discover amazing flight deals to your dream destinations**

*A beautiful, privacy-focused desktop app that helps you find cheap round-trip flights worldwide*

<br/>

[<img src="https://img.shields.io/badge/Download%20for%20Windows-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Download Windows" height="40"/>](https://github.com/MeguminKami/Flight-Deal-Finder/releases/latest)
&nbsp;&nbsp;
[<img src="https://img.shields.io/badge/Download%20for%20macOS-000000?style=for-the-badge&logo=apple&logoColor=white" alt="Download macOS" height="40"/>](https://github.com/MeguminKami/Flight-Deal-Finder/releases/latest)

<br/>

---

</div>

## 📋 Quick Navigation

- [Download & Install](#-download--install)
- [Features](#-features)
- [How It Works](#-how-it-works)
- [Screenshots](#-screenshots)
- [Configuration](#-configuration)
- [For Developers](#-for-developers)
- [FAQ](#-faq)

---

## 📥 Download & Install

<table>
<tr>
<td align="center" width="50%">

### 🪟 Windows

**[Download Installer](https://github.com/MeguminKami/Flight-Deal-Finder/releases/latest)**

`FlightDealFinder-win-x64-vX.X.exe`

1. Download the `.exe` installer
2. Run and follow the setup wizard
3. Launch from Start Menu

**Requirements:** Windows 10 or later (64-bit)

</td>
<td align="center" width="50%">

### 🍎 macOS

**[Download App](https://github.com/MeguminKami/Flight-Deal-Finder/releases/latest)**

`FlightDealFinder-mac-arm64-vX.X.zip`

1. Download and unzip
2. Drag to Applications folder
3. Right-click → Open (first launch only)

**Requirements:** macOS 11+ (Apple Silicon M1/M2/M3)

</td>
</tr>
</table>

---

## ✨ Features

<table>
<tr>
<td width="50%">

### 🌍 Search Anywhere
- **Entire World** - Find deals to any destination
- **By Continent** - Focus on Europe, Asia, Americas...
- **By Country** - All airports in a specific country
- **Specific Route** - Airport to airport search

</td>
<td width="50%">

### 📅 Flexible Dates
- **Date Range** - Set your travel window
- **Trip Duration** - Min/max days for your vacation
- **Smart Validation** - Prevents invalid date combinations

</td>
</tr>
<tr>
<td width="50%">

### 💰 Compare & Book
- **Direct Links** - Open results in Google Flights
- **Hotel Integration** - Check Booking.com for stays
- **Price Display** - Clear pricing in EUR
- **Stop Info** - See direct vs connecting flights

</td>
<td width="50%">

### 🎨 Beautiful Experience
- **Dark/Light Mode** - Easy on the eyes, any time
- **Modern UI** - Clean, intuitive interface
- **Fast Search** - Results in seconds
- **Pagination** - Browse through many deals easily

</td>
</tr>
</table>

### 🔒 100% Private

> **Runs entirely on your computer.** No tracking, no analytics, no data collection. Your travel plans stay yours.

---

## 🔄 How It Works

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────┐
│  Your Search │ ──► │  Travelpayouts  │ ──► │   Results    │
│   Criteria   │     │   Price Cache   │     │   & Deals    │
└──────────────┘     └─────────────────┘     └──────────────┘
```

1. **Set your search** - Origin, destination, dates, trip length
2. **API fetches data** - From Travelpayouts cached flight prices
3. **Results display** - Sorted deals with booking links
4. **Book directly** - Click through to Google Flights or Booking.com

> **Note:** Prices are from cached search data (2-7 days old). Always verify final prices on booking sites before purchasing.

---

## 📸 Screenshots

<div align="center">

| Dark Mode | Light Mode |
|:---------:|:----------:|
| *Modern dark interface* | *Clean light theme* |

</div>

---

## ⚙️ Configuration

### API Setup

The app uses **Travelpayouts API** for flight data. To use your own API key:

1. Get a free API key at [Travelpayouts](https://www.travelpayouts.com/)
2. Create `config.env` file next to the app:

```env
TRAVELPAYOUTS_TOKEN=your_token_here
```

### Config File Locations

| Platform | Location |
|----------|----------|
| **Windows** | Next to `.exe` or `%LOCALAPPDATA%\FlightDealFinder\` |
| **macOS** | Next to the app bundle |
| **Development** | Project root folder |

---

## 👩‍💻 For Developers

<details>
<summary><strong>Click to expand source code instructions</strong></summary>

<br/>

### Prerequisites

- Python 3.12+
- Git

### Setup

```bash
# Clone the repository
git clone https://github.com/MeguminKami/Flight-Deal-Finder.git
cd Flight-Deal-Finder

# Create virtual environment
python -m venv .venv

# Activate (Windows)
.venv\Scripts\activate

# Activate (macOS/Linux)
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Running Locally

```bash
python app.py
```

The app opens in your browser at `http://localhost:8080`

### Project Structure

```
FlightSearchV2/
├── app.py              # Main application & UI
├── airports.py         # Airport database handling
├── airports.json       # Airport data (IATA codes, cities, countries)
├── api_travelpayouts.py # Travelpayouts API client
├── api_amadeus.py      # Amadeus API client (optional)
├── cache.py            # Local SQLite caching
├── config.py           # Configuration management
├── models.py           # Data models (FlightDeal)
├── requirements.txt    # Python dependencies
├── static/
│   └── app_theme.css   # UI theming (dark/light)
├── scripts/            # Build scripts for releases
└── .github/workflows/  # CI/CD for automated releases
```

### Tech Stack

| Component | Technology |
|-----------|------------|
| **UI Framework** | [NiceGUI](https://nicegui.io/) |
| **HTTP Client** | Requests |
| **Database** | SQLite (caching) |
| **Packaging** | PyInstaller + Inno Setup (Windows) |
| **CI/CD** | GitHub Actions |

### Building Releases

Windows and macOS releases are built automatically via GitHub Actions when you push a version tag:

```bash
git tag v1.0
git push origin v1.0
```

</details>

---

## ❓ FAQ

<details>
<summary><strong>What is this app?</strong></summary>
<br/>
A local flight deal finder that searches cached price data from Travelpayouts/Aviasales to inspire your travel plans. It helps you discover cheap round-trip flights to destinations worldwide.
</details>

<details>
<summary><strong>Are prices real-time?</strong></summary>
<br/>
No. Prices are 2-7 days old (cached search data from other users). Always verify final prices on booking sites like Google Flights before purchasing.
</details>

<details>
<summary><strong>Why are some routes empty?</strong></summary>
<br/>
The API only has data for popular routes with recent search activity. Try different dates, a broader destination (like "Entire World" or a continent), or alternative airports.
</details>

<details>
<summary><strong>Is my data private?</strong></summary>
<br/>
Yes! The app runs 100% locally on your computer. It only calls the Travelpayouts API for flight data. There is no tracking, analytics, or data collection.
</details>

<details>
<summary><strong>Can I use my own API key?</strong></summary>
<br/>
Yes! Create a `config.env` file with your Travelpayouts token. See the <a href="#-configuration">Configuration</a> section for details.
</details>

---

<div align="center">

### 💜 Built with love for travelers

<br/>

**[Report a Bug](https://github.com/MeguminKami/Flight-Deal-Finder/issues)** · **[Request Feature](https://github.com/MeguminKami/Flight-Deal-Finder/issues)** · **[Releases](https://github.com/MeguminKami/Flight-Deal-Finder/releases)**

<br/>

<sub>Made with Python, NiceGUI, and a passion for finding great deals</sub>

</div>
