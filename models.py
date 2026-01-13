"""
Data models for the flight deal finder application.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class FlightDeal:
    """Represents a flight deal with all relevant information."""
    origin_iata: str
    dest_iata: str
    origin_city: str
    dest_city: str
    origin_flag: str
    dest_flag: str
    depart_date: str
    return_date: str
    price_eur: float
    transfers: Optional[int] = None
    airline: Optional[str] = None
    flight_number: Optional[str] = None
    deep_link: Optional[str] = None
    found_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    raw_payload: dict = field(default_factory=dict)

    @property
    def trip_duration(self) -> int:
        """Calculate trip duration in days."""
        try:
            depart = datetime.fromisoformat(self.depart_date.replace('Z', '+00:00'))
            return_dt = datetime.fromisoformat(self.return_date.replace('Z', '+00:00'))
            return (return_dt - depart).days
        except Exception:
            return 0

    @property
    def formatted_price(self) -> str:
        """Format price as EUR with proper formatting."""
        return f"€{self.price_eur:,.0f}"

    def __repr__(self) -> str:
        return (
            f"FlightDeal({self.origin_iata}→{self.dest_iata}, "
            f"{self.depart_date[:10]} to {self.return_date[:10]}, "
            f"{self.formatted_price})"
        )


@dataclass
class Airport:
    """Represents an airport with location information."""
    iata: str
    city: str
    country: str
    country_code: str
    continent: str
    airport_name: str = ""

    @property
    def flag_emoji(self) -> str:
        """Convert country code to flag emoji."""
        if not self.country_code or len(self.country_code) != 2:
            return "🌍"
        try:
            code_points = [ord(char) + 127397 for char in self.country_code.upper()]
            return chr(code_points[0]) + chr(code_points[1])
        except:
            return "🌍"

    @property
    def display_name(self) -> str:
        """Format airport for display: 🇵🇹 LIS (Lisbon)"""
        return f"{self.flag_emoji} {self.iata} ({self.city})"

    def __repr__(self) -> str:
        return f"Airport({self.display_name})"
