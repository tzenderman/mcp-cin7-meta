"""Record an MCP-client-flagged issue to a single structured log file.

Each call appends one `ISSUE_REPORT <json>` line to two places:

1. stderr via the module logger — captured by Render's log stream in prod and
   visible to anyone watching the server's stderr.
2. The file at `ISSUE_REPORT_PATH` (default `./data/issue_reports.log`).
   On a developer laptop or a Render service with a persistent disk this is
   the durable record. The format matches the stderr line exactly, so the
   same `grep ISSUE_REPORT` works against either source.

If the file write fails the call still returns successfully; the stderr line
carries the full report so nothing is lost.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

from cin7_meta import __version__

logger = logging.getLogger(__name__)

DEFAULT_PATH = "./data/issue_reports.log"


REDACTED = "[REDACTED]"

# Keys whose values are dropped wherever they appear in the payload. The second
# line covers Cin7's own credentials (api-auth-accountid /
# api-auth-applicationkey headers, CIN7_ACCOUNT_ID env), which the generic
# names miss. It is deliberately narrower than "accountid": Cin7 bodies carry
# real fields like AccountID and BankAccountId that must survive. There is no
# in-text pattern: the credentials are plain UUIDs, the same shape as the Cin7
# record IDs reports need to keep.
_SECRET_KEY = re.compile(
    r"token|secret|password|passwd|authorization|api[_-]?key|cookie|credential"
    r"|application[_-]?key|api[_-]auth[_-]|cin7[_-]account[_-]?id",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")


def _redact(value):
    """Best-effort scrub of credentials and email addresses before persisting.

    Reports carry model-supplied tool arguments and response excerpts, which can
    contain secrets or customer PII. Names/addresses can't be detected reliably;
    this covers credentials and emails.
    """
    if isinstance(value, dict):
        return {
            k: REDACTED if isinstance(k, str) and _SECRET_KEY.search(k) else _redact(v)
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact(v) for v in value]
    if isinstance(value, str):
        return _EMAIL.sub(REDACTED, value)
    return value


def _new_report_id() -> str:
    return "rpt_" + secrets.token_hex(4)


def record_issue(payload: dict) -> tuple[str, bool]:
    """Persist an issue report.

    Args:
        payload: Caller-supplied fields. Server-stamped metadata
            (`report_id`, `timestamp`, `server`, `server_version`,
            `python_version`) takes precedence over identically-named caller keys.

    Returns:
        `(report_id, wrote_to_file)` — `wrote_to_file` is False if the file
        append failed (e.g. permission denied or read-only filesystem).
    """
    enriched = {
        **_redact(payload),
        "report_id": _new_report_id(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "server": "mcp-cin7-meta",
        "server_version": __version__,
        "python_version": sys.version.split()[0],
    }

    line = "ISSUE_REPORT " + json.dumps(enriched, default=str)
    logger.info(line)

    path = os.getenv("ISSUE_REPORT_PATH", DEFAULT_PATH)
    wrote = False
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        wrote = True
    except OSError as e:
        logger.warning("ISSUE_REPORT file write failed (%s): %s", path, e)

    return enriched["report_id"], wrote
