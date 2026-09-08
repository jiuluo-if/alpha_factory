"""Post-simulation health check: verify a DONE alpha is a real linear
signal (y=kx) rather than a concentrated-weight noise trap (Z-shaped).

Usage:
    python scripts/check_health.py <alpha_id> [--verbose]

Reads the alpha's is block and reports:
  - longCount / shortCount (must be broadly distributed, not 1/N extreme)
  - CONCENTRATED_WEIGHT check (must PASS)
  - LOW_SUB_UNIVERSE_SHARPE check (must PASS)
Exit code 0 = healthy, 1 = noise trap / not healthy, 2 = error.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.client import WQBClient
from wqb_agent.metrics import check_health as evaluate_health, num

def check(alpha_id, verbose=False):
    c = WQBClient()
    a = c.get_alpha(alpha_id)
    isb = a.get("is") or {}
    checks = {ck.get("name"): ck for ck in (isb.get("checks") or [])}
    long_count = num(isb.get("longCount"))
    short_count = num(isb.get("shortCount"))
    health = evaluate_health(a)
    issues = list(health["reasons"])
    if long_count is None or short_count is None:
        issues.append("missing long/short count")

    if verbose:
        print(f"alpha={alpha_id}")
        print(f"  longCount={long_count} shortCount={short_count}")
        for n in ("LOW_SHARPE", "LOW_FITNESS", "LOW_TURNOVER", "HIGH_TURNOVER",
                  "CONCENTRATED_WEIGHT", "LOW_SUB_UNIVERSE_SHARPE", "SELF_CORRELATION"):
            ck = checks.get(n) or {}
            print(f"  {n}: {ck.get('result')} limit={ck.get('limit')} value={ck.get('value')}")
        print(f"  sharpe={isb.get('sharpe')} fitness={isb.get('fitness')} "
              f"turnover={isb.get('turnover')}")

    if issues:
        if verbose:
            print("  HEALTH: NOISE TRAP ->", "; ".join(issues))
        return False, issues
    if verbose:
        print("  HEALTH: OK (broad book, checks pass)")
    return True, []


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("alpha_id")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    try:
        ok, issues = check(args.alpha_id, verbose=args.verbose)
        sys.exit(0 if ok else 1)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(2)
