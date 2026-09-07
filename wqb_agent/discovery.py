import hashlib
import json
import math
import os
import re
import time

from .artifacts import atomic_write_json_if_changed
from .schema import FIELDS_CACHE_VERSION, CREATED_BY_VERSION

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
                 random_seed="newwqb"):
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
        self.selection_mode = str(selection_mode or "semantic_random").lower()
        try:
            self.random_fraction = max(0.0, min(1.0, float(random_fraction)))
        except (TypeError, ValueError):
            self.random_fraction = 0.35
        self.random_seed = str(random_seed or "newwqb")
        self.last_excluded_high_usage = []
        self._catalog_provenance, catalog = self._load_latest_catalog(catalog_root)
        # 完整的本地目录是不可变字段证据源；旧 fields_cache 只作为
        # 没有目录时的跨运行回退，避免生产运行再次复制目录内容。
        self._using_catalog = self._catalog_provenance is not None
        self._disk_cache = catalog or self._load_disk_cache()

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
        if self._catalog_provenance:
            return dict(self._catalog_provenance)
        return {"kind": "brain_api", "path": None, "snapshot_date": None}

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

    def _fields_for(self, dataset_id, persist=True):
        if dataset_id in self._cache:
            return self._cache[dataset_id]
        if dataset_id in self._disk_cache:
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
            alpha_count = float(field.get("alphaCount"))
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
        keywords = self._keywords_from_hypothesis(hypothesis)
        chosen = []
        seen = set()

        # Preferred datasets first (carried over from memory: hypothesis
        # "datasets" / "dataset_hints" or next-idea datasets). Only fields
        # matching the hypothesis keywords are kept, so the same dataset
        # can be reused across rounds without repeating formulas.
        preferred = hypothesis.get("datasets") or hypothesis.get("dataset_hints") or []
        preferred = preferred if isinstance(preferred, list) else []
        preferred_ids = []
        for raw_dataset_id in preferred:
            dataset_id = raw_dataset_id
            if isinstance(dataset_id, dict):
                dataset_id = dataset_id.get("id") or dataset_id.get("name")
            if not isinstance(dataset_id, (str, int)):
                continue
            dataset_id = str(dataset_id)
            if dataset_id not in preferred_ids:
                preferred_ids.append(dataset_id)
        for dataset_id in preferred_ids:
            if len(chosen) >= target_count:
                break
            self._collect_from_dataset(
                dataset_id, keywords, chosen, seen, target_count, category=None,
                hypothesis=hypothesis,
            )

        if len(chosen) < target_count:
            categories = self.categorize_hypothesis(hypothesis)
            for category in categories:
                if len(chosen) >= target_count:
                    break
                for dataset_id in DATASET_CATEGORIES[category]:
                    if dataset_id in preferred_ids:
                        continue
                    if len(chosen) >= target_count:
                        break
                    self._collect_from_dataset(
                        dataset_id, keywords, chosen, seen, target_count, category,
                        hypothesis=hypothesis,
                    )
        if len(chosen) < target_count and self.selection_mode in {
            "random", "semantic_random", "broad"
        }:
            for category, dataset_ids in DATASET_CATEGORIES.items():
                for dataset_id in dataset_ids:
                    if len(chosen) >= target_count:
                        break
                    if dataset_id in preferred_ids:
                        continue
                    self._collect_from_dataset(
                        dataset_id, keywords, chosen, seen, target_count, category,
                        hypothesis=hypothesis,
                    )
        # A discovery pass may touch several datasets. Persist the merged
        # cache once, after all fields for this pass have been collected.
        self._save_disk_cache()
        return chosen

    def _collect_from_dataset(
        self, dataset_id, keywords, chosen, seen, target_count, category,
        hypothesis=None,
    ):
        try:
            fields = self._fields_for(dataset_id, persist=False)
        except Exception:
            return
        ranked = []
        for field in fields:
            if not isinstance(field, dict) or not isinstance(field.get("id"), (str, int)):
                continue  # a field without an id cannot be proposed or audited
            field_id = str(field.get("id"))
            if field_id in seen:
                continue
            alpha_count = field.get("alphaCount")
            if self.max_alpha_count is not None and alpha_count is not None:
                try:
                    if float(alpha_count) > float(self.max_alpha_count):
                        self.last_excluded_high_usage.append({
                            "id": field_id, "alpha_count": alpha_count,
                            "dataset": self._dataset_id(field) or dataset_id,
                        })
                        continue
                except (TypeError, ValueError):
                    pass
            score = self._score_field(field, keywords)
            if score <= 0 and self.selection_mode not in {
                "random", "semantic_random", "broad"
            }:
                continue
            token = "|".join((self.random_seed, str(hypothesis or {}),
                              str(dataset_id), field_id))
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            noise = int(digest[:12], 16) / float(16 ** 12)
            if self.selection_mode == "random":
                rank = noise
            elif self.selection_mode in {"semantic_random", "broad"}:
                rank = ((1.0 - self.random_fraction) * score
                        + self.random_fraction * noise)
            else:
                rank = score
            ranked.append((rank, score, field))
        ranked.sort(key=lambda x: (-x[0], -x[1], str(x[2].get("id"))))
        for _rank, score, field in ranked:
            if len(chosen) >= target_count:
                break
            field_id = str(field.get("id"))
            chosen.append(
                {
                    "id": field_id,
                    "name": field.get("name") or field.get("description") or field_id,
                    # Keep the platform metadata intact.  The proposal author
                    # needs evidence for a field interpretation; reducing
                    # discovery to an id/name makes a post-hoc story easy.
                    "description": field.get("description") or "",
                    "coverage": (
                        field.get("coverage")
                        or field.get("coveragePercentage")
                        or field.get("coverage_percent")
                    ),
                    "alpha_count": field.get("alphaCount"),
                    # Keep the API's cadence verbatim (including None).  A
                    # missing platform value must be visible to the proposal
                    # author, never silently inferred from a window choice.
                    "frequency": (
                        field.get("frequency")
                        or field.get("dataFrequency")
                        or field.get("updateFrequency")
                    ),
                    "semantic_status": (
                        "KNOWN" if field.get("description") else "UNKNOWN"
                    ),
                    "category": category or "preferred",
                    "dataset": self._dataset_id(field) or dataset_id,
                    # 平台字段类型（MATRIX/VECTOR/...）：提案前置类型校验
                    # 使用它阻止 vec_* 误套 MATRIX 字段。
                    "type": field.get("type"),
                    "match_score": score,
                    "field_source": self.source_provenance(),
                }
            )
            seen.add(field_id)


_STOPWORDS = {
    "with", "from", "that", "this", "will", "have", "been", "being",
    "into", "over", "under", "across", "about", "their", "there", "which",
    "while", "using", "should", "would", "where", "when", "after", "before",
}
