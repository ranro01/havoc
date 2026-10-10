from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def root() -> Path:
    """Project root. Run commands from the repo root, or set HAVOC_HOME."""
    return Path(os.getenv("HAVOC_HOME", Path.cwd()))


def data_dir() -> Path:
    return root() / "data"


def index_dir() -> Path:
    return root() / "index"


def groq_model() -> str:
    return os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
