"""Fernet token encryption with a private, atomically published local key."""

import os
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet

from ledgerlight.config import config_dir


def get_or_create_key() -> bytes:
    directory = config_dir()
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    path = directory / "key"
    if not path.exists():
        # Publish only a complete key; concurrent first uses must share one key.
        fd, temporary = tempfile.mkstemp(dir=directory, prefix=".key-")
        try:
            with os.fdopen(fd, "wb") as file:
                file.write(Fernet.generate_key())
                file.flush()
                os.fsync(file.fileno())
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
        finally:
            # Remove secret-bearing temporaries even if writing/publication fails.
            Path(temporary).unlink(missing_ok=True)
    path.chmod(0o600)
    key = path.read_bytes()
    Fernet(key)  # Fail closed on a corrupt key; never replace it and lose access.
    return key


def encrypt(value: str) -> str:
    return Fernet(get_or_create_key()).encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return Fernet(get_or_create_key()).decrypt(value.encode()).decode()
