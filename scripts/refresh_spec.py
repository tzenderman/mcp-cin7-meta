"""Refresh the vendored Cin7 Core API Blueprint and derived JSON catalog.

Usage:

    uv run python scripts/refresh_spec.py [--no-fetch]

Writes:

    cin7_meta/spec/cin7_v2.apib   # raw API Blueprint (1.7MB+)
    cin7_meta/spec/cin7_v2.json   # normalized catalog the runtime indexes

Re-run any time the Cin7 Core API changes (new endpoints, new params,
schema changes). The fetch step requires no Cin7 credentials — the Apiary
URL is publicly accessible.

Pass `--no-fetch` to skip the network call and re-parse the existing
`.apib` file (useful when iterating on the parser).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

# Make `cin7_meta` importable when running this script directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cin7_meta.utils.logging import setup_logging
from cin7_meta.utils.spec_parser import parse_apib

logger = logging.getLogger("refresh_spec")

SPEC_DIR = Path(__file__).resolve().parent.parent / "cin7_meta" / "spec"
APIB_PATH = SPEC_DIR / "cin7_v2.apib"
JSON_PATH = SPEC_DIR / "cin7_v2.json"
SOURCE_URL = "https://dearinventory.docs.apiary.io/api-description-document"


def fetch_apib() -> str:
    logger.info("Fetching API Blueprint from %s", SOURCE_URL)
    with httpx.Client(timeout=httpx.Timeout(60.0, connect=10.0), follow_redirects=True) as client:
        response = client.get(SOURCE_URL)
    response.raise_for_status()
    content = response.text
    if not content.startswith("FORMAT:") and "FORMAT: 1A" not in content[:200]:
        raise RuntimeError(
            f"Unexpected response from {SOURCE_URL!r}: not API Blueprint format. "
            f"First 200 chars: {content[:200]!r}"
        )
    logger.info("Fetched %d bytes", len(content))
    return content


def write_apib(text: str) -> None:
    SPEC_DIR.mkdir(parents=True, exist_ok=True)
    APIB_PATH.write_text(text)
    logger.info("Wrote %s (%d bytes)", APIB_PATH, APIB_PATH.stat().st_size)


def parse_and_write_catalog() -> dict:
    text = APIB_PATH.read_text()
    catalog = parse_apib(text)
    catalog["generated_at"] = datetime.now(timezone.utc).isoformat()
    catalog["source"] = SOURCE_URL
    JSON_PATH.write_text(json.dumps(catalog, indent=2, sort_keys=False))
    logger.info(
        "Parsed %d endpoints across %d groups. %d parser warnings.",
        len(catalog["endpoints"]),
        len({e["group"] for e in catalog["endpoints"]}),
        len(catalog["parser_warnings"]),
    )
    logger.info("Wrote %s (%d bytes)", JSON_PATH, JSON_PATH.stat().st_size)
    return catalog


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip the network fetch and re-parse the existing .apib file",
    )
    args = parser.parse_args()

    setup_logging()

    if not args.no_fetch:
        text = fetch_apib()
        write_apib(text)
    elif not APIB_PATH.exists():
        raise FileNotFoundError(
            f"--no-fetch passed but {APIB_PATH} does not exist. Run without --no-fetch first."
        )

    parse_and_write_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
