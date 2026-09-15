"""Environment access shared by all settings modules."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]
env = environ.Env()

_loaded: set[Path] = set()


def load_env_file(path: Path = BASE_DIR / ".env") -> None:
    """Load a dotenv file once. Real environment variables always win over the file."""
    if path in _loaded or not path.is_file():
        return
    environ.Env.read_env(str(path), overwrite=False)
    _loaded.add(path)
