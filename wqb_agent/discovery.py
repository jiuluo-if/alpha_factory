"""ROLE: CORE
AGENT_RELEVANCE: HIGH
PURPOSE: Discover and profile fields using current BRAIN data or bounded cache.
READ WHEN: changing field/dataset discovery or provenance.
DO NOT USE FOR: inventing field semantics or choosing economic hypotheses.
"""

import hashlib
import json
import math
import os
import re
import time
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from .artifacts import atomic_write_json_if_changed
from .schema import CREATED_BY_VERSION, FIELDS_CACHE_VERSION

DATASET_CATEGORIES = {
    "analyst": ["analyst4"],
    "fundamental": ["fundamental2", "fundamental6"],
    "model": ["model16", "model51"],
    "news": ["news12", "news18"],
    "option": ["option8", "option9"],
    "price_volume": ["pv1", "pv13", "univ1"],
    "social": ["socialmedia12", "socialmedia8"],
}

CATEGORY_VALUE = {
    "model": 7,
    "option": 6,
    "analyst": 5,
    "fundamental": 3,
    "news": 3,
    "price_volume": 2,
    "social": 2,
}

CATEGORY_KEYWORDS = {
    "analyst": [
        "analyst", "recommendation", "target", "rating", "estimate", "eps",
        "consensus", "revision", "forecast", "broker",
    ],
    "fundamental": [
        "fundamental", "revenue", "earning", "margin", "ratio", "balance",
        "cashflow", "cash", "debt", "asset", "equity", "profit", "growth",
    ],
    "model": [
        "model", "score", "sentiment", "forecast", "prediction", "probability",
        "factor", "composite", "risk",
    ],
    "news": [
        "news", "article", "headline", "mention", "buzz", "press", "release",
    ],
    "option": [
        "option", "volatility", "implied", "iv", "put", "call", "gamma",
        "delta", "skew", "greeks", "open_interest", "oi",
    ],
    "price_volume": [
        "price", "volume", "return", "close", "open", "high", "low", "adv",
        "liquidity", "turnover", "volatility",
    ],
    "social": [
        "social", "tweet", "post", "mention", "reddit", "discussion",
        "crowdsource", "score",
    ],
}


