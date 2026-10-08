"""Local storage locations; secrets are never loaded from .env automatically."""

import os
from pathlib import Path


def data_dir() -> Path:
    return Path(
        os.environ.get("LEDGERLIGHT_DATA_DIR", "~/.local/share/ledgerlight")
    ).expanduser()


def config_dir() -> Path:
    return Path(
        os.environ.get("LEDGERLIGHT_CONFIG_DIR", "~/.config/ledgerlight")
    ).expanduser()


def db_path() -> Path:
    return data_dir() / "ledgerlight.db"
