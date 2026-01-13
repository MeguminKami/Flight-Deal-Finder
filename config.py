from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

from dotenv import load_dotenv


APP_NAME_NO_SPACES = 'FlightDealFinder'


def is_frozen() -> bool:
    return bool(getattr(sys, 'frozen', False))


def exe_dir() -> Path:
    return Path(sys.executable).resolve().parent if is_frozen() else Path(__file__).resolve().parent


def user_config_dir() -> Path:
    # Prefer LocalAppData on Windows; fall back to ~/.config on others.
    local = os.getenv('LOCALAPPDATA')
    if local:
        return Path(local) / APP_NAME_NO_SPACES
    return Path.home() / '.config' / APP_NAME_NO_SPACES


def candidate_env_files() -> Iterable[Path]:
    # Highest priority first (later candidates only matter if nothing loaded yet).
    yield user_config_dir() / 'config.env'
    yield exe_dir() / 'config.env'
    yield exe_dir() / '.env'
    # dev convenience
    yield Path(__file__).resolve().parent / '.env'


@dataclass(frozen=True)
class LoadedConfig:
    token: str
    loaded_from: Optional[Path]


def load_config() -> LoadedConfig:
    """Load dotenv files (if present) and return the Travelpayouts token.

    Returns:
        LoadedConfig with token and which file (if any) provided it.
    """
    # Environment always wins
    token = (os.getenv('TRAVELPAYOUTS_TOKEN') or '').strip()
    if token:
        return LoadedConfig(token=token, loaded_from=None)

    loaded_from: Optional[Path] = None
    for env_path in candidate_env_files():
        try:
            if env_path.exists() and env_path.is_file():
                # override=False means: don't clobber an already-set env var.
                load_dotenv(dotenv_path=str(env_path), override=False)
                token = (os.getenv('TRAVELPAYOUTS_TOKEN') or '').strip()
                if token:
                    loaded_from = env_path
                    break
        except Exception:
            # Ignore unreadable/malformed env files and continue.
            continue

    return LoadedConfig(token=token, loaded_from=loaded_from)


def config_help_text() -> str:
    """Human-friendly instructions shown in the UI."""
    cfg = user_config_dir() / 'config.env'
    portable = exe_dir() / 'config.env'
    return (
        'API token not configured. Set TRAVELPAYOUTS_TOKEN in one of these places:\n\n'
        f'1) Environment variable TRAVELPAYOUTS_TOKEN\n'
        f'2) User config file: {cfg}\n'
        f'3) Portable config next to the app: {portable}\n'
    )
