"""Backward-compatible wrapper for `cin7-meta-refresh-spec`.

The refresh logic lives in `cin7_meta/cli/refresh_spec.py` so it ships with
the package (and works from a `uvx --from git+...` install). From a clone:

    uv run python scripts/refresh_spec.py [--no-fetch]
"""

import sys
from pathlib import Path

# Make `cin7_meta` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cin7_meta.cli.refresh_spec import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
