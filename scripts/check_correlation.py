"""Self-correlation check: how close is an alpha to the ones you already have?

Usage:
    python scripts/check_correlation.py <alpha_id> [--prod] [--top 5]

Reads BRAIN /alphas/{id}/correlations/self (or /prod with --prod), which is
computed asynchronously (200 + Retry-After while pending), and reports the
maximum correlation plus the closest alphas.

The submission gate is read from config.json, so a *low* number here is what
makes a new alpha genuinely additive rather than a re-skin of an old one.
Exit code 0 = below threshold, 1 = above threshold, 2 = error.
"""
import argparse
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.client import WQBClient

DEFAULT_THRESHOLD = 0.5


def configured_threshold(config_path=None):
    """Read the current self-correlation gate without importing Agent state."""
    if config_path is None:
        config_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "config.json",
        )
    try:
        import json
        with open(config_path, encoding="utf-8") as handle:
            value = json.load(handle)["agent"]["quality"]["max_self_correlation"]
        value = float(value)
        if math.isfinite(value) and 0.0 < value < 1.0:
            return value
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        pass
    return DEFAULT_THRESHOLD


def fetch_correlations(client, alpha_id, kind="self", timeout_sec=300):
    """Poll correlation through the client's public read-only adapter."""
    return client.get_correlation(alpha_id, kind=kind, timeout_sec=timeout_sec)


def parse_records(payload):
    """Normalise the schema/records payload into a list of dicts."""
    if not isinstance(payload, dict):
        return [], []
    schema = payload.get("schema") or {}
    properties = schema.get("properties", []) if isinstance(schema, dict) else []
    props = [p.get("name") for p in properties if isinstance(p, dict) and p.get("name")]
    rows = []
    for rec in payload.get("records") or []:
        if isinstance(rec, (list, tuple)):
            rows.append(dict(zip(props, rec)))
    return props, rows


def numeric_correlations(payload, props, rows):
    """Return finite absolute correlation values; unresolved is not a pass."""
    corr_key = next(
        (key for key in props if "correlation" in str(key).lower()),
        None,
    )
    values = []
    if corr_key:
        for row in rows:
            try:
                value = float(row.get(corr_key))
            except (TypeError, ValueError):
                continue
            if math.isfinite(value):
                values.append(abs(value))
    if not values and isinstance(payload, dict):
        try:
            value = float(payload.get("max"))
        except (TypeError, ValueError):
            value = None
        if value is not None and math.isfinite(value):
            values.append(abs(value))
    return corr_key, values


def main():
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("alpha_id")
    ap.add_argument("--prod", action="store_true", help="check prod correlation instead of self")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--threshold", type=float, default=None,
                    help="diagnostic threshold; defaults to config.json self gate")
    args = ap.parse_args()

    kind = "prod" if args.prod else "self"
    threshold = args.threshold if args.threshold is not None else configured_threshold()
    if not math.isfinite(threshold) or not 0.0 < threshold < 1.0:
        raise ValueError("threshold must be a finite number between 0 and 1")
    client = WQBClient()
    payload = fetch_correlations(client, args.alpha_id, kind=kind)
    props, rows = parse_records(payload)
    corr_key, values = numeric_correlations(payload, props, rows)

    if not rows:
        # Histogram-style payload (min/max buckets) or no other alphas yet.
        print(f"alpha={args.alpha_id} {kind}-correlation: no pairwise records")
        print(f"  raw keys: {list(payload.keys())}  schema: {props}")
        if values:
            print(f"  max={max(values):.4f} min={payload.get('min')}")
            return 0 if max(values) < threshold else 1
        print("  correlation unresolved or malformed; fail closed")
        return 2

    if not values or not corr_key:
        print("correlation records contain no finite correlation value; fail closed",
              file=sys.stderr)
        return 2
    rows.sort(
        key=lambda row: abs(float(row.get(corr_key)))
        if row.get(corr_key) is not None and _finite_float(row.get(corr_key))
        else -1,
        reverse=True,
    )
    top = max(values)
    print(f"alpha={args.alpha_id} {kind}-correlation: max={top:.4f} (n={len(rows)}, gate<{threshold})")
    for r in rows[: args.top]:
        print("  " + "  ".join(f"{k}={r.get(k)}" for k in props))
    return 0 if abs(top) < threshold else 1


def _finite_float(value):
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
