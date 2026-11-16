"""Windows frozen entry (PyInstaller)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Ensure sibling package import works when frozen.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _setup_file_logging() -> None:
    try:
        from voice_type.platform_util import user_data_dir
        log_path = user_data_dir() / "voice-type.log"
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%H:%M:%S",
            handlers=[
                logging.FileHandler(log_path, encoding="utf-8"),
                logging.StreamHandler(sys.stderr),
            ],
        )
    except Exception:
        logging.basicConfig(level=logging.INFO)


if __name__ == "__main__":
    _setup_file_logging()
    from voice_type.__main__ import main
    raise SystemExit(main())
