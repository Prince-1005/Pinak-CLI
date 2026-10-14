"""Central logging setup for Pinak CLI.

- Console output stays pretty (Rich) via existing prints.
- This module adds an optional *file* log (`--log-file`) plus a `--verbose`
  flag that switches the root logger to DEBUG.
- Safe to call multiple times; handlers are added only once.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_configured = False
_file_handler_path: str | None = None


def setup_logging(verbose: bool = False, log_file: str | None = None) -> logging.Logger:
    """Configure root logging. Returns the 'pinak' logger."""
    global _configured, _file_handler_path

    logger = logging.getLogger("pinak")
    level = logging.DEBUG if verbose else logging.INFO
    console_level = logging.DEBUG if verbose else logging.WARNING
    logger.setLevel(level)

    if not _configured:
        if sys.stderr is not None:
            handler = logging.StreamHandler(sys.stderr)
            handler.setLevel(console_level)
            handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
            logger.addHandler(handler)
        else:
            logger.addHandler(logging.NullHandler())
        _configured = True
    else:
        for h in logger.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(console_level)

    if log_file and log_file != _file_handler_path:
        import contextlib

        # Remove old file handler if log file changed.
        for h in list(logger.handlers):
            if isinstance(h, logging.FileHandler):
                logger.removeHandler(h)
                with contextlib.suppress(Exception):
                    h.close()
        path = Path(log_file).expanduser()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(str(path), encoding="utf-8")
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(
                logging.Formatter(
                    "%(asctime)s %(levelname)s %(name)s %(funcName)s:%(lineno)d - %(message)s"
                )
            )
            logger.addHandler(fh)
            _file_handler_path = log_file
            logger.debug("File logging enabled: %s", path)
        except OSError as exc:
            logger.warning("Could not enable log file %s: %s", log_file, exc)

    # Quiet noisy third-party loggers unless verbose.
    if not verbose:
        for noisy in ("urllib3", "yt_dlp", "yt-dlp"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    return logger


def get_logger(name: str = "pinak") -> logging.Logger:
    return logging.getLogger(name)
