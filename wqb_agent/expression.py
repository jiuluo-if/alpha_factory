"""Single source of truth for lightweight expression identity."""

import hashlib
import json
import re


_SPACE_RE = re.compile(r"\s+")


def canonical_expression(expression):
    """Normalize only syntax-insensitive whitespace/case for identity keys."""
    return _SPACE_RE.sub("", str(expression or "")).lower()


def submission_fingerprint(expression, settings):
    """Return the stable expression/settings identity used by checkpoints."""
    canonical = json.dumps(
        {"expression": canonical_expression(expression), "settings": settings},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
