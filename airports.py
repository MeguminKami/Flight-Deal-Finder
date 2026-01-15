"""Airport database loader.

This module provides `get_airport_db()`, which is used across the project
(app UI + providers) to:
- lookup airports by IATA code
- populate dropdowns (airports/continents/countries)

Data source: `airports.json` in the project root or in the PyInstaller bundle.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from models import Airport


def _resource_path(filename: str) -> Path:
    """Return a path to a data file for both dev and PyInstaller."""
    import sys

    if hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / filename


@dataclass(frozen=True)
class _AirportRecord:
    iata: str
    city: str
    country: str
    country_code: str
    continent: str
    airport_name: str = ""
    commercial_flights: bool = True

    def to_model(self) -> Airport:
        return Airport(
            iata=self.iata,
            city=self.city,
            country=self.country,
            country_code=self.country_code,
            continent=self.continent,
            airport_name=self.airport_name or "",
        )


class AirportDB:
    """In-memory airport database loaded from airports.json."""

    def __init__(self, airports: Iterable[_AirportRecord]):
        self._by_iata: Dict[str, _AirportRecord] = {}
        for a in airports:
            code = (a.iata or "").strip().upper()
            if len(code) != 3:
                continue
            # keep first occurrence
            self._by_iata.setdefault(code, a)

    def get_airport(self, iata: str) -> Optional[Airport]:
        code = (iata or "").strip().upper()
        rec = self._by_iata.get(code)
        return rec.to_model() if rec else None

    def get_all_airports(self) -> List[Airport]:
        return [rec.to_model() for rec in self._by_iata.values()]

    def get_airports_for_dropdown(self) -> List[Tuple[str, str]]:
        """Return (display_name, iata) pairs for UI dropdowns."""

        airports = [rec.to_model() for rec in self._by_iata.values() if rec.commercial_flights]
        airports.sort(key=lambda a: (a.country, a.city, a.iata))
        return [(a.display_name, a.iata) for a in airports]

    def get_continents_for_dropdown(self) -> List[Tuple[str, str]]:
        """Return (display_name, continent_code) pairs.

        The current UI treats continent_code as the value key and display_name as the label.
        """

        continents = sorted({rec.continent for rec in self._by_iata.values() if rec.continent})
        return [(c, c) for c in continents]

    def get_countries_for_dropdown(self) -> List[Tuple[str, str]]:
        """Return (display_name, country_name) pairs.

        The current UI expects a list where item[0] is the label and item[1] is the value.
        """

        countries = sorted({rec.country for rec in self._by_iata.values() if rec.country})
        return [(c, c) for c in countries]

    def get_airports_by_continent(self, continent: str) -> List[Airport]:
        continent = (continent or "").strip()
        out = [rec.to_model() for rec in self._by_iata.values() if rec.continent == continent and rec.commercial_flights]
        out.sort(key=lambda a: (a.country, a.city, a.iata))
        return out

    def get_airports_by_country(self, country: str) -> List[Airport]:
        country = (country or "").strip()
        out = [rec.to_model() for rec in self._by_iata.values() if rec.country == country and rec.commercial_flights]
        out.sort(key=lambda a: (a.city, a.iata))
        return out


_db_lock = threading.Lock()
_db_singleton: Optional[AirportDB] = None


def _load_airports_json(path: Path) -> List[_AirportRecord]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("airports.json must contain a JSON list")

    airports: List[_AirportRecord] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        airports.append(
            _AirportRecord(
                iata=str(item.get("iata") or "").strip().upper(),
                city=str(item.get("city") or "").strip(),
                country=str(item.get("country") or "").strip(),
                country_code=str(item.get("country_code") or "").strip().upper(),
                continent=str(item.get("continent") or "").strip(),
                airport_name=str(item.get("airport_name") or "").strip(),
                commercial_flights=bool(item.get("commercial_flights", True)),
            )
        )
    return airports


def get_airport_db() -> AirportDB:
    """Return a cached AirportDB instance (loads airports.json once)."""

    global _db_singleton
    if _db_singleton is not None:
        return _db_singleton

    with _db_lock:
        if _db_singleton is not None:
            return _db_singleton

        path = _resource_path("airports.json")
        if not path.exists():
            # fallback: try current working directory
            cwd_path = Path.cwd() / "airports.json"
            if cwd_path.exists():
                path = cwd_path

        if not path.exists():
            raise FileNotFoundError(f"airports.json not found at {path}")

        _db_singleton = AirportDB(_load_airports_json(path))
        return _db_singleton

