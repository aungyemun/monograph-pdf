"""Allow `python -m app` from project root."""

from __future__ import annotations

from app.bootstrap import main

if __name__ == "__main__":
    raise SystemExit(main())