class FieldDiscovery:
    CACHE_SCHEMA = 2

    # 拉取 MATRIX 与 VECTOR 两类字段，供提案按平台真实类型选择合法算子。
    # 用户 2026-08-20 校正：vec_avg/vec_sum 的输入必须是 VECTOR，输出为
    # 可继续参与矩阵运算的 MATRIX 信号；两类仍都要发现，但用途不同。
    FIELD_TYPES = ("MATRIX", "VECTOR")

    def __init__(self, client, pagination_limit=50, max_pages=20,
                 cache_path=None, cache_ttl_sec=7 * 24 * 3600,
                 catalog_root=None, max_alpha_count=None,
                 selection_mode="semantic", random_fraction=0.35,
                 random_seed="newwqb", platform_usage_refresh=False,
                 require_platform_alpha_count=False,
                 dataset_sampling="stratified", min_datasets=2,
                 dataset_pool=None, persist_catalog=False):
        """Field discovery with a two-level cache: in-memory (per run) and
        on-disk (cross-run, keyed by dataset id, TTL-bounded). A large
        pagination walk is only re-done when the cache is missing or stale,
        which keeps repeated rounds cheap without freezing the catalog.
        """
        self.client = client
        self.pagination_limit = pagination_limit
        self.max_pages = max_pages
        self._cache = {}
        self.cache_path = cache_path
        self.cache_ttl_sec = cache_ttl_sec
        self.max_alpha_count = max_alpha_count
        self.platform_usage_refresh = bool(platform_usage_refresh)
        self.require_platform_alpha_count = bool(require_platform_alpha_count)
        self.selection_mode = str(selection_mode or "semantic_random").lower()
        self.dataset_sampling = str(dataset_sampling or "stratified").lower()
        try:
            self.min_datasets = max(1, int(min_datasets))
        except (TypeError, ValueError):
            self.min_datasets = 2
        self.dataset_pool = self._normalize_dataset_ids(dataset_pool)
        self.persist_catalog = bool(persist_catalog)
        self.catalog_root = catalog_root or (
            os.path.dirname(cache_path) if cache_path else None
        )
        try:
            self.random_fraction = max(0.0, min(1.0, float(random_fraction)))
        except (TypeError, ValueError):
            self.random_fraction = 0.35
        self.random_seed = str(random_seed or "newwqb")
        self.last_excluded_high_usage = []
        self.last_excluded_unknown_usage = []
        self._platform_usage_provenance = None
        self._platform_usage_status = {}
        self.last_dataset_selection = {}
        self._catalog_provenance, catalog = self._load_latest_catalog(
            self.catalog_root
        )
        # 完整的本地目录是不可变字段证据源；旧 fields_cache 只作为
        # 没有目录时的跨运行回退，避免生产运行再次复制目录内容。
        self._using_catalog = self._catalog_provenance is not None
        self._disk_cache = catalog or self._load_disk_cache()

    @staticmethod
    def _normalize_dataset_ids(values):
        normalized = []
        if isinstance(values, (str, int)):
            values = [values]
        for value in values or []:
            if isinstance(value, dict):
                value = value.get("id") or value.get("name")
            if not isinstance(value, (str, int)):
                continue
            value = str(value).strip()
            if value and value not in normalized:
                normalized.append(value)
        return normalized

    def _load_latest_catalog(self, catalog_root=None):
        """Load the newest complete immutable catalog snapshot, if present."""
        root = catalog_root or (os.path.dirname(self.cache_path) if self.cache_path else None)
        if not root:
            return None, {}
        latest = None
        try:
            entries = os.scandir(root)
        except OSError:
            return None, {}
        with entries:
            for entry in entries:
                if not entry.name.startswith("platform_field_catalog_"):
                    continue
                try:
                    if not entry.is_dir():
                        continue
                except OSError:
                    continue
                directory = entry.path
                manifest_path = os.path.join(directory, "manifest.json")
                try:
                    with open(manifest_path, encoding="utf-8") as f:
                        manifest = json.load(f)
                    if not isinstance(manifest, dict):
                        continue
                    expected_scope = {
                        "instrument_type": getattr(self.client, "instrument_type", "EQUITY"),
                        "region": getattr(self.client, "region", "USA"),
                        "delay": getattr(self.client, "delay", 1),
                        "universe": getattr(self.client, "universe", "TOP3000"),
                    }
                    manifest_scope = manifest.get("scope")
                    if isinstance(manifest_scope, dict) and any(
                        manifest_scope.get(key) != value
                        for key, value in expected_scope.items()
                        if key in manifest_scope
                    ):
                        # A field id is only meaningful within the same BRAIN
                        # query scope.  Do not reuse a complete catalog from a
                        # different region/universe/instrument configuration.
                        continue
                    datasets = manifest.get("datasets") or {}
                    if (
                        not isinstance(datasets, dict)
                        or not datasets
                        or any(not isinstance(row, dict) for row in datasets.values())
                        or any(
                            not isinstance(row.get("file"), str)
                            or not os.path.isfile(os.path.join(directory, row["file"]))
                            for row in datasets.values()
                        )
                    ):
                        continue
                    catalog = {}
                    for dataset_id, row in datasets.items():
                        with open(
                            os.path.join(directory, row["file"]),
                            encoding="utf-8",
                        ) as dataset_handle:
                            dataset_payload = json.load(dataset_handle)
                        if (not isinstance(dataset_payload, dict)
                                or not isinstance(dataset_payload.get("fields"), list)):
                            raise ValueError("catalog dataset payload must contain a fields list")
                        catalog[dataset_id] = dataset_payload["fields"]
                    candidate = (entry.name, directory, manifest, catalog)
                    if latest is None or candidate[0] > latest[0]:
                        latest = candidate
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
        if latest is None:
            return None, {}
        _name, directory, manifest, datasets = latest
        return {
            "kind": "local_catalog",
            "path": os.path.abspath(directory),
            "snapshot_date": manifest.get("fetched_at"),
        }, datasets

    def source_provenance(self):
        if self._platform_usage_provenance:
            return dict(self._platform_usage_provenance)
        if self._catalog_provenance:
            return dict(self._catalog_provenance)
        return {"kind": "brain_api", "path": None, "snapshot_date": None}

    @staticmethod
    def _alpha_count(field):
        """Return a usable platform field-usage count from either API spelling."""
        if not isinstance(field, dict):
            return None
        value = field.get("alphaCount")
        if value is None:
            value = field.get("alpha_count")
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(number) or number < 0:
            return None
        return value

    def platform_dedupe_view(self):
        """Expose only live field-usage status, never Simulation/Alpha results."""
        return {
            "source": self.source_provenance(),
            "status_by_dataset": dict(self._platform_usage_status),
            "require_alpha_count": self.require_platform_alpha_count,
            "max_alpha_count": self.max_alpha_count,
        }

    def platform_usage_by_field(self, dataset_ids):
        """Return current platform counts keyed by dataset then field id."""
        result = {}
        normalized = []
        for value in dataset_ids or []:
            if isinstance(value, dict):
                value = value.get("id") or value.get("name")
            if isinstance(value, (str, int)) and str(value).strip():
                value = str(value)
                if value not in normalized:
                    normalized.append(value)
        for dataset_id in normalized:
            dataset_status = self._platform_usage_status.get(dataset_id)
            dataset_result = result.setdefault(dataset_id, {})
            for field in self._cache.get(dataset_id, self._disk_cache.get(dataset_id, [])):
                if not isinstance(field, dict) or not field.get("id"):
                    continue
                alpha_count = self._alpha_count(field) if dataset_status == "KNOWN" else None
                dataset_result[str(field["id"])] = {
                    "alpha_count": alpha_count,
                    "status": (
                        "KNOWN" if alpha_count is not None else (dataset_status or "UNKNOWN")
                    ),
                    "source": self.source_provenance().get("kind"),
                }
        return result

    def cached_datasets(self):
        """Return the active field evidence without creating another cache.

        Consumers that need manually reviewed profiles should use the same
        catalog/cache selected by discovery, otherwise a complete immutable
        catalog would still be ignored by the proposal preflight layer.
        """
        # Only the immutable catalog is safe to reuse as an already parsed
        # source. The legacy cache may be updated by a compatibility caller
        # after Agent construction, so keep its file-read semantics intact.
        return self._disk_cache if self._using_catalog else None

    def _load_disk_cache(self):
        if not self.cache_path or not os.path.exists(self.cache_path):
            return {}
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            if data.get("schema") != self.CACHE_SCHEMA:
                return {}
            saved_at = data.get("saved_at", 0)
            if time.time() - float(saved_at) > self.cache_ttl_sec:
                return {}
            datasets = data.get("datasets", {})
            return datasets if isinstance(datasets, dict) else {}
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return {}

    def _save_disk_cache(self):
        if not self.cache_path or self._using_catalog:
            return
        data = {"schema": self.CACHE_SCHEMA, "schema_version": FIELDS_CACHE_VERSION,
                "created_by_version": CREATED_BY_VERSION, "saved_at": time.time(),
                "datasets": self._disk_cache}
        try:
            # A cache heartbeat is not a new discovery artifact.  Refresh the
            # timestamp only when the dataset payload itself changed.
            atomic_write_json_if_changed(
                self.cache_path, data, ignored_keys=("saved_at",),
                indent=None,
            )
        except OSError:
            pass

    def _catalog_scope(self):
        """Return the platform query scope, without any research result data."""
        return {
            "instrument_type": getattr(self.client, "instrument_type", "EQUITY"),
            "region": getattr(self.client, "region", "USA"),
            "delay": getattr(self.client, "delay", 1),
            "universe": getattr(self.client, "universe", "TOP3000"),
        }

    def _persist_field_catalog(self, dataset_ids):
        """Write a complete metadata-only, New-York-day field snapshot.

        The catalog deliberately contains no Simulation, Alpha, metric, or
        submission payload.  Dataset files are written before the manifest, so
        an interrupted write cannot be mistaken for a complete snapshot by the
        loader.
        """
        if not self.persist_catalog or not self.catalog_root:
            return None
        normalized = self._normalize_dataset_ids(dataset_ids)
        if not normalized:
            return None
        local_day = datetime.now(UTC).astimezone(
            ZoneInfo("America/New_York")
        ).strftime("%Y%m%d")
        directory = os.path.join(
            self.catalog_root, f"platform_field_catalog_{local_day}"
        )
        try:
            os.makedirs(directory, exist_ok=True)
        except OSError:
            return None
        fetched_at = datetime.now(UTC).isoformat()
        manifest_datasets = {}
        for dataset_id in normalized:
            fields = self._cache.get(dataset_id, self._disk_cache.get(dataset_id, []))
            if not isinstance(fields, list):
                fields = []
            payload = {
                "schema": 1,
                "dataset_id": dataset_id,
                "fetched_at": fetched_at,
                "scope": self._catalog_scope(),
                "fields": fields,
            }
            encoded = json.dumps(
                fields, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            digest = hashlib.sha256(encoded).hexdigest()
            filename = f"dataset_{hashlib.sha256(dataset_id.encode('utf-8')).hexdigest()[:16]}.json"
            try:
                atomic_write_json_if_changed(
                    os.path.join(directory, filename), payload, indent=None
                )
            except OSError:
                return None
            manifest_datasets[dataset_id] = {
                "file": filename,
                "field_count": len(fields),
                "field_sha256": digest,
                "status": self._platform_usage_status.get(dataset_id, "UNKNOWN"),
            }
        manifest = {
            "schema": 1,
            "kind": "platform_field_catalog",
            "fetched_at": fetched_at,
            "local_date": local_day,
            "scope": self._catalog_scope(),
            "datasets": manifest_datasets,
        }
        try:
            atomic_write_json_if_changed(
                os.path.join(directory, "manifest.json"), manifest, indent=None
            )
        except OSError:
            return None
        return directory

    def categorize_hypothesis(self, hypothesis):
        hypothesis = hypothesis if isinstance(hypothesis, dict) else {}
        text = str(hypothesis.get("statement") or "")
        tags = hypothesis.get("tags")
        tags = tags if isinstance(tags, list) else []
        combined = " ".join([text] + [str(tag or "") for tag in tags]).lower()
        scores = {}
        for category, keywords in CATEGORY_KEYWORDS.items():
            hits = sum(1 for kw in keywords if kw in combined)
            if hits:
                scores[category] = hits
        if not scores:
            return []
        return sorted(
            scores.keys(), key=lambda c: (scores[c], CATEGORY_VALUE[c]), reverse=True
        )

    def _fields_for(self, dataset_id, persist=True, force_refresh=False):
        if not force_refresh and dataset_id in self._cache:
            return self._cache[dataset_id]
        if not force_refresh and dataset_id in self._disk_cache:
            self._cache[dataset_id] = self._disk_cache[dataset_id]
            return self._cache[dataset_id]
        collected = []
        for ftype in self.FIELD_TYPES:
            offset = 0
            total = None
            type_collected = 0
            for _ in range(self.max_pages):
                results, count = self.client.get_datafields(
                    dataset_id, limit=self.pagination_limit, offset=offset,
                    field_type=ftype,
                )
                if not isinstance(results, list):
                    # A malformed platform response is not a field catalogue;
                    # stop this dataset without turning the whole factory into
                    # an exception loop.
                    break
                collected.extend(results)
                type_collected += len(results)
                total = count
                if not results or (
                    total is not None and type_collected >= total
                ):
                    break
                offset += len(results)
        # 同一 dataset 的不同类型可能返回重复 id（极端情况），去重保序。
        seen_ids = set()
        deduped = []
        for field in collected:
            if not isinstance(field, dict):
                continue
            fid = field.get("id")
            if not isinstance(fid, (str, int)):
                continue
            fid = str(fid)
            if fid in seen_ids:
                continue
            seen_ids.add(fid)
            field = dict(field)
            field["id"] = fid
            deduped.append(field)
        self._cache[dataset_id] = deduped
        self._disk_cache[dataset_id] = deduped
        if persist:
            self._save_disk_cache()
        return deduped

    def refresh_platform_usage(self, dataset_ids):
        """Refresh field metadata so alphaCount comes from BRAIN, not old cache.

        This is intentionally a read-only `/data-fields` refresh.  It updates
        the discovery cache only; Simulation results and submitted Alpha
        payloads are never reconstructed or persisted here.
        """
        normalized = []
        for value in dataset_ids or []:
            if isinstance(value, dict):
                value = value.get("id") or value.get("name")
            if isinstance(value, (str, int)) and str(value).strip():
                value = str(value)
                if value not in normalized:
                    normalized.append(value)
        if not self.platform_usage_refresh or not normalized:
            return
        self._platform_usage_status = {}
        for dataset_id in normalized:
            try:
                fields = self._fields_for(
                    dataset_id, persist=False, force_refresh=True
                )
            except Exception:
                self._platform_usage_status[dataset_id] = "UNAVAILABLE"
                continue
            known = sum(1 for field in fields if self._alpha_count(field) is not None)
            self._platform_usage_status[dataset_id] = "KNOWN" if known else "UNKNOWN"
        self._platform_usage_provenance = {
            "kind": "brain_api",
            "path": None,
            "snapshot_date": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        self._save_disk_cache()

    def _score_field(self, field, keywords):
        haystack_id = str(field.get("id") or "").lower()
        haystack_name = str(field.get("name") or "").lower()
        haystack_desc = str(field.get("description") or "").lower()
        score = 0.0
        for kw in keywords:
            if kw in haystack_id:
                score += 3.0
            if kw in haystack_name:
                score += 2.0
            if kw in haystack_desc:
                score += 1.0
        # Catalog metadata is evidence, not a hard filter: coverage rewards
        # usable history, while prior alpha usage is a small exploration cost.
        try:
            coverage = float(field.get("coverage") or field.get("coveragePercentage") or 0.0)
            score += min(2.0, max(0.0, coverage / 100.0))
        except (TypeError, ValueError):
            pass
        try:
            alpha_count = float(self._alpha_count(field))
            score -= min(1.5, math.log1p(max(0.0, alpha_count)) / 10.0)
        except (TypeError, ValueError):
            pass
        return score

    @staticmethod
    def _dataset_id(field):
        dataset = field.get("dataset")
        if isinstance(dataset, dict):
            dataset = dataset.get("id") or dataset.get("name")
        return str(dataset) if isinstance(dataset, (str, int)) else None

    @staticmethod
    def _keywords_from_hypothesis(hypothesis, limit=6):
        hypothesis = hypothesis if isinstance(hypothesis, dict) else {}
        ordered = []
        seen = set()

        def push(word):
            w = str(word or "").lower()
            if len(w) > 2 and w not in seen and w not in _STOPWORDS:
                seen.add(w)
                ordered.append(w)

        tags = hypothesis.get("tags")
        tags = tags if isinstance(tags, list) else []
        for tag in tags:
            for piece in re.split(r"[^a-z0-9]+", str(tag or "").lower()):
                if piece:
                    push(piece)
        for piece in re.split(
            r"[^a-z0-9]+", str(hypothesis.get("statement") or "").lower()
        ):
            if piece:
                push(piece)
        return ordered[:limit]

    def discover(self, hypothesis, target_count=6):
        hypothesis = hypothesis if isinstance(hypothesis, dict) else {}
        try:
            target_count = max(0, int(target_count))
        except (TypeError, ValueError):
            target_count = 0
        self.last_excluded_high_usage = []
        self.last_excluded_unknown_usage = []
        keywords = self._keywords_from_hypothesis(hypothesis)
        chosen = []
        seen = set()

        # Preferred datasets first (carried over from memory: hypothesis
        # "datasets" / "dataset_hints" or next-idea datasets). Only fields
        # matching the hypothesis keywords are kept, so the same dataset
        # can be reused across rounds without repeating formulas.
        preferred_ids = self._normalize_dataset_ids(
            hypothesis.get("datasets") or hypothesis.get("dataset_hints") or []
        )
        categories = self.categorize_hypothesis(hypothesis)
        dataset_ids = list(preferred_ids)
        if not dataset_ids:
            dataset_ids.extend(self.dataset_pool)
            for category in categories:
                for dataset_id in DATASET_CATEGORIES[category]:
                    if dataset_id not in dataset_ids:
                        dataset_ids.append(dataset_id)
            if self.selection_mode in {"random", "semantic_random", "broad"}:
                for dataset_group in DATASET_CATEGORIES.values():
                    for dataset_id in dataset_group:
                        if dataset_id not in dataset_ids:
                            dataset_ids.append(dataset_id)
        if not dataset_ids:
            dataset_ids = [
                dataset_id
                for dataset_group in DATASET_CATEGORIES.values()
                for dataset_id in dataset_group
            ]
        self.refresh_platform_usage(dataset_ids)

        ranked_by_dataset = {}
        for dataset_id in dataset_ids:
            category = next(
                (name for name, values in DATASET_CATEGORIES.items()
                 if dataset_id in values),
                None,
            )
            ranked_by_dataset[dataset_id] = self._rank_fields_for_dataset(
                dataset_id, keywords, category, hypothesis
            )
        round_no = hypothesis.get("_round", 0)
        ordered_datasets = sorted(
            dataset_ids,
            key=lambda dataset_id: hashlib.sha256(
                f"{self.random_seed}|{round_no}|{dataset_id}".encode()
            ).hexdigest(),
        )
        available = [dataset_id for dataset_id in ordered_datasets
                     if ranked_by_dataset.get(dataset_id)]
        # An explicitly named single dataset remains an intentional scope.  A
        # multi-dataset scope, category scope, or configured pool is sampled
        # round-robin so semantic ranking cannot consume the whole batch from
        # the first dataset.
        stratified = (
            self.dataset_sampling in {"stratified", "random", "semantic_random", "broad"}
            and len(available) > 1
            and len(preferred_ids) != 1
        )
        offsets = {dataset_id: 0 for dataset_id in available}
        while len(chosen) < target_count and available:
            progressed = False
            for dataset_id in available:
                if len(chosen) >= target_count:
                    break
                ranked = ranked_by_dataset[dataset_id]
                index = offsets[dataset_id]
                if index >= len(ranked):
                    continue
                _rank, score, field, actual_dataset = ranked[index]
                offsets[dataset_id] = index + 1
                key = (actual_dataset, str(field.get("id")))
                if key in seen:
                    continue
                chosen.append(self._profile_from_field(
                    actual_dataset, field, score, category=(
                        next((name for name, values in DATASET_CATEGORIES.items()
                              if actual_dataset in values), "preferred")
                    ),
                ))
                seen.add(key)
                progressed = True
            if not stratified and chosen:
                # Sequential mode is retained only for an explicitly selected
                # single dataset or a caller that asks for it.
                if len(chosen) >= target_count:
                    break
                if len(preferred_ids) != 1:
                    # In non-stratified mode, consume the first available pool.
                    available = available[:1]
            if not progressed:
                break
        selected_counts = {}
        for field in chosen:
            dataset_id = str(field.get("dataset"))
            selected_counts[dataset_id] = selected_counts.get(dataset_id, 0) + 1
        self.last_dataset_selection = {
            "strategy": "stratified_round_robin" if stratified else "scoped_ranked",
            "seed": self.random_seed,
            "round": round_no,
            "pool": list(dataset_ids),
            "ordered_pool": ordered_datasets,
            "available": available,
            "min_datasets": self.min_datasets,
            "selected_counts": selected_counts,
            "available_counts": {
                dataset_id: len(ranked_by_dataset.get(dataset_id, []))
                for dataset_id in ordered_datasets
            },
            "rejections": {
                "high_usage": list(self.last_excluded_high_usage),
                "unknown_usage": list(self.last_excluded_unknown_usage),
            },
        }
        self._persist_field_catalog(dataset_ids)
        # A discovery pass may touch several datasets. Persist the merged
        # cache once, after all fields for this pass have been collected.
        self._save_disk_cache()
        return chosen

    def _rank_fields_for_dataset(self, dataset_id, keywords, category, hypothesis):
        try:
            fields = self._fields_for(dataset_id, persist=False)
        except Exception:
            return []
        ranked = []
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("id"), (str, int)):
                continue
            field_id = str(field["id"])
            actual_dataset = self._dataset_id(field) or str(dataset_id)
            alpha_count = self._alpha_count(field)
            if self.max_alpha_count is not None and alpha_count is None and self.require_platform_alpha_count:
                self.last_excluded_unknown_usage.append({
                    "id": field_id,
                    "dataset": actual_dataset,
                    "reason": "platform alphaCount unavailable",
                })
                continue
            if self.max_alpha_count is not None and alpha_count is not None:
                try:
                    if float(alpha_count) > float(self.max_alpha_count):
                        self.last_excluded_high_usage.append({
                            "id": field_id, "alpha_count": alpha_count,
                            "dataset": actual_dataset,
                        })
                        continue
                except (TypeError, ValueError):
                    pass
            score = self._score_field(field, keywords)
            if score <= 0 and self.selection_mode not in {"random", "semantic_random", "broad"}:
                continue
            token = "|".join((self.random_seed, str(hypothesis or {}),
                              str(actual_dataset), field_id))
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            noise = int(digest[:12], 16) / float(16 ** 12)
            if self.selection_mode == "random":
                rank = noise
            elif self.selection_mode in {"semantic_random", "broad"}:
                rank = ((1.0 - self.random_fraction) * score
                        + self.random_fraction * noise)
            else:
                rank = score
            ranked.append((rank, score, field, actual_dataset))
        ranked.sort(key=lambda item: (-item[0], -item[1], str(item[2].get("id"))))
        return ranked

    def _profile_from_field(self, dataset_id, field, score, category):
        field_id = str(field.get("id"))
        alpha_count = self._alpha_count(field)
        return {
            "id": field_id,
            "name": field.get("name") or field.get("description") or field_id,
            "description": field.get("description") or "",
            "coverage": (
                field.get("coverage") or field.get("coveragePercentage")
                or field.get("coverage_percent")
            ),
            "alpha_count": alpha_count,
            "frequency": (
                field.get("frequency") or field.get("dataFrequency")
                or field.get("updateFrequency")
            ),
            "semantic_status": "KNOWN" if field.get("description") else "UNKNOWN",
            "category": category or "preferred",
            "dataset": str(dataset_id),
            "type": field.get("type"),
            "match_score": score,
            "field_source": self.source_provenance(),
            "platform_dedupe": {
                "source": self.source_provenance().get("kind"),
                "status": "KNOWN" if alpha_count is not None else "UNKNOWN",
                "alpha_count": alpha_count,
            },
        }

    def _collect_from_dataset(
        self, dataset_id, keywords, chosen, seen, target_count, category,
        hypothesis=None,
    ):
        ranked = self._rank_fields_for_dataset(dataset_id, keywords, category, hypothesis)
        for _rank, score, field, actual_dataset in ranked:
            if len(chosen) >= target_count:
                break
            key = (actual_dataset, str(field.get("id")))
            if key in seen:
                continue
            chosen.append(self._profile_from_field(actual_dataset, field, score, category))
            seen.add(key)


_STOPWORDS = {
    "with", "from", "that", "this", "will", "have", "been", "being",
    "into", "over", "under", "across", "about", "their", "there", "which",
    "while", "using", "should", "would", "where", "when", "after", "before",
}
