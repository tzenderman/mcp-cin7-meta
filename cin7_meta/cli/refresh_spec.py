"""Refresh the Cin7 Core API Blueprint and derived JSON catalog.

Usage:

    cin7-meta-refresh-spec [--no-fetch]

(or, from a clone: `uv run python scripts/refresh_spec.py [--no-fetch]`)

Writes `cin7_v2.apib` (raw API Blueprint) and `cin7_v2.json` (the normalized
catalog the runtime indexes) to `CIN7_SPEC_DIR` when that env var is set,
otherwise to the package's own `cin7_meta/spec/` directory.

The fetch needs no Cin7 credentials — the Apiary URL is public. Pass
`--no-fetch` to re-parse the existing `.apib` in the output directory without
a network call (useful when iterating on the parser).
"""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import httpx

from cin7_meta.utils.logging import setup_logging
from cin7_meta.utils.spec_loader import SPEC_DIR, SPEC_FILENAME, spec_dir_from_env
from cin7_meta.utils.spec_parser import parse_apib

logger = logging.getLogger("refresh_spec")

APIB_FILENAME = "cin7_v2.apib"
SOURCE_URL = "https://dearinventory.docs.apiary.io/api-description-document"


def output_dir() -> Path:
    """`CIN7_SPEC_DIR` if set, else the packaged spec directory."""
    return spec_dir_from_env() or SPEC_DIR


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


def write_apib(text: str, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / APIB_FILENAME
    # Explicit UTF-8: the spec contains non-ASCII and Windows defaults to cp1252.
    path.write_text(text, encoding="utf-8")
    logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)
    return path


def parse_and_write_catalog(out_dir: Path) -> dict:
    text = (out_dir / APIB_FILENAME).read_text(encoding="utf-8")
    catalog = parse_apib(text)
    catalog["generated_at"] = datetime.now(timezone.utc).isoformat()
    catalog["source"] = SOURCE_URL
    path = out_dir / SPEC_FILENAME
    path.write_text(json.dumps(catalog, indent=2, sort_keys=False), encoding="utf-8")
    logger.info(
        "Parsed %d endpoints across %d groups. %d parser warnings.",
        len(catalog["endpoints"]),
        len({e["group"] for e in catalog["endpoints"]}),
        len(catalog["parser_warnings"]),
    )
    logger.info("Wrote %s (%d bytes)", path, path.stat().st_size)
    return catalog


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cin7-meta-refresh-spec",
        description="Refresh the Cin7 Core API Blueprint and normalized JSON catalog.",
    )
    parser.add_argument(
        "--no-fetch",
        action="store_true",
        help="Skip the network fetch and re-parse the existing .apib file",
    )
    args = parser.parse_args(argv)

    setup_logging()
    out_dir = output_dir()
    logger.info("Spec output directory: %s", out_dir)

    if not args.no_fetch:
        write_apib(fetch_apib(), out_dir)
    elif not (out_dir / APIB_FILENAME).exists():
        raise FileNotFoundError(
            f"--no-fetch passed but {out_dir / APIB_FILENAME} does not exist. "
            "Run without --no-fetch first."
        )

    parse_and_write_catalog(out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
