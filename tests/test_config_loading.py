from pathlib import Path

import config


def _force_cwd_only(monkeypatch, tmp_path: Path) -> None:
    """Make tests deterministic by ensuring only the temp CWD has config.env."""
    monkeypatch.chdir(tmp_path)

    # Ensure we don't accidentally load a per-user installer config.
    monkeypatch.delenv('LOCALAPPDATA', raising=False)

    # Ensure we don't pick up the repo's real config.env (project_root_dir/exe_dir)
    monkeypatch.setattr(config, 'project_root_dir', lambda: tmp_path)
    monkeypatch.setattr(config, 'exe_dir', lambda: tmp_path)


def test_dotenv_path_prefers_existing(tmp_path, monkeypatch):
    # Create a config.env in CWD and ensure it can be found.
    env_file = tmp_path / "config.env"
    env_file.write_text("AMADEUS_CLIENT_ID=abc\nAMADEUS_CLIENT_SECRET=def\n")

    _force_cwd_only(monkeypatch, tmp_path)

    # Clear env vars so dotenv is needed
    monkeypatch.delenv("AMADEUS_CLIENT_ID", raising=False)
    monkeypatch.delenv("AMADEUS_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TRAVELPAYOUTS_TOKEN", raising=False)

    cfg = config.load_config()
    assert cfg.has_amadeus
    assert cfg.loaded_from is not None
    assert Path(cfg.loaded_from) == env_file


def test_dotenv_overrides_placeholders(tmp_path, monkeypatch):
    env_file = tmp_path / "config.env"
    env_file.write_text("AMADEUS_CLIENT_ID=realid\nAMADEUS_CLIENT_SECRET=realsecret\n")

    _force_cwd_only(monkeypatch, tmp_path)

    # Set placeholders in environment; config.env should override them.
    monkeypatch.setenv("AMADEUS_CLIENT_ID", "x")
    monkeypatch.setenv("AMADEUS_CLIENT_SECRET", "y")
    monkeypatch.delenv("TRAVELPAYOUTS_TOKEN", raising=False)

    cfg = config.load_config()
    assert cfg.has_amadeus
    assert cfg.amadeus_client_id == "realid"
    assert cfg.amadeus_client_secret == "realsecret"
