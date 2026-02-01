from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


APP_NAME_NO_SPACES = 'FlightDealFinder'


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def exe_dir() -> Path:
    return Path(sys.executable).resolve().parent if is_frozen() else Path(__file__).resolve().parent


def project_root_dir() -> Path:
    # For dev runs, keep config.env next to the source files.
    return Path(__file__).resolve().parent


def _user_config_dir() -> Optional[Path]:
    """Return per-user config directory used by the Windows installer (if any)."""
    local_appdata = os.getenv('LOCALAPPDATA')
    if not local_appdata:
        return None
    try:
        return Path(local_appdata) / APP_NAME_NO_SPACES
    except Exception:
        return None


def _candidate_dotenv_paths() -> list[Path]:
    """Return candidate locations for config.env.

    We support:
    - dev runs (next to sources)
    - frozen builds (next to the executable)
    - running from an arbitrary working directory
    - Windows installer per-user provisioning: %LOCALAPPDATA%/FlightDealFinder/config.env

    Precedence rule (first existing file wins):
    1) next to the executable (frozen) / or next to sources (dev)
    2) current working directory
    3) Windows per-user provisioned location (installer fallback)
    """
    candidates: list[Path] = []

    # Frozen exe: user can drop config.env next to the .exe
    try:
        candidates.append(exe_dir() / 'config.env')
    except Exception:
        pass

    # Dev/source: repo folder
    try:
        candidates.append(project_root_dir() / 'config.env')
    except Exception:
        pass

    # Current working directory
    try:
        candidates.append(Path.cwd() / 'config.env')
    except Exception:
        pass

    # Windows installer provisions a per-user config.env here (fallback)
    user_dir = _user_config_dir()
    if user_dir is not None:
        candidates.append(user_dir / 'config.env')

    # De-dup while preserving order
    out: list[Path] = []
    seen: set[str] = set()
    for p in candidates:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def dotenv_path() -> Path:
    """Best-effort config.env locator.

    Compatibility: callers treat this as 'the' expected location. We now return the
    first existing candidate if available, otherwise the dev default.
    """
    for p in _candidate_dotenv_paths():
        try:
            if p.exists() and p.is_file():
                return p
        except Exception:
            continue
    return project_root_dir() / 'config.env'


def _is_placeholder(value: str) -> bool:
    v = (value or '').strip()
    if not v:
        return True
    # Only reject obvious placeholders, not values that could be real credentials
    return v.lower() in {'x', 'y', 'your_client_id', 'your_client_secret', 'your_token',
                         'youramadeusclientidhere', 'youramadeusclientsecrethere',
                         'yourtravelpayoutstokenhere', 'placeholder', 'example', 'test'}


def load_dotenv_once() -> Optional[Path]:
    """Load config.env if present.

    The config.env file should always take precedence when:
    - Amadeus credentials are not set in environment variables
    - Amadeus credentials in environment are placeholder values

    This ensures that the config.env file is the primary source of configuration.
    """
    env_path = dotenv_path()
    try:
        if not (env_path.exists() and env_path.is_file()):
            return None

        current_id = (os.getenv('AMADEUS_CLIENT_ID') or '').strip()
        current_secret = (os.getenv('AMADEUS_CLIENT_SECRET') or '').strip()

        # Check if Amadeus credentials are missing or placeholders
        amadeus_is_placeholder = _is_placeholder(current_id) or _is_placeholder(current_secret)
        amadeus_missing = (not current_id) or (not current_secret)

        # Always override when credentials are missing or placeholders
        # This ensures config.env is properly loaded
        should_override = amadeus_is_placeholder or amadeus_missing

        # Load config.env with override when needed
        load_dotenv(dotenv_path=str(env_path), override=should_override)
        return env_path
    except Exception as e:
        # Log the error for debugging
        print(f"Warning: Failed to load config.env: {e}")
        return None


