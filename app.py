"""
Flight Deal Finder - Main Application
A local tool to discover cheap round-trip flights using Travelpayouts cached data.
"""
import os
import base64
from datetime import datetime, timedelta
from typing import List, Optional
from dotenv import load_dotenv
from nicegui import ui, app as nicegui_app
from api_client import TravelpayoutsClient, APIConfig
from airports import get_airport_db
from models import FlightDeal
import asyncio
import json
from pathlib import Path

load_dotenv()

API_TOKEN = os.getenv('TRAVELPAYOUTS_TOKEN', '')

ITEMS_PER_PAGE = 10

airport_db = get_airport_db()
api_client = None


def _static_dir() -> Path:
    return Path(__file__).resolve().parent / 'static'


def _add_theme_assets() -> None:
    """Serve and include the custom theme."""
    static_dir = _static_dir()
    if static_dir.exists():
        nicegui_app.add_static_files('/static', str(static_dir))
        ui.add_head_html('<link rel="stylesheet" href="/static/theme.css">')
    ui.add_head_html('<meta name="viewport" content="width=device-width, initial-scale=1">')


def _svg_banner_data_uri(title: str, subtitle: str) -> str:
    """Create a small inline SVG banner with aviation theme colors."""
    svg = f"""
    <svg xmlns="http://www.w3.org/2000/svg" width="1200" height="420" viewBox="0 0 1200 420">
      <defs>
        <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stop-color="#1E88E5" stop-opacity="0.95"/>
          <stop offset="55%" stop-color="#00ACC1" stop-opacity="0.85"/>
          <stop offset="100%" stop-color="#0F172A" stop-opacity="1"/>
        </linearGradient>
        <filter id="blur" x="-20%" y="-20%" width="140%" height="140%">
          <feGaussianBlur stdDeviation="30"/>
        </filter>
      </defs>

      <rect width="1200" height="420" rx="16" fill="#1E293B"/>
      <rect x="0" y="0" width="1200" height="420" rx="16" fill="url(#g)" opacity="0.3"/>
      <circle cx="220" cy="120" r="140" fill="#1E88E5" opacity="0.2" filter="url(#blur)"/>
      <circle cx="980" cy="320" r="180" fill="#00ACC1" opacity="0.15" filter="url(#blur)"/>
      <circle cx="600" cy="200" r="80" fill="#FFB300" opacity="0.1" filter="url(#blur)"/>

      <text x="64" y="170" font-family="system-ui, -apple-system, Segoe UI, Roboto, Arial" font-size="54" font-weight="800" fill="#F1F5F9">
        {title}
      </text>
      <text x="64" y="230" font-family="system-ui, -apple-system, Segoe UI, Roboto, Arial" font-size="26" font-weight="600" fill="#F1F5F9" opacity="0.9">
        {subtitle}
      </text>

      <text x="64" y="320" font-family="ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace"
            font-size="18" font-weight="600" fill="#94A3B8" opacity="0.9">
        Cached prices · Verify on booking sites · Great for inspiration
      </text>
    </svg>
    """.strip()

    b64 = base64.b64encode(svg.encode('utf-8')).decode('ascii')
    return f"data:image/svg+xml;base64,{b64}"


def _copy_to_clipboard(text: str) -> None:
    payload = json.dumps(text)
    ui.run_javascript(f"navigator.clipboard.writeText({payload});")


