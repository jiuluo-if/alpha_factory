"""List real datafields of a dataset (id / type / coverage / alphaCount / description).

Usage:
    python scripts/list_fields.py <dataset_id> [--max 200] [--grep SUBSTR]

Read-only helper for field discovery; no simulation is issued.
"""
import argparse
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from wqb_agent.client import WQBClient


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset_id")
    ap.add_argument("--max", type=int, default=200)
    ap.add_argument("--grep", default=None)
    args = ap.parse_args()

    client = WQBClient()
    fields = []
    offset = 0
    while offset < args.max:
        page, total = client.get_datafields(args.dataset_id, limit=50, offset=offset)
        if not page:
            break
        fields.extend(page)
        offset += 50
        if offset >= total:
            break

    if args.grep:
        needle = args.grep.lower()
        fields = [
            f for f in fields
            if needle in (f.get("id") or "").lower()
            or needle in (f.get("description") or "").lower()
        ]

    print(f"n={len(fields)}")
    for f in fields:
        print(
            f"{f.get('id')} | {f.get('type')} | cov={f.get('coverage')} "
            f"| alphas={f.get('alphaCount')} | {(f.get('description') or '')[:70]}"
        )


if __name__ == "__main__":
    main()
