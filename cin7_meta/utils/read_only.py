"""Opt-in read-only mode for the Cin7 Core API surface.

The server exposes exactly one data tool — `invoke_api_endpoint` — and it is
read+write by construction: it walks the whole Cin7 REST spec, so the same tool
that fetches a sale order can also create or void one. That is fine for agents
whose role includes mutating Cin7 (inventory-ops, support), but it makes the
tool ungrantable to an agent whose read-only boundary is absolute.

Setting `CIN7_READ_ONLY=1` in the server's environment makes every non-GET
invocation fail before any network call. Enforcement lives in two independent
places so neither is load-bearing alone:

1. `invoke_api_endpoint` checks first and returns a structured error, so the
   model gets a readable refusal on the same shape as a validation failure;
2. `Cin7Client.invoke()` raises `Cin7ReadOnlyError` — the true chokepoint that
   every request passes through, including any future caller that forgets (1).

Default is OFF, so servers that do not set the variable are unaffected.
"""

from __future__ import annotations

import os

#: The only HTTP verb permitted while read-only mode is active.
READ_ONLY_ALLOWED_METHODS = frozenset({"GET"})

#: Environment variable that turns read-only mode on.
READ_ONLY_ENV_VAR = "CIN7_READ_ONLY"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def is_read_only() -> bool:
    """Return True when the server is configured read-only.

    Read live from the environment on every call rather than cached at import,
    so tests (and any future runtime reconfiguration) can toggle it.
    """
    return os.getenv(READ_ONLY_ENV_VAR, "").strip().lower() in _TRUTHY


def method_is_allowed(method: str) -> bool:
    """Return True if `method` may be executed under the current mode."""
    if not is_read_only():
        return True
    return (method or "").strip().upper() in READ_ONLY_ALLOWED_METHODS


def refusal_message(method: str, path: str) -> str:
    """The single wording used for a read-only refusal, wherever it surfaces."""
    return (
        f"{(method or '').strip().upper()} /{(path or '').lstrip('/')} refused: this "
        f"Cin7 server runs in READ-ONLY mode ({READ_ONLY_ENV_VAR}=1), so only GET "
        f"requests are executed. This is a deliberate configuration, not a "
        f"transient failure — do not retry, and do not look for another endpoint "
        f"that achieves the same write. Report what you wanted to change and let "
        f"the human or an agent that owns Cin7 writes make the change."
    )
