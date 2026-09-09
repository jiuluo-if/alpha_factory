"""Manual, read-only platform smoke checks."""

from __future__ import annotations

from .config import AppConfig


def run_readonly_smoke(client, config: AppConfig):
    if not isinstance(config, AppConfig):
        raise TypeError("run_readonly_smoke 需要已 normalize 的 AppConfig")
    result = {
        "network_write": False,
        "datasets": {"status": "UNAVAILABLE", "count": None},
        "fields": {"status": "UNAVAILABLE", "count": None},
        "existing_alphas": {"status": "NOT_REQUESTED", "count": None},
    }
    try:
        datasets = client.get_datasets()
        if isinstance(datasets, tuple):
            datasets = datasets[0]
        if not isinstance(datasets, list):
            raise ValueError("datasets response is not a list")
        result["datasets"] = {"status": "PASS", "count": len(datasets)}
    except (AttributeError, OSError, TypeError, ValueError):
        return result
    dataset_id = config.runtime.smoke_dataset
    if not dataset_id and datasets and isinstance(datasets[0], dict):
        dataset_id = datasets[0].get("id")
    if dataset_id:
        try:
            fields = client.get_datafields(dataset_id, limit=10, offset=0)
            fields = fields[0] if isinstance(fields, tuple) else fields
            if not isinstance(fields, list):
                raise ValueError("fields response is not a list")
            result["fields"] = {"status": "PASS", "count": len(fields), "dataset": dataset_id}
        except (AttributeError, OSError, TypeError, ValueError):
            pass
    return result
