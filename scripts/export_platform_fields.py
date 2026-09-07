"""Export the live BRAIN data-field catalog without submitting simulations.

Usage:
    python scripts/export_platform_fields.py --output-dir .wqb_state/platform_field_catalog_20260822
"""

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wqb_agent.client import WQBClient
from wqb_agent.artifacts import atomic_write_json_if_changed


DATASETS = [
    "analyst4", "fundamental2", "fundamental6", "model16", "model51",
    "news12", "news18", "option8", "option9", "pv1", "pv13", "univ1",
    "socialmedia12", "socialmedia8",
]
FIELD_TYPES = ("MATRIX", "VECTOR")


def fetch_dataset(client, dataset_id, page_size=50, max_pages=100):
    fields = []
    pages = []
    for field_type in FIELD_TYPES:
        offset = 0
        total = None
        type_count = 0
        for page_no in range(max_pages):
            page, reported_total = client.get_datafields(
                dataset_id,
                limit=page_size,
                offset=offset,
                field_type=field_type,
            )
            pages.append({
                "field_type": field_type,
                "page": page_no,
                "offset": offset,
                "reported_total": reported_total,
                "count": len(page),
            })
            fields.extend(page)
            type_count += len(page)
            total = reported_total
            if not page or type_count >= total:
                break
            offset += len(page)
        else:
            raise RuntimeError(
                f"pagination limit reached for {dataset_id}/{field_type}"
            )

    unique = []
    seen = set()
    for field in fields:
        field_id = field.get("id")
        key = (field_id, field.get("type"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(field)
    return unique, pages


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    client = WQBClient()
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    manifest = {
        "schema": 1,
        "source": "BRAIN /data-fields via WQBClient.get_datafields",
        "fetched_at": fetched_at,
        "datasets": {},
    }

    for dataset_id in DATASETS:
        fields, pages = fetch_dataset(client, dataset_id)
        payload = {
            "schema": 1,
            "dataset": dataset_id,
            "fetched_at": fetched_at,
            "field_count": len(fields),
            "pages": pages,
            "fields": fields,
        }
        path = os.path.join(args.output_dir, f"{dataset_id}.json")
        atomic_write_json_if_changed(path, payload, ignored_keys=("fetched_at",))
        manifest["datasets"][dataset_id] = {
            "file": f"{dataset_id}.json",
            "field_count": len(fields),
            "pages": len(pages),
        }
        print(f"{dataset_id}: {len(fields)} fields")

    manifest_path = os.path.join(args.output_dir, "manifest.json")
    atomic_write_json_if_changed(
        manifest_path, manifest, ignored_keys=("fetched_at",)
    )
    print(f"manifest: {manifest_path}")


if __name__ == "__main__":
    main()
