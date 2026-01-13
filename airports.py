"""
Airport data management module.
"""

import json
from pathlib import Path
from typing import List, Optional, Dict
from models import Airport

class AirportDatabase:
    """Manages the airport dataset."""

    CONTINENT_EMOJIS = {
        "Europe": "🌍",
        "North America": "🌎",
        "South America": "🌎",
        "Asia": "🌏",
        "Africa": "🌍",
        "Oceania": "🌏",
    }

    def __init__(self, data_file: str = "airports.json"):
        """Load airport data from JSON file."""
        self.data_file = Path(data_file)
        self.airports: List[Airport] = []
        self._airport_map: Dict[str, Airport] = {}
        self._load_data()

    def _load_data(self):
        """Load and parse airport data."""
        if not self.data_file.exists():
            raise FileNotFoundError(f"Airport data file not found: {self.data_file}")

        with open(self.data_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for item in data:
            airport = Airport(
                iata=item['iata'],
                city=item['city'],
                country=item['country'],
                country_code=item['country_code'],
                continent=item['continent'],
                airport_name=item.get('airport_name', '')
            )
            self.airports.append(airport)
            self._airport_map[airport.iata] = airport

    def get_airport(self, iata: str) -> Optional[Airport]:
        """Get airport by IATA code."""
        return self._airport_map.get(iata.upper())

    def get_airports_by_continent(self, continent: str) -> List[Airport]:
        """Get all airports in a continent."""
        return [a for a in self.airports if a.continent == continent]

    def get_airports_by_country(self, country: str) -> List[Airport]:
        """Get all airports in a country."""
        return [a for a in self.airports if a.country == country]

    def get_countries(self) -> List[tuple]:
        """Get list of all unique countries with their country codes."""
        countries = {}
        for a in self.airports:
            if a.country not in countries:
                countries[a.country] = a.country_code
        return sorted(countries.items(), key=lambda x: x[0])

    def get_countries_for_dropdown(self) -> List[tuple]:
        """Get countries formatted for dropdown with flags."""
        countries = self.get_countries()
        result = []
        for country_name, country_code in countries:
            # Generate flag emoji from country code
            if country_code and len(country_code) == 2:
                try:
                    code_points = [ord(char) + 127397 for char in country_code.upper()]
                    flag = chr(code_points[0]) + chr(code_points[1])
                except:
                    flag = "🌍"
            else:
                flag = "🌍"
            result.append((f"{flag} {country_name}", country_name))
        return result

    def get_all_airports(self) -> List[Airport]:
        """Get all airports."""
        return self.airports.copy()

    def get_continents(self) -> List[str]:
        """Get list of all continents."""
        return sorted(set(a.continent for a in self.airports))

    def get_continent_display_name(self, continent: str) -> str:
        """Get display name for continent with emoji."""
        emoji = self.CONTINENT_EMOJIS.get(continent, "🌍")
        return f"{emoji} {continent}"

    def get_airports_for_dropdown(self) -> List[tuple]:
        """Get airports formatted for dropdown (display_name, iata)."""
        return sorted(
            [(a.display_name, a.iata) for a in self.airports],
            key=lambda x: x[0]
        )

    def get_continents_for_dropdown(self) -> List[tuple]:
        """Get continents formatted for dropdown."""
        continents = self.get_continents()
        return [
            (self.get_continent_display_name(c), c)
            for c in continents
        ]

    @staticmethod
    def get_world_option() -> tuple:
        """Get the 'World' option for dropdown."""
        return ("🌍 ALL (World)", "ALL")


# Global instance
_db_instance = None

def get_airport_db() -> AirportDatabase:
    """Get or create the global airport database instance."""
    global _db_instance
    if _db_instance is None:
        _db_instance = AirportDatabase()
    return _db_instance
