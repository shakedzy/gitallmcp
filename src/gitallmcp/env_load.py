"""Load `.env` into the process environment before GitHub client reads tokens."""

from __future__ import annotations

from pathlib import Path


def load_dotenv_files() -> None:
    """Populate os.environ from `.env` files.

    Order:
    1. Repository root `.env` (next to ``src/`` when installed editable from this layout).
    2. Current working directory `.env`, with values overriding (1) so local cwd wins.

    Variables already set in the real environment are not overwritten unless ``override=True``
    on the second load; the first uses default ``override=False`` so OS/env wins over repo file.
    """
    from dotenv import load_dotenv

    pkg_dir = Path(__file__).resolve().parent
    repo_root = pkg_dir.parent.parent

    load_dotenv(repo_root / ".env")
    load_dotenv(Path.cwd() / ".env", override=True)