class FlightSearchApp:
    """Main application controller."""

    def __init__(self):
        self.results: List[FlightDeal] = []
        self.current_page = 1

        # Search defaults
        self.origin_iata = 'LIS'
        self.dest_mode = 'specific'
        self.dest_value = 'BCN'
        self.start_date = None
        self.end_date = None
        self.min_days = 3
        self.max_days = 5

        # Client-side filters (do not affect API requests)
        self.max_price: Optional[float] = None
        self.max_stops: Optional[int] = None
        self.sort_mode = 'Best price'

        self.is_searching = False

        # UI refs
        self.origin_select = None
        self.dest_mode_radio = None
        self.dest_airport_select = None
        self.dest_continent_select = None
        self.start_date_input = None
        self.end_date_input = None
        self.min_days_input = None
        self.max_days_input = None
        self.search_button = None
        self.loading_label = None
        self.results_container = None
        self.pagination_container = None
        self.filters_container = None

    def create_ui(self):
        """Build the complete UI."""
        _add_theme_assets()

        ui.html('<div class="bgGlow"></div>', sanitize=False)

        with ui.column().classes('wrap'):
            self._create_topbar()
            self._create_hero()
            self._create_search_form()
            self._create_results_section()
            self._create_footer()

    def _create_topbar(self):
        """Top navigation / quick actions."""
        with ui.row().classes('topbar'):
            with ui.row().classes('brand'):
                ui.element('div').classes('avatar')
                with ui.column().style('gap:2px'):
                    ui.label('Flight Deal Finder').classes('name')
                    ui.label('Cheap round-trips from cached searches').classes('headline')

            with ui.row().style('gap:8px'):
                info_dialog = self._build_info_dialog()
                ui.button(icon='info', on_click=info_dialog.open).classes('iconBtn').props('flat')

                cache_dialog = self._build_cache_dialog()
                ui.button(icon='database', on_click=cache_dialog.open).classes('iconBtn').props('flat')

    def _create_hero(self):
        """Hero + quick stats panel."""
        airports_count = len(airport_db.get_all_airports())

        with ui.row().classes('hero'):
            # Left column
            with ui.column():
                ui.label('Find flight deals — fast.').classes('h1')
                ui.label(
                    "Search destinations by airport, continent, or worldwide. "
                    "Prices come from Travelpayouts/Aviasales cached data, so always verify before booking."
                ).classes('lead')

                with ui.row().classes('btnRow'):
                    ui.button('Search deals', icon='search', on_click=lambda: ui.run_javascript("window.scrollTo({top: 560, behavior: 'smooth'})")).classes('btn primary')
                    ui.button('How this works', icon='help', on_click=self._build_info_dialog().open).classes('btn ghost')

                ui.element('div').classes('hr')

                ui.label('Quick tips').classes('sectionTitle')
                ui.html(
                    '<div class="toastHint">Try <b>Continent</b> first for inspiration → then switch to a specific airport.</div>',
                    sanitize=False
                )
                ui.html(
                    '<div class="toastHint" style="margin-top:8px">Wider date ranges (full months) usually return more cached data.</div>',
                    sanitize=False
                )

            # Right column: stats card
            with ui.element('div').classes('heroCard'):
                with ui.element('div').classes('heroCardTop'):
                    ui.element('div').classes('dot dot1')
                    ui.element('div').classes('dot dot2')
                    ui.element('div').classes('dot dot3')
                    ui.label('v1.1 · local').classes('mono')
                with ui.element('div').classes('heroCardBody'):
                    with ui.row().style('align-items:baseline; gap:8px'):
                        ui.label(str(airports_count)).classes('mono').style('font-size:2rem; font-weight:900')
                        ui.label('airports in dataset').classes('muted')
                    ui.label('Includes flags & city names').classes('muted').style('margin-top:8px')

                    ui.element('div').classes('hr')

                    with ui.row().style('justify-content:space-between;'):
                        ui.label('Cache TTL').classes('muted')
                        ui.label('6h').classes('mono')
                    with ui.row().style('justify-content:space-between;'):
                        ui.label('Currency').classes('muted')
                        ui.label('EUR').classes('mono')
                    with ui.row().style('justify-content:space-between;'):
                        ui.label('Mode').classes('muted')
                        ui.label('Round-trip').classes('mono')

    def _create_search_form(self):
        """Create search controls."""
        airports = airport_db.get_airports_for_dropdown()
        continents = airport_db.get_continents_for_dropdown()

        with ui.element('div').classes('panel').style('margin-top: 24px;'):
            ui.label('Search').classes('sectionTitle').style('margin-top:0')

            with ui.row().style('gap:16px; flex-wrap:wrap;'):
                with ui.column().style('flex: 1; min-width: 256px;'):
                    self.origin_select = ui.select(
                        label='Origin airport',
                        options={iata: name for name, iata in airports},
                        value=self.origin_iata,
                        on_change=lambda e: setattr(self, 'origin_iata', e.value)
                    ).props('dense outlined')

                with ui.column().style('flex: 1; min-width: 256px;'):
                    self.dest_mode_radio = ui.radio(
                        ['Specific Airport', 'Continent', 'World'],
                        value='Specific Airport',
                        on_change=self._on_dest_mode_change
                    ).props('inline')

                    self.dest_airport_select = ui.select(
                        label='Destination airport',
                        options={iata: name for name, iata in airports},
                        value=self.dest_value
                    ).props('dense outlined').style('margin-top:8px')

                    self.dest_continent_select = ui.select(
                        label='Destination continent',
                        options={cont: name for name, cont in continents},
                        value='Europe'
                    ).props('dense outlined').style('margin-top:8px; display:none')

            with ui.row().style('gap:16px; flex-wrap:wrap; margin-top:16px;'):
                with ui.column().style('flex: 1; min-width: 224px;'):
                    default_start = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                    self.start_date_input = ui.input(
                        label='Start date',
                        value=default_start,
                        on_change=lambda e: setattr(self, 'start_date', e.value)
                    ).props('type=date dense outlined')
                    self.start_date = default_start

                with ui.column().style('flex: 1; min-width: 224px;'):
                    default_end = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                    self.end_date_input = ui.input(
                        label='End date',
                        value=default_end,
                        on_change=lambda e: setattr(self, 'end_date', e.value)
                    ).props('type=date dense outlined')
                    self.end_date = default_end

                with ui.column().style('flex: 0.5; min-width: 160px;'):
                    self.min_days_input = ui.number(
                        label='Min days',
                        value=self.min_days,
                        min=1,
                        max=30,
                        on_change=lambda e: setattr(self, 'min_days', int(e.value or 1))
                    ).props('dense outlined')

                with ui.column().style('flex: 0.5; min-width: 160px;'):
                    self.max_days_input = ui.number(
                        label='Max days',
                        value=self.max_days,
                        min=1,
                        max=30,
                        on_change=lambda e: setattr(self, 'max_days', int(e.value or 1))
                    ).props('dense outlined')

            with ui.row().style('align-items:center; justify-content:space-between; margin-top:16px; flex-wrap:wrap; gap:16px'):
                self.search_button = ui.button(
                    'Search flights',
                    on_click=self._on_search_click,
                    icon='search'
                ).classes('btn primary')

                self.loading_label = ui.label('').classes('toastHint').style('display:none')

                ui.label('Tip: results are cached, so repeat searches are much faster.').classes('muted')

    def _on_dest_mode_change(self, e):
        """Handle destination mode change."""
        mode_map = {
            'Specific Airport': 'specific',
            'Continent': 'continent',
            'World': 'world'
        }
        self.dest_mode = mode_map.get(e.value, 'specific')

        if self.dest_mode == 'specific':
            self.dest_airport_select.style('display:block')
            self.dest_continent_select.style('display:none')
        elif self.dest_mode == 'continent':
            self.dest_airport_select.style('display:none')
            self.dest_continent_select.style('display:block')
        else:
            self.dest_airport_select.style('display:none')
            self.dest_continent_select.style('display:none')

    async def _on_search_click(self):
        """Handle search button click."""
        if self.is_searching:
            return

        if not API_TOKEN:
            ui.notify('API token not configured. Please set TRAVELPAYOUTS_TOKEN in .env', type='negative')
            return

        global api_client
        if api_client is None:
            api_client = TravelpayoutsClient(APIConfig(token=API_TOKEN))

        self.is_searching = True
        self.search_button.set_enabled(False)
        self.loading_label.style('display:inline-block')
        self.loading_label.set_text('Searching…')

        try:
            destinations = self._get_destination_list()

            start = datetime.fromisoformat(self.start_date)
            end = datetime.fromisoformat(self.end_date)

            if self.min_days > self.max_days:
                ui.notify('Min days cannot be greater than max days', type='warning')
                return

            def progress_callback(current, total, message):
                self.loading_label.set_text(f'{message} ({current}/{total})')

            self.results = await asyncio.to_thread(
                api_client.search_deals,
                origin=self.origin_iata,
                destinations=destinations,
                start_date=start,
                end_date=end,
                min_days=self.min_days,
                max_days=self.max_days,
                progress_callback=progress_callback
            )

            self.current_page = 1
            self._render_results()

            if not self.results:
                ui.notify('No deals found. Try different criteria.', type='info')
            else:
                ui.notify(f'Found {len(self.results)} deals!', type='positive')

        except Exception as e:
            ui.notify(f'Search failed: {str(e)}', type='negative')

        finally:
            self.is_searching = False
            self.search_button.set_enabled(True)
            self.loading_label.style('display:none')

    def _get_destination_list(self) -> List[str]:
        """Get list of destination IATA codes based on mode."""
        if self.dest_mode == 'specific':
            return [self.dest_airport_select.value]
        if self.dest_mode == 'continent':
            continent = self.dest_continent_select.value
            airports = airport_db.get_airports_by_continent(continent)
            return [a.iata for a in airports]
        return [a.iata for a in airport_db.get_all_airports()]

    def _create_results_section(self):
        """Create results display area."""
        ui.label('Results').classes('sectionTitle')

        with ui.element('div').classes('panel'):
            with ui.row().style('align-items:flex-end; justify-content:space-between; gap:16px; flex-wrap:wrap'):
                with ui.row().style('gap:16px; flex-wrap:wrap'):
                    ui.label('Filters (optional)').classes('muted')
                    ui.number(
                        label='Max price (€)',
                        value=None,
                        min=0,
                        step=10,
                        on_change=lambda e: self._set_and_rerender('max_price', float(e.value) if e.value else None)
                    ).props('dense outlined').style('width: 176px')

                    ui.select(
                        label='Max stops',
                        options={
                            'any': 'Any',
                            '0': 'Direct only',
                            '1': 'Up to 1 stop',
                            '2': 'Up to 2 stops',
                        },
                        value='any',
                        on_change=lambda e: self._set_and_rerender('max_stops', None if e.value == 'any' else int(e.value))
                    ).props('dense outlined').style('width: 176px')

                ui.select(
                    label='Sort',
                    options=['Best price', 'Soonest trip', 'Direct first'],
                    value=self.sort_mode,
                    on_change=lambda e: self._set_and_rerender('sort_mode', e.value)
                ).props('dense outlined').style('width: 224px')

            ui.element('div').classes('hr')

            self.results_container = ui.column().classes('dealList')
            self.pagination_container = ui.row().style('justify-content:center; gap:8px; margin-top:16px')

            self._render_results()

    def _set_and_rerender(self, attr: str, value):
        setattr(self, attr, value)
        self.current_page = 1
        self._render_results()

    def _apply_client_filters(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        filtered = deals
        if self.max_price is not None:
            filtered = [d for d in filtered if d.price_eur <= self.max_price]
        if self.max_stops is not None:
            filtered = [d for d in filtered if (d.transfers if d.transfers is not None else 999) <= int(self.max_stops)]
        return filtered

    def _apply_sort(self, deals: List[FlightDeal]) -> List[FlightDeal]:
        if self.sort_mode == 'Soonest trip':
            return sorted(deals, key=lambda d: (d.depart_date_ymd, d.price_eur))
        if self.sort_mode == 'Direct first':
            return sorted(deals, key=lambda d: ((d.transfers if d.transfers is not None else 999), d.price_eur, d.depart_date_ymd))
        return sorted(deals, key=lambda d: (d.price_eur, (d.transfers if d.transfers is not None else 999), d.depart_date_ymd))

    def _render_results(self):
        """Render search results with pagination."""
        if self.results_container is None:
            return

        self.results_container.clear()
        self.pagination_container.clear()

        if not self.results:
            with self.results_container:
                ui.label('No results yet. Run a search above ✈️').classes('muted').style('text-align:center; padding: 26px 0')
            return

        deals = self._apply_sort(self._apply_client_filters(self.results))

        if not deals:
            with self.results_container:
                ui.label('No deals match your filters.').classes('muted').style('text-align:center; padding: 26px 0')
                ui.button('Clear filters', icon='filter_alt_off', on_click=self._clear_filters).classes('btn small')
            return

        total_pages = (len(deals) - 1) // ITEMS_PER_PAGE + 1
        start_idx = (self.current_page - 1) * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(deals))
        page_results = deals[start_idx:end_idx]

        with self.results_container:
            ui.label(f'Showing {len(deals)} deals · Page {self.current_page} of {total_pages}').classes('muted')

            for deal in page_results:
                self._render_deal_card(deal)

        self._render_pagination(total_pages)

    def _clear_filters(self):
        self.max_price = None
        self.max_stops = None
        self.sort_mode = 'Best price'
        self._render_results()

    def _render_deal_card(self, deal: FlightDeal):
        """Render a single flight deal card."""
        dialog = self._build_deal_dialog(deal)

        with ui.card().classes('dealCard'):
            with ui.row().style('justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap'):
                with ui.row().style('align-items:center; gap:8px'):
                    ui.label(f'{deal.origin_flag} {deal.origin_iata}').style('font-size:1.125rem; font-weight:800')
                    ui.icon('arrow_forward').classes('routeArrow')
                    ui.label(f'{deal.dest_flag} {deal.dest_iata}').style('font-size:1.125rem; font-weight:800')
                    ui.label(f'· {deal.origin_city} → {deal.dest_city}').classes('muted')

                ui.label(deal.formatted_price).classes('priceTag')

            with ui.row().classes('gridMeta'):
                with ui.row().classes('metaItem'):
                    ui.icon('flight_takeoff', size='18px').classes('muted')
                    ui.label(deal.depart_date_ymd)
                with ui.row().classes('metaItem'):
                    ui.icon('flight_land', size='18px').classes('muted')
                    ui.label(deal.return_date_ymd)
                with ui.row().classes('metaItem'):
                    ui.icon('schedule', size='18px').classes('muted')
                    ui.label(f'{deal.trip_duration} days')
                if deal.transfers is not None:
                    with ui.row().classes('metaItem'):
                        ui.icon('connecting_airports', size='18px').classes('muted')
                        ui.label('Direct' if deal.transfers == 0 else f'{deal.transfers} stop(s)')
                if deal.airline:
                    with ui.row().classes('metaItem'):
                        ui.icon('apartment', size='18px').classes('muted')
                        ui.label(f'Airline: {deal.airline}')

            with ui.row().style('justify-content:space-between; align-items:center; gap:16px; flex-wrap:wrap; margin-top:16px'):
                ui.label('Tap for details & links').classes('muted')

                with ui.row().style('gap:8px; flex-wrap:wrap'):
                    ui.button('Details', icon='open_in_new', on_click=dialog.open).classes('btn small')
                    ui.button('Google Flights', icon='travel_explore', on_click=lambda u=deal.google_flights_url(): ui.open(u, new_tab=True)).classes('btn small')
                    if deal.booking_url:
                        ui.button('Book', icon='shopping_bag', on_click=lambda u=deal.booking_url: ui.open(u, new_tab=True)).classes('btn primary small')

    def _render_pagination(self, total_pages: int):
        """Render pagination controls."""
        with self.pagination_container:
            if total_pages <= 1:
                return

            ui.button(icon='chevron_left', on_click=lambda: self._change_page(self.current_page - 1)).classes('btn small').set_enabled(self.current_page > 1)
            # compact page display
            start_page = max(1, self.current_page - 2)
            end_page = min(total_pages, self.current_page + 2)

            for page_num in range(start_page, end_page + 1):
                classes = 'btn primary small' if page_num == self.current_page else 'btn small'
                ui.button(str(page_num), on_click=lambda p=page_num: self._change_page(p)).classes(classes)

            ui.button(icon='chevron_right', on_click=lambda: self._change_page(self.current_page + 1)).classes('btn small').set_enabled(self.current_page < total_pages)

    def _change_page(self, new_page: int):
        deals = self._apply_sort(self._apply_client_filters(self.results))
        total_pages = (len(deals) - 1) // ITEMS_PER_PAGE + 1
        if 1 <= new_page <= total_pages:
            self.current_page = new_page
            self._render_results()

    def _build_deal_dialog(self, deal: FlightDeal):
        """Build a detail dialog for a deal (extra communication & links)."""
        banner = _svg_banner_data_uri(
            f"{deal.origin_iata} → {deal.dest_iata}",
            f"{deal.origin_city} to {deal.dest_city} · {deal.trip_duration} days · {deal.formatted_price}"
        )

        google_url = deal.google_flights_url()
        booking_url = deal.booking_url

        with ui.dialog() as dialog:
            with ui.card().style('max-width: 896px; width: min(896px, 92vw);'):
                ui.image(banner).classes('bannerImg')

                with ui.column().style('padding:16px; gap:16px'):
                    ui.label(deal.trip_summary).style('font-size:1.25rem; font-weight:900')
                    ui.label(f"Depart: {deal.depart_date_ymd} · Return: {deal.return_date_ymd}").classes('muted')

                    badges = []
                    badges.append(f"{deal.trip_duration} days")
                    if deal.transfers is not None:
                        badges.append('Direct' if deal.transfers == 0 else f'{deal.transfers} stop(s)')
                    if deal.airline:
                        badges.append(f"Airline {deal.airline}")

                    with ui.row().style('gap:8px; flex-wrap:wrap'):
                        for b in badges:
                            ui.label(b).classes('badge')

                    ui.element('div').classes('hr')

                    ui.label('Links').style('font-weight:800')
                    ui.label('Use Google Flights to explore options, then verify the price on the booking site.').classes('muted')

                    with ui.row().style('gap:8px; flex-wrap:wrap'):
                        ui.button('Open Google Flights', icon='travel_explore', on_click=lambda: ui.open(google_url, new_tab=True)).classes('btn primary')
                        if booking_url:
                            ui.button('Open booking site', icon='shopping_bag', on_click=lambda: ui.open(booking_url, new_tab=True)).classes('btn secondary')

                        ui.button('Copy links', icon='content_copy', on_click=lambda: _copy_to_clipboard(
                            f"{deal.trip_summary}\nGoogle Flights: {google_url}\nBooking: {booking_url or 'N/A'}"
                        )).classes('btn small')

                    ui.element('div').classes('hr')

                    ui.label('Notes').style('font-weight:800')
                    ui.html(
                        "<ul class='muted' style='margin:0; padding-left:16px'>"
                        "<li>Prices come from cached searches (can be 2–7 days old).</li>"
                        "<li>Availability changes quickly — treat this as inspiration.</li>"
                        "<li>For the best experience, try a wider date range (month-long).</li>"
                        "</ul>",
                        sanitize=False
                    )

                with ui.row().style('justify-content:flex-end; padding:0 16px 16px'):
                    ui.button('Close', icon='close', on_click=dialog.close).classes('btn')

        return dialog

    def _build_info_dialog(self):
        """Info dialog (explain purpose + limitations)."""
        with ui.dialog() as dialog:
            with ui.card().style('max-width: 768px; width: min(768px, 92vw);'):
                with ui.column().style('padding:16px; gap:16px'):
                    ui.label('How Flight Deal Finder works').style('font-size:1.25rem; font-weight:900')
                    ui.label(
                        "This app queries Travelpayouts/Aviasales cached price data. "
                        "It's great for discovering destinations and rough price signals — "
                        "but it isn't live inventory."
                    ).classes('muted')

                    ui.element('div').classes('hr')

                    ui.label('What it can do').style('font-weight:800')
                    ui.html(
                        "<ul class='muted' style='margin:0; padding-left:16px'>"
                        "<li>Find cheap round-trip deals across many destinations.</li>"
                        "<li>Filter by trip duration (min/max days).</li>"
                        "<li>Provide one-click links to Google Flights and a booking page.</li>"
                        "</ul>",
                        sanitize=False
                    )

                    ui.label('What it cannot do').style('font-weight:800')
                    ui.html(
                        "<ul class='muted' style='margin:0; padding-left:16px'>"
                        "<li>Guarantee availability or final prices.</li>"
                        "<li>Book flights — always verify on the booking site.</li>"
                        "<li>Provide real-time price alerts (yet).</li>"
                        "</ul>",
                        sanitize=False
                    )

                with ui.row().style('justify-content:flex-end; padding:0 16px 16px'):
                    ui.button('Close', icon='close', on_click=dialog.close).classes('btn')
        return dialog

    def _build_cache_dialog(self):
        """Cache stats dialog (extra transparency)."""
        from cache import get_cache
        cache = get_cache()
        stats = cache.get_stats()

        with ui.dialog() as dialog:
            with ui.card().style('max-width: 672px; width: min(672px, 92vw);'):
                with ui.column().style('padding:16px; gap:16px'):
                    ui.label('Cache').style('font-size:1.25rem; font-weight:900')
                    ui.label('The app stores API responses locally to speed up repeat searches and reduce rate limits.').classes('muted')

                    with ui.row().style('gap:8px; flex-wrap:wrap'):
                        ui.label(f"Entries: {stats.get('total_entries', 0)}").classes('badge')
                        ui.label(f"Valid: {stats.get('valid_entries', 0)}").classes('badge success')
                        ui.label(f"Expired: {stats.get('expired_entries', 0)}").classes('badge warning')

                    with ui.row().style('gap:8px; flex-wrap:wrap'):
                        ui.button('Clear expired', icon='auto_delete', on_click=lambda: self._clear_expired(cache)).classes('btn small')
                        ui.button('Clear all', icon='delete_sweep', on_click=lambda: self._clear_all_cache(cache)).classes('btn small')

                with ui.row().style('justify-content:flex-end; padding:0 16px 16px'):
                    ui.button('Close', icon='close', on_click=dialog.close).classes('btn')
        return dialog

    def _clear_expired(self, cache):
        deleted = cache.clear_expired()
        ui.notify(f"Cleared {deleted} expired entries", type='info')

    def _clear_all_cache(self, cache):
        cache.clear_all()
        ui.notify("Cache cleared", type='warning')

    def _create_footer(self):
        with ui.element('div').style('margin-top:48px'):
            ui.label('Reminder').classes('sectionTitle')
            ui.html(
                "<div class='toastHint'>Prices are cached and may be outdated. "
                "Always confirm details and price on Google Flights / booking sites.</div>",
                sanitize=False
            )


@ui.page('/')
def index():
    """Main page route."""
    app_instance = FlightSearchApp()
    app_instance.create_ui()


if __name__ in {'__main__', '__mp_main__'}:
    if not API_TOKEN:
        print('WARNING: TRAVELPAYOUTS_TOKEN not set in .env file')
        print('Create a .env file (or copy .env.example) and add your API token.')

    ui.run(
        title='Flight Deal Finder',
        favicon='✈️',
        dark=True,
        reload=False,
        port=8080
    )
