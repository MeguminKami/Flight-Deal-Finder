'''
Flight Deal Finder - Main Application (Modernized)
A local tool to discover cheap round-trip flights using Travelpayouts cached data.
'''

import os
import sys
from pathlib import Path

# Fix for PyInstaller no-console mode: stdout/stderr are None which breaks uvicorn logging
# This must be done before importing uvicorn/nicegui
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

from datetime import datetime, timedelta
from typing import List, Optional
from urllib.parse import urlencode
from dotenv import load_dotenv
from nicegui import ui, app as nicegui_app
from api_client import TravelpayoutsClient, APIConfig
from airports import get_airport_db
from models import FlightDeal
from cache import get_cache
import asyncio


def get_resource_path(relative_path: str) -> Path:
    """Get the absolute path to a resource, works for dev and PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        # Running as bundled executable
        base_path = Path(sys._MEIPASS)
    else:
        # Running in development
        base_path = Path(__file__).parent
    return base_path / relative_path


load_dotenv()

API_TOKEN = os.getenv('TRAVELPAYOUTS_TOKEN', '')
ITEMS_PER_PAGE = 10

airport_db = get_airport_db()
api_client = None

class FlightSearchApp:
    '''Main application controller with modernized UI.'''

    def __init__(self):
        self.results: List[FlightDeal] = []
        self.current_page = 1
        self.origin_iata = 'LIS'
        self.dest_mode = 'specific'
        self.dest_value = 'BCN'
        self.start_date = None
        self.end_date = None
        self.min_days = 3
        self.max_days = 5
        self.is_searching = False
        self.theme_dark = True
        self.search_performed = False  # Track if search was done
        self.cancel_flag = {'cancelled': False}  # Flag to cancel ongoing search

        # UI components
        self.origin_select = None
        self.dest_mode_radio = None
        self.dest_airport_select = None
        self.dest_continent_select = None
        self.start_date_input = None
        self.end_date_input = None
        self.min_days_input = None
        self.max_days_input = None
        self.search_button = None
        self.results_container = None
        self.pagination_container = None
        self.progress_container = None
        self.theme_toggle_icon = None
        self.results_section = None  # Container for results section
        self.eta_label = None  # ETA label during search
        self.dest_airport_label = None  # Label for destination dropdown

    def create_ui(self):
        '''Build the complete modernized UI.'''
        # Add theme CSS
        ui.add_head_html('<link rel="stylesheet" href="/static/app_theme.css">')

        # Add JavaScript for theme persistence
        ui.add_head_html('''
        <script>
        // Load theme preference
        const savedTheme = localStorage.getItem('theme') || 'dark';
        if (savedTheme === 'light') {
            document.body.classList.add('light');
        }

        window.toggleTheme = function() {
            document.body.classList.toggle('light');
            const isDark = !document.body.classList.contains('light');
            localStorage.setItem('theme', isDark ? 'dark' : 'light');
            return isDark;
        }
        </script>
        ''')

        with ui.column().style('width: 100%; max-width: 1200px; margin: 0 auto; padding: 20px; position: relative; z-index: 1;'):
            self._create_header()
            ui.space()
            self._create_search_form()
            ui.space()
            self._create_results_section()
            ui.space()
            self._create_faq_section()
            ui.space()
            self._create_footer()

    def _create_header(self):
        '''Create modern header with branding and theme toggle.'''
        with ui.row().classes('theme-card').style(
            'width: 100%; padding: 24px 32px; align-items: center; justify-content: space-between;'
        ):
            # Left: Brand
            with ui.row().style('align-items: center; gap: 16px;'):
                ui.label('✈️').style('font-size: 2rem;')
                ui.label('Flight Deal Finder').style(
                    'font-size: 1.8rem; font-weight: 700; color: var(--text);'
                ).classes('text-gradient')

            # Right: Cache info + Theme toggle
            with ui.row().style('gap: 12px; align-items: center;'):
                # Cache info button
                cache_btn = ui.icon('info', size='1.5rem').style('color: var(--text);')
                cache_btn.on('click', self._show_cache_info_dialog)
                cache_btn.classes('theme-toggle')

                self.theme_toggle_icon = ui.icon('dark_mode', size='1.5rem').style('color: var(--text);')
                self.theme_toggle_icon.on('click', self._toggle_theme)
                self.theme_toggle_icon.classes('theme-toggle')

    def _show_cache_info_dialog(self):
        '''Show cache information dialog.'''
        cache = get_cache()
        stats = cache.get_stats()
        total_airports = len(airport_db.get_all_airports())

        with ui.dialog() as dialog, ui.card().style('min-width: 400px; max-width: 500px; padding: 24px;'):
            ui.label('📊 System Information').style('font-size: 1.5rem; font-weight: 600; margin-bottom: 16px;')

            with ui.column().style('gap: 16px; width: 100%;'):
                # Cache stats
                ui.label('Cache Statistics').style('font-weight: 600; font-size: 1.1rem;')
                with ui.column().style('gap: 8px; padding-left: 16px;'):
                    ui.label(f"Total cached entries: {stats['total_entries']}").classes('text-muted')
                    ui.label(f"Valid entries: {stats['valid_entries']}").classes('text-muted')
                    ui.label(f"Expired entries: {stats['expired_entries']}").classes('text-muted')
                    ui.label(f"Cache TTL: 6 hours").classes('text-muted')

                # Airport stats
                ui.label('Airport Data').style('font-weight: 600; font-size: 1.1rem; margin-top: 8px;')
                with ui.column().style('gap: 8px; padding-left: 16px;'):
                    ui.label(f"Loaded airports: {total_airports}").classes('text-muted')
                    ui.label("Data source: airports.json (local file)").classes('text-muted')

                # Data age note
                ui.label('Data Freshness').style('font-weight: 600; font-size: 1.1rem; margin-top: 8px;')
                with ui.column().style('gap: 8px; padding-left: 16px;'):
                    ui.label("API prices: 2-7 days old (from Travelpayouts cache)").classes('text-muted')
                    ui.label("Always verify prices on booking sites").classes('text-muted')

                # Actions
                with ui.row().style('gap: 12px; margin-top: 16px; justify-content: flex-end;'):
                    def clear_cache():
                        cache.clear_all()
                        ui.notify('Cache cleared successfully!', type='positive')
                        dialog.close()

                    ui.button('Clear Cache', icon='delete', on_click=clear_cache).classes('btn-secondary')
                    ui.button('Close', on_click=dialog.close).classes('btn-primary')

        dialog.open()

    def _toggle_theme(self):
        '''Toggle between light and dark theme.'''
        ui.run_javascript('window.toggleTheme()')
        # Update icon
        if self.theme_dark:
            self.theme_toggle_icon.props('name=light_mode')
        else:
            self.theme_toggle_icon.props('name=dark_mode')
        self.theme_dark = not self.theme_dark

    def _create_search_form(self):
        '''Create modernized search controls.'''
        with ui.column().classes('theme-card').style('width: 100%; padding: 32px; gap: 24px;'):
            ui.label('🔍 Search Flights').style('font-size: 1.3rem; font-weight: 600; color: var(--text);')

            # Route section - 3 dropdowns
            with ui.row().style('width: 100%; gap: 20px; flex-wrap: wrap;'):
                # Origin Airport
                with ui.column().style('flex: 1; min-width: 250px;'):
                    ui.label('🛫 Origin Airport').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    airports = airport_db.get_airports_for_dropdown()
                    self.origin_select = ui.select(
                        options={iata: self._format_airport_display(iata) for name, iata in airports},
                        value=self.origin_iata,
                        on_change=lambda e: setattr(self, 'origin_iata', e.value),
                        with_input=True
                    ).classes('theme-select input-left-padding').style('width: 100%;')

                # Part of the World dropdown
                with ui.column().style('flex: 1; min-width: 250px;'):
                    ui.label('🌍 Part of the World').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    continents = airport_db.get_continents_for_dropdown()
                    dest_options = {'all': '🌎 Entire World', 'specific': '🎯 Specific Airport', 'country': '🏳️ Search by Country'}
                    dest_options.update({cont: f"🌐 {name}" for name, cont in continents})
                    self.dest_continent_select = ui.select(
                        options=dest_options,
                        value='specific',
                        on_change=self._on_dest_mode_change
                    ).classes('theme-select input-left-padding').style('width: 100%;')

                # Destination Airport (shown only when 'specific' is selected)
                with ui.column().style('flex: 1; min-width: 250px;'):
                    self.dest_airport_label = ui.label('🛬 Destination Airport').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    self.dest_airport_select = ui.select(
                        options={iata: self._format_airport_display(iata) for name, iata in airports},
                        value=self.dest_value,
                        on_change=self._on_dest_airport_change,
                        with_input=True
                    ).classes('theme-select input-left-padding').style('width: 100%;')

            # Dates section
            with ui.row().style('width: 100%; gap: 20px; flex-wrap: wrap;'):
                with ui.column().style('flex: 1; min-width: 200px;'):
                    ui.label('📅 Start Date').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    default_start = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
                    self.start_date_input = ui.input(value=default_start).classes('theme-input date-input').props('type=date').style('width: 100%;')
                    self.start_date = default_start
                    self.start_date_input.on('change', lambda e: setattr(self, 'start_date', e.sender.value))

                with ui.column().style('flex: 1; min-width: 200px;'):
                    ui.label('📅 End Date').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    default_end = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')
                    self.end_date_input = ui.input(value=default_end).classes('theme-input date-input').props('type=date').style('width: 100%;')
                    self.end_date = default_end
                    self.end_date_input.on('change', lambda e: setattr(self, 'end_date', e.sender.value))

                with ui.column().style('flex: 0.5; min-width: 120px;'):
                    ui.label('⏱️ Min Days').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    self.min_days_input = ui.number(value=self.min_days, min=1, max=30).classes('theme-input number-input').style('width: 100%;')
                    self.min_days_input.on('change', lambda e: setattr(self, 'min_days', int(e.sender.value or 1)))

                with ui.column().style('flex: 0.5; min-width: 120px;'):
                    ui.label('⏱️ Max Days').classes('text-muted').style('font-weight: 500; margin-bottom: 8px; font-size: 0.9rem;')
                    self.max_days_input = ui.number(value=self.max_days, min=1, max=30).classes('theme-input number-input').style('width: 100%;')
                    self.max_days_input.on('change', lambda e: setattr(self, 'max_days', int(e.sender.value or 1)))

            # Search button and progress - full width with margin
            with ui.column().style('width: 100%; gap: 12px; margin-top: 24px;'):
                self.search_button = ui.button(
                    'Search Flights',
                    on_click=self._on_search_button_click,
                    icon='search'
                ).classes('btn-primary').style('width: 100%; padding: 16px; font-size: 1.15rem;')

                self.progress_container = ui.column().style('width: 100%; display: none;')

    def _format_airport_display(self, iata: str) -> str:
        '''Format airport with flag for display.'''
        airport = airport_db.get_airport(iata)
        if not airport:
            return iata
        return f"{airport.flag_emoji} {airport.iata} ({airport.city})"

    async def _on_search_button_click(self):
        '''Handle search button click - start or stop search.'''
        if self.is_searching:
            # Stop the search
            self._stop_search()
        else:
            # Start the search - directly await to keep UI context
            await self._on_search_click()

    def _stop_search(self):
        '''Stop the ongoing search.'''
        self.cancel_flag['cancelled'] = True
        ui.notify('Stopping search...', type='warning')

    def _update_button_to_stop(self):
        '''Update button to show Stop Search state.'''
        self.search_button.text = 'Stop Search'
        self.search_button.props('icon=stop')
        self.search_button.classes(remove='btn-primary')
        self.search_button.classes(add='btn-danger')

    def _update_button_to_search(self):
        '''Update button to show Search Flights state.'''
        self.search_button.text = 'Search Flights'
        self.search_button.props('icon=search')
        self.search_button.classes(remove='btn-danger')
        self.search_button.classes(add='btn-primary')

    def _on_dest_airport_change(self, e):
        '''Handle destination airport/country selection change.'''
        if not e.value:
            return
        if self.dest_mode == 'country':
            # Store as country marker so search knows to expand to all airports
            self.dest_value = f'__COUNTRY_{e.value}__'
        else:
            self.dest_value = e.value

    def _on_dest_mode_change(self, e):
        '''Handle destination mode change.'''
        value = e.value

        if value == 'specific':
            self.dest_mode = 'specific'
            # Show all airports
            airports = airport_db.get_airports_for_dropdown()
            self.dest_airport_select.options = {iata: self._format_airport_display(iata) for name, iata in airports}
            self.dest_airport_label.set_text('🛬 Destination Airport')
            self.dest_airport_select.style('display: block;')
        elif value == 'all':
            self.dest_mode = 'world'
            # Add "All World" as first option, then all airports
            airports = airport_db.get_airports_for_dropdown()
            options = {'__ALL_WORLD__': '🌎 All Destinations (Entire World)'}
            options.update({iata: self._format_airport_display(iata) for name, iata in airports})
            self.dest_airport_select.options = options
            self.dest_airport_select.value = '__ALL_WORLD__'
            self.dest_value = '__ALL_WORLD__'
            self.dest_airport_label.set_text('🛬 Destination Airport')
            self.dest_airport_select.style('display: block;')
        elif value == 'country':
            self.dest_mode = 'country'
            # Show country selection dropdown
            countries = airport_db.get_countries_for_dropdown()
            options = {country_name: display_name for display_name, country_name in countries}
            self.dest_airport_select.options = options
            # Set first country as default
            if countries:
                first_country = countries[0][1]
                self.dest_airport_select.value = first_country
                self.dest_value = f'__COUNTRY_{first_country}__'
            self.dest_airport_label.set_text('🛬 Destination Country')
            self.dest_airport_select.style('display: block;')
        else:
            # It's a continent - filter airports by continent
            self.dest_mode = 'continent'
            # Get continent display name
            continents = airport_db.get_continents_for_dropdown()
            continent_name = next((name for name, cont in continents if cont == value), value)
            # Get airports for this continent
            continent_airports = airport_db.get_airports_by_continent(value)
            if continent_airports:
                # Add "All [Continent]" as first option
                options = {f'__ALL_{value}__': f'🌐 All Destinations ({continent_name})'}
                options.update({a.iata: self._format_airport_display(a.iata) for a in continent_airports})
                self.dest_airport_select.options = options
                # Set the "All" option as default
                self.dest_airport_select.value = f'__ALL_{value}__'
                self.dest_value = f'__ALL_{value}__'
            self.dest_airport_label.set_text('🛬 Destination Airport')
            self.dest_airport_select.style('display: block;')

        self.dest_airport_select.update()

    async def _on_search_click(self):
        '''Handle search with progress UI.'''
        if self.is_searching:
            return

        if not API_TOKEN:
            self._safe_notify('API token not configured. Set TRAVELPAYOUTS_TOKEN in .env', 'negative')
            return

        global api_client
        if api_client is None:
            api_client = TravelpayoutsClient(APIConfig(token=API_TOKEN))

        # Validation
        if self.min_days > self.max_days:
            self._safe_notify('Min days cannot exceed max days', 'warning')
            return

        # Reset cancel flag and update state
        self.cancel_flag['cancelled'] = False
        self.is_searching = True
        self._safe_update_button_to_stop()
        self._safe_style(self.progress_container, 'display: flex;')

        # Show progress with ETA
        try:
            with self.progress_container:
                self.progress_container.clear()
                with ui.column().style('width: 100%; gap: 12px; align-items: center;'):
                    ui.html('<div class="progress-bar"><div class="progress-bar-fill"></div></div>', sanitize=False).style('width: 100%;')
                    progress_label = ui.label('Initializing search...').classes('text-muted')
                    self.eta_label = ui.label('').classes('text-muted').style('font-size: 0.9rem;')
        except Exception as e:
            print(f"Error creating progress UI: {e}")
            progress_label = None

        try:
            destinations = self._get_destination_list()
            start = datetime.fromisoformat(self.start_date)
            end = datetime.fromisoformat(self.end_date)

            search_start_time = datetime.now()

            def progress_callback(current, total, message):
                try:
                    if progress_label:
                        progress_label.set_text(f'{message}')
                    # Calculate ETA
                    if current > 0:
                        elapsed = (datetime.now() - search_start_time).total_seconds()
                        avg_time_per_item = elapsed / current
                        remaining = total - current
                        eta_seconds = avg_time_per_item * remaining
                        if eta_seconds > 60:
                            eta_str = f"~{int(eta_seconds/60)}m {int(eta_seconds%60)}s remaining"
                        else:
                            eta_str = f"~{int(eta_seconds)}s remaining"
                        if self.eta_label:
                            self.eta_label.set_text(f'Searching {current}/{total} combinations • {eta_str}')
                    else:
                        if self.eta_label:
                            self.eta_label.set_text(f'Searching 0/{total} combinations')
                except Exception:
                    pass  # Silently ignore UI update errors in callback

            self.results = await asyncio.to_thread(
                api_client.search_deals,
                origin=self.origin_iata,
                destinations=destinations,
                start_date=start,
                end_date=end,
                min_days=self.min_days,
                max_days=self.max_days,
                progress_callback=progress_callback,
                cancel_flag=self.cancel_flag
            )

            self.current_page = 1
            self.search_performed = True
            self._safe_render_results()

            # Show results section
            self._safe_style(self.results_section, 'display: flex;')

            # Show appropriate notification
            if self.cancel_flag['cancelled']:
                if self.results:
                    self._safe_notify(f'Search stopped. Found {len(self.results)} deals so far.', 'warning')
                else:
                    self._safe_notify('Search stopped.', 'warning')
            elif not self.results:
                self._safe_notify('No deals found. Try different criteria.', 'info')
            else:
                self._safe_notify(f'Found {len(self.results)} deals!', 'positive')

        except Exception as e:
            if not self.cancel_flag['cancelled']:
                self._safe_notify(f'Search failed: {str(e)}', 'negative')
                print(f"Search error: {e}")

        finally:
            self.is_searching = False
            self._safe_update_button_to_search()
            self._safe_style(self.progress_container, 'display: none;')

    def _safe_notify(self, message: str, msg_type: str = 'info'):
        '''Safely show notification, handling context errors.'''
        try:
            ui.notify(message, type=msg_type)
        except Exception as e:
            print(f"Notification ({msg_type}): {message}")

    def _safe_style(self, element, style: str):
        '''Safely apply style to element, handling errors.'''
        try:
            if element:
                element.style(style)
        except Exception as e:
            print(f"Style error: {e}")

    def _safe_render_results(self):
        '''Safely render results, handling errors.'''
        try:
            self._render_results()
        except Exception as e:
            print(f"Render error: {e}")

    def _safe_update_button_to_stop(self):
        '''Safely update button to stop state.'''
        try:
            self._update_button_to_stop()
        except Exception as e:
            print(f"Button update error: {e}")

    def _safe_update_button_to_search(self):
        '''Safely update button to search state.'''
        try:
            self._update_button_to_search()
        except Exception as e:
            print(f"Button update error: {e}")

    def _get_destination_list(self) -> List[str]:
        '''Get destination IATA codes based on mode.'''
        dest_value = self.dest_value

        # Check if "All" option is selected
        if dest_value == '__ALL_WORLD__':
            return [a.iata for a in airport_db.get_all_airports()]
        elif dest_value and dest_value.startswith('__COUNTRY_') and dest_value.endswith('__'):
            # Extract country name from __COUNTRY_Portugal__ format
            country = dest_value[10:-2]  # Remove __COUNTRY_ prefix and __ suffix
            airports = airport_db.get_airports_by_country(country)
            return [a.iata for a in airports]
        elif dest_value and dest_value.startswith('__ALL_') and dest_value.endswith('__'):
            # Extract continent from __ALL_Europe__ format
            continent = dest_value[6:-2]  # Remove __ALL_ prefix and __ suffix
            airports = airport_db.get_airports_by_continent(continent)
            return [a.iata for a in airports]
        elif self.dest_mode == 'specific':
            return [dest_value] if dest_value else []
        elif self.dest_mode == 'continent':
            # Single airport selected from continent list
            return [dest_value] if dest_value else []
        elif self.dest_mode == 'country':
            # This shouldn't happen if country is properly marked, but fallback
            return [dest_value] if dest_value else []
        else:  # world with specific airport selected
            return [dest_value] if dest_value else []

    def _create_results_section(self):
        '''Create results display area - hidden until search is performed.'''
        self.results_section = ui.column().classes('theme-card').style('width: 100%; padding: 32px; gap: 20px; display: none;')
        self.results_section.props('id="search-results"')  # Add ID for scroll targeting
        with self.results_section:
            ui.label('✈️ Search Results').style('font-size: 1.3rem; font-weight: 600; color: var(--text);')
            self.results_container = ui.column().style('width: 100%; gap: 16px;')
            self.pagination_container = ui.row().style('width: 100%; justify-content: center; gap: 8px;')


    def _render_empty_state(self):
        '''Render empty state with illustration and call to action.'''
        with ui.column().classes('empty-state').style('width: 100%; align-items: center; justify-content: center;'):
            # Animated plane icon with gradient background
            ui.html('''
                <div class="empty-state-icon">
                    <svg width="80" height="80" viewBox="0 0 24 24" fill="none" stroke="url(#plane-gradient)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                        <defs>
                            <linearGradient id="plane-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
                                <stop offset="0%" style="stop-color:#7c5cff;stop-opacity:1" />
                                <stop offset="100%" style="stop-color:#2dd4ff;stop-opacity:1" />
                            </linearGradient>
                        </defs>
                        <path d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
                    </svg>
                </div>
            ''', sanitize=False)

            # Main message
            ui.label('Ready to Explore?').style(
                'font-size: 1.5rem; font-weight: 600; margin-top: 24px; color: var(--text);'
            )

            # Subtitle
            ui.label('Find amazing flight deals to your dream destinations').classes('text-muted').style(
                'font-size: 1rem; margin-top: 8px; max-width: 400px; text-align: center; line-height: 1.6;'
            )

            # Features/hints
            with ui.row().style('margin-top: 32px; gap: 24px; flex-wrap: wrap; justify-content: center;'):
                # Hint 1
                with ui.column().style('align-items: center; gap: 8px;'):
                    ui.html('<span style="font-size: 1.5rem;">🌍</span>', sanitize=False)
                    ui.label('Search worldwide').classes('text-muted').style('font-size: 0.85rem;')

                # Hint 2
                with ui.column().style('align-items: center; gap: 8px;'):
                    ui.html('<span style="font-size: 1.5rem;">💰</span>', sanitize=False)
                    ui.label('Compare prices').classes('text-muted').style('font-size: 0.85rem;')

                # Hint 3
                with ui.column().style('align-items: center; gap: 8px;'):
                    ui.html('<span style="font-size: 1.5rem;">✈️</span>', sanitize=False)
                    ui.label('Book your trip').classes('text-muted').style('font-size: 0.85rem;')

            ui.html('''
                <h4>Start your search above</h4>
            ''', sanitize=False)

    def _render_results(self):
        '''Render search results with pagination.'''
        self.results_container.clear()
        self.pagination_container.clear()

        # Show results section
        if self.results_section:
            self.results_section.style('display: flex;')

        if not self.results:
            with self.results_container:
                self._render_empty_state()
            return

        total_pages = (len(self.results) - 1) // ITEMS_PER_PAGE + 1
        start_idx = (self.current_page - 1) * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, len(self.results))
        page_results = self.results[start_idx:end_idx]

        with self.results_container:
            ui.label(f'{len(self.results)} deals found (Page {self.current_page}/{total_pages})').classes('text-muted')
            for deal in page_results:
                self._render_deal_card(deal)

        self._render_pagination(total_pages)

    def _render_deal_card(self, deal: FlightDeal):
        '''Render enhanced deal card with CTAs.'''
        origin_airport = airport_db.get_airport(deal.origin_iata)
        dest_airport = airport_db.get_airport(deal.dest_iata)

        origin_city = origin_airport.city if origin_airport else deal.origin_city
        dest_city = dest_airport.city if dest_airport else deal.dest_city

        with ui.card().classes('deal-card').style('width: 100%; padding: 24px;'):
            # Top row: Route + Price
            with ui.row().style('width: 100%; align-items: center; justify-content: space-between; margin-bottom: 16px;'):
                with ui.row().style('align-items: center; gap: 16px;'):
                    ui.label(f"{deal.origin_flag} {deal.origin_iata} ({origin_city})").style('font-size: 1.2rem; font-weight: 600;')
                    ui.icon('arrow_forward', size='1.5rem').style('color: var(--text-muted);')
                    ui.label(f"{deal.dest_flag} {deal.dest_iata} ({dest_city})").style('font-size: 1.2rem; font-weight: 600;')

                ui.label(deal.formatted_price).style(
                    'font-size: 2rem; font-weight: 700; font-family: monospace;'
                ).classes('text-gradient')


            # Details row
            with ui.row().style('width: 100%; gap: 24px; flex-wrap: wrap; margin-bottom: 16px;'):
                with ui.row().style('align-items: center; gap: 8px;'):
                    ui.icon('flight_takeoff', size='1.1rem').classes('text-muted')
                    ui.label(deal.depart_date[:10]).classes('text-muted')

                with ui.row().style('align-items: center; gap: 8px;'):
                    ui.icon('flight_land', size='1.1rem').classes('text-muted')
                    ui.label(deal.return_date[:10]).classes('text-muted')

                with ui.row().style('align-items: center; gap: 8px;'):
                    ui.icon('schedule', size='1.1rem').classes('text-muted')
                    ui.label(f'{deal.trip_duration} days').classes('text-muted')

                if deal.transfers is not None:
                    if deal.transfers == 0:
                        ui.html('<span class="chip chip-success">Direct</span>', sanitize=False)
                    elif deal.transfers == 1:
                        ui.html('<span class="chip chip-warning">1 stop</span>', sanitize=False)
                    else:
                        ui.html(f'<span class="chip">{deal.transfers} stops</span>', sanitize=False)

            # CTAs - Direct links
            with ui.row().style('width: 100%; gap: 12px; flex-wrap: wrap;'):
                google_url = self._generate_google_flights_url(deal)
                booking_url = self._generate_booking_url(deal)

                # Google Flights link button
                with ui.link(target=google_url, new_tab=True).style('text-decoration: none;'):
                    ui.button('View on Google Flights', icon='search').classes('btn-secondary').props('no-caps')

                # Booking.com link button
                with ui.link(target=booking_url, new_tab=True).style('text-decoration: none;'):
                    ui.button('View on Booking', icon='hotel').classes('btn-primary').props('no-caps')

    def _generate_google_flights_url(self, deal: FlightDeal) -> str:
        '''Generate Google Flights search URL.'''
        origin_airport = airport_db.get_airport(deal.origin_iata)
        dest_airport = airport_db.get_airport(deal.dest_iata)

        origin_city = origin_airport.city if origin_airport else deal.origin_city
        dest_city = dest_airport.city if dest_airport else deal.dest_city

        depart_date = deal.depart_date[:10]
        return_date = deal.return_date[:10]

        query = f"Flights from {origin_city} to {dest_city} on {depart_date} returning {return_date}"
        params = {
            'gl': 'PT',
            'hl': 'en',
            'q': query
        }
        return f"https://www.google.com/travel/flights?{urlencode(params)}"

    def _generate_booking_url(self, deal: FlightDeal) -> str:
        '''Generate Booking.com URL with destination city and travel dates.'''
        dest_airport = airport_db.get_airport(deal.dest_iata)
        dest_city = dest_airport.city if dest_airport else deal.dest_city

        checkin_date = deal.depart_date[:10]  # YYYY-MM-DD format
        checkout_date = deal.return_date[:10]  # YYYY-MM-DD format

        params = {
            'ss': dest_city,
            'checkin': checkin_date,
            'checkout': checkout_date
        }
        return f"https://www.booking.com/searchresults.html?{urlencode(params)}"


    def _render_pagination(self, total_pages: int):
        '''Render pagination controls.'''
        with self.pagination_container:
            if total_pages <= 1:
                return

            ui.button(icon='chevron_left', on_click=lambda: self._change_page(self.current_page - 1)).classes('btn-secondary').set_enabled(self.current_page > 1)

            start_page = max(1, self.current_page - 2)
            end_page = min(total_pages, self.current_page + 2)

            for page_num in range(start_page, end_page + 1):
                btn_class = 'btn-primary' if page_num == self.current_page else 'btn-secondary'
                ui.button(str(page_num), on_click=lambda p=page_num: self._change_page(p)).classes(btn_class)

            ui.button(icon='chevron_right', on_click=lambda: self._change_page(self.current_page + 1)).classes('btn-secondary').set_enabled(self.current_page < total_pages)

    def _change_page(self, new_page: int):
        '''Navigate to different page and scroll to results.'''
        total_pages = (len(self.results) - 1) // ITEMS_PER_PAGE + 1
        if 1 <= new_page <= total_pages:
            self.current_page = new_page
            self._render_results()
            # Scroll to the results section
            ui.run_javascript('document.getElementById("search-results").scrollIntoView({behavior: "smooth", block: "start"})')

    def _create_faq_section(self):
        '''Create FAQ section.'''
        with ui.column().classes('theme-card').style('width: 100%; padding: 32px; gap: 24px;'):
            ui.label('❓ Frequently Asked Questions').style('font-size: 1.2rem; font-weight: 600;')

            faqs = [
                ('What is this app?', 'A local flight deal finder that searches cached price data from Travelpayouts/Aviasales to inspire your travel plans.'),
                ('Are prices real-time?', 'No. Prices are 2-7 days old (cached search data from other users). Always verify on booking sites.'),
                ('Why are some routes empty?', 'The API only has data for popular routes with recent search activity. Try different dates or destinations.'),
                ('What does "cached" mean?', 'The API returns prices from recent user searches, not live airline data. This makes searches fast but prices may change.'),
                ('How do links work?', 'Google Flights link opens a search. Booking link uses Travelpayouts deep link or Aviasales search.'),
                ('Privacy?', 'Runs 100% locally. Only calls Travelpayouts API for flight data. No tracking or analytics.')
            ]

            for question, answer in faqs:
                with ui.expansion(question).classes('faq-item').style('width: 100%;'):
                    ui.label(answer).classes('text-muted').style('line-height: 1.6;')

    def _create_footer(self):

        with ui.column().classes('footer-container'):
            with ui.element('div').classes('footer-grid'):
                with ui.element('div').classes('footer-panel is-info'):
                    with ui.element('div').classes('footer-panel-header'):
                        ui.html('''
                            <svg class="footer-panel-icon" viewBox="0 0 20 20" fill="currentColor" width="20" height="20">
                                <path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a.75.75 0 000 1.5h.253a.25.25 0 01.244.304l-.459 2.066A1.75 1.75 0 0010.747 15H11a.75.75 0 000-1.5h-.253a.25.25 0 01-.244-.304l.459-2.066A1.75 1.75 0 009.253 9H9z" clip-rule="evenodd"/>
                            </svg>
                        ''', sanitize=False)
                        ui.label('Important Notice').classes('footer-panel-title')

                    with ui.element('p').classes('footer-panel-text'):
                        ui.html('''
                            Flight prices displayed are <strong>cached data</strong> from the Travelpayouts API, 
                            typically 2–7 days old. Prices are <em>not real-time</em> and may differ from current rates. 
                            Always verify pricing on the booking site before purchasing.
                        ''', sanitize=False)

                    with ui.element('div').classes('footer-panel-badge').style('margin-top: 16px;'):
                        ui.html('''
                            <svg viewBox="0 0 16 16" fill="currentColor" width="12" height="12">
                                <path d="M8 3.5a.5.5 0 0 0-1 0V9a.5.5 0 0 0 .252.434l3.5 2a.5.5 0 0 0 .496-.868L8 8.71V3.5z"/>
                                <path d="M8 16A8 8 0 1 0 8 0a8 8 0 0 0 0 16zm7-8A7 7 0 1 1 1 8a7 7 0 0 1 14 0z"/>
                            </svg>
                        ''', sanitize=False)
                        ui.label('Updated every 2–7 days · For inspiration only')

                with ui.element('div').classes('footer-section is-powered'):
                    ui.html('<span class="footer-section-label">Powered By</span>', sanitize=False)

                    with ui.element('nav').classes('footer-pills'):
                        with ui.link(target='https://www.travelpayouts.com', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16" fill="none">
                                    <path fill="#00BCD4" d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
                                    <path stroke="#00BCD4" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" d="M2 17l10 5 10-5M2 12l10 5 10-5"/>
                                </svg>
                                <span class="footer-pill-label">Travelpayouts</span>
                            ''', sanitize=False)

                        with ui.link(target='https://developers.amadeus.com/', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16">
                                    <circle cx="12" cy="12" r="10" fill="#1B69B6"/>
                                    <path d="M12 6l-6 10h3l1-2h4l1 2h3L12 6zm0 3.5L13.5 13h-3L12 9.5z" fill="white"/>
                                </svg>
                                <span class="footer-pill-label">Amadeus</span>
                            ''', sanitize=False)

                        with ui.link(target='https://www.aviasales.com', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16">
                                    <path fill="#FF6D00" d="M21 16v-2l-8-5V3.5c0-.83-.67-1.5-1.5-1.5S10 2.67 10 3.5V9l-8 5v2l8-2.5V19l-2 1.5V22l3.5-1 3.5 1v-1.5L13 19v-5.5l8 2.5z"/>
                                </svg>
                                <span class="footer-pill-label">Aviasales</span>
                            ''', sanitize=False)

                        with ui.link(target='https://www.google.com/travel/flights', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16">
                                    <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
                                    <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                                    <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                                    <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                                </svg>
                                <span class="footer-pill-label">Google Flights</span>
                            ''', sanitize=False)

                        with ui.link(target='https://nicegui.io', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16">
                                    <rect width="24" height="24" rx="6" fill="#5898D4"/>
                                    <path d="M7 17V7h2l6 7V7h2v10h-2l-6-7v7H7z" fill="white"/>
                                </svg>
                                <span class="footer-pill-label">NiceGUI</span>
                            ''', sanitize=False)

                        with ui.link(target='https://www.python.org', new_tab=True).classes('footer-pill'):
                            ui.html('''
                                <svg class="footer-pill-icon" viewBox="0 0 24 24" width="16" height="16">
                                    <path fill="#3776AB" d="M11.914 0C5.82 0 6.2 2.656 6.2 2.656l.007 2.752h5.814v.826H3.9S0 5.789 0 11.969c0 6.18 3.403 5.96 3.403 5.96h2.03v-2.867s-.109-3.42 3.35-3.42h5.766s3.24.052 3.24-3.148V3.202S18.28 0 11.913 0zM8.708 1.85c.578 0 1.046.47 1.046 1.052 0 .581-.468 1.051-1.046 1.051-.579 0-1.046-.47-1.046-1.051 0-.582.467-1.052 1.046-1.052z"/>
                                    <path fill="#FFD43B" d="M12.087 24c6.093 0 5.713-2.656 5.713-2.656l-.007-2.752h-5.814v-.826h8.123s3.9.445 3.9-5.735c0-6.18-3.404-5.96-3.404-5.96h-2.03v2.867s.109 3.42-3.35 3.42H9.452s-3.24-.052-3.24 3.148v5.292S5.72 24 12.087 24zm3.206-1.85c-.578 0-1.046-.47-1.046-1.052 0-.581.468-1.051 1.046-1.051.579 0 1.046.47 1.046 1.051 0 .582-.467 1.052-1.046 1.052z"/>
                                </svg>
                                <span class="footer-pill-label">Python</span>
                            ''', sanitize=False)

            ui.html('<div class="footer-separator"></div>', sanitize=False)

            with ui.element('div').classes('footer-bottom'):
                ui.html(f'''
                    <p class="footer-copyright">
                        Copyright © {datetime.now().year} All rights reserved to <span class="footer-author">João Ferreira</span>
                    </p>
                ''', sanitize=False)
                ui.html('''
                    <p class="footer-tagline">
                        Built with <span class="footer-heart">❤️</span> for Sofia & travel enthusiasts
                        <span class="footer-location">
                            <svg viewBox="0 0 16 16" fill="currentColor" width="10" height="10">
                                <path d="M8 16s6-5.686 6-10A6 6 0 0 0 2 6c0 4.314 6 10 6 10zm0-7a3 3 0 1 1 0-6 3 3 0 0 1 0 6z"/>
                            </svg>
                            Paris, 12 Aug - 16 Aug 2025
                        </span>
                    </p>
                ''', sanitize=False)


# ============================================================================
# Auto-shutdown functionality
# ============================================================================
SHUTDOWN_DELAY = 5  # seconds of inactivity before shutdown

shutdown_task = None
connected_clients = 0


async def schedule_shutdown():
    """Shutdown server after delay if no clients connected."""
    await asyncio.sleep(SHUTDOWN_DELAY)
    if connected_clients == 0:
        print(f"No clients connected for {SHUTDOWN_DELAY}s. Shutting down...")
        nicegui_app.shutdown()


@nicegui_app.on_connect
def on_client_connect():
    """Cancel scheduled shutdown when a client connects."""
    global shutdown_task, connected_clients
    connected_clients += 1
    if shutdown_task is not None:
        shutdown_task.cancel()
        shutdown_task = None


@nicegui_app.on_disconnect
def on_client_disconnect():
    """Schedule shutdown when all clients disconnect."""
    global shutdown_task, connected_clients
    connected_clients = max(0, connected_clients - 1)

    async def check_and_schedule():
        global shutdown_task
        await asyncio.sleep(1)  # Brief delay to allow reconnections
        if connected_clients == 0:
            shutdown_task = asyncio.create_task(schedule_shutdown())

    asyncio.create_task(check_and_schedule())


@ui.page('/')
def index():
    '''Main page route.'''
    app_instance = FlightSearchApp()
    app_instance.create_ui()


# Serve static CSS - use add_static_file for a single file
nicegui_app.add_static_files('/static', str(get_resource_path('static')))


if __name__ in {'__main__', '__mp_main__'}:
    if not API_TOKEN:
        print('WARNING: TRAVELPAYOUTS_TOKEN not set in .env file')
        print('Please create a .env file with your API token.')

    ui.run(
        title='Flight Deal Finder',
        favicon='✈️',
        dark=None,
        reload=False,
        port=8080,
        show=True
    )