@dataclass(frozen=True)
class LoadedConfig:
    travelpayouts_token: str
    amadeus_client_id: str
    amadeus_client_secret: str
    loaded_from: Optional[Path]
    provider_override: str = ''

    @property
    def has_amadeus(self) -> bool:
        return bool(self.amadeus_client_id and self.amadeus_client_secret)

    @property
    def has_travelpayouts(self) -> bool:
        return bool(self.travelpayouts_token)

    @property
    def provider_preference(self) -> str:
        """Return the selected provider.

        Order:
        1) Optional explicit override via PROVIDER=amadeus|travelpayouts|auto
        2) Prefer Amadeus when configured
        3) Else Travelpayouts when configured
        """
        override = (self.provider_override or '').strip().lower()
        if override in {'amadeus', 'travelpayouts'}:
            # Only honor the override when the requested provider is configured.
            if override == 'amadeus' and self.has_amadeus:
                return 'amadeus'
            if override == 'travelpayouts' and self.has_travelpayouts:
                return 'travelpayouts'
            return 'none'

        # Prefer Amadeus when configured
        if self.has_amadeus:
            return 'amadeus'
        if self.has_travelpayouts:
            return 'travelpayouts'
        return 'none'


def load_config() -> LoadedConfig:
    """Load credentials from environment variables and/or config.env.

    The project uses config.env as the file containing:
      - AMADEUS_CLIENT_ID
      - AMADEUS_CLIENT_SECRET
      - TRAVELPAYOUTS_TOKEN
      - optional: PROVIDER=amadeus|travelpayouts|auto

    We only read config.env; we never modify it.
    """
    loaded_from = load_dotenv_once()

    tp = (os.getenv('TRAVELPAYOUTS_TOKEN') or '').strip()
    aid = (os.getenv('AMADEUS_CLIENT_ID') or '').strip()
    asec = (os.getenv('AMADEUS_CLIENT_SECRET') or '').strip()
    provider_override = (os.getenv('PROVIDER') or '').strip()

    # Treat placeholder values as "not configured".
    if _is_placeholder(aid):
        print(f"WARNING: AMADEUS_CLIENT_ID contains a placeholder value. Please set your real Amadeus credentials in config.env")
        aid = ''
    if _is_placeholder(asec):
        print(f"WARNING: AMADEUS_CLIENT_SECRET contains a placeholder value. Please set your real Amadeus credentials in config.env")
        asec = ''

    return LoadedConfig(
        travelpayouts_token=tp,
        amadeus_client_id=aid,
        amadeus_client_secret=asec,
        loaded_from=loaded_from,
        provider_override=provider_override,
    )


def _mask(s: str) -> str:
    if not s:
        return ''
    if len(s) <= 6:
        return '*' * len(s)
    return f"{s[:3]}***{s[-3:]}"


def config_diagnostics() -> str:
    """Human-readable diagnostics for config/env loading (no secrets leaked)."""
    cfg = load_config()
    candidates = _candidate_dotenv_paths()

    lines = []
    lines.append(f"Frozen: {is_frozen()}")
    lines.append(f"CWD: {Path.cwd()}")
    lines.append(f"Resolved config.env: {dotenv_path()}")
    lines.append("Candidates searched:")
    for p in candidates:
        try:
            exists = p.exists() and p.is_file()
        except Exception:
            exists = False
        lines.append(f"  - {p} (exists={exists})")

    lines.append(f"Loaded from: {cfg.loaded_from}")
    lines.append(f"Provider preference: {cfg.provider_preference}")
    lines.append(f"AMADEUS_CLIENT_ID: {_mask(cfg.amadeus_client_id)}")
    lines.append(f"AMADEUS_CLIENT_SECRET: {_mask(cfg.amadeus_client_secret)}")
    lines.append(f"TRAVELPAYOUTS_TOKEN: {_mask(cfg.travelpayouts_token)}")
    return "\n".join(lines)


def config_help_text() -> str:
    env_file = dotenv_path()
    user_dir = _user_config_dir()
    return (
        'No API credentials configured. Create a config.env file and set ONE provider:\n\n'
        'Amadeus (recommended):\n'
        '  AMADEUS_CLIENT_ID=...\n'
        '  AMADEUS_CLIENT_SECRET=...\n\n'
        'Travelpayouts (legacy):\n'
        '  TRAVELPAYOUTS_TOKEN=...\n\n'
        f'config.env location (first found): {env_file}\n'
        + (f'Per-user config folder (Windows installer): {user_dir}\\config.env\n' if user_dir else '')
    )
