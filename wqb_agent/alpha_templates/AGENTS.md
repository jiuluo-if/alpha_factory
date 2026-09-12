# Alpha template generation constraints

This directory owns the template schema, fail-closed loaders, registry, and numeric/operator audits. The tracked catalog is public synthetic material only; it must never contain production expressions, private field IDs, fixed private pairings, research evidence, or learned priors.

Private templates are loaded only from an explicit absolute constructor path, `WQB_ALPHA_TEMPLATE_CATALOG`, or `~/.wqb_alpha_factory/private/alpha_templates.toml`. Missing private input is `PRIVATE_TEMPLATE_CATALOG_MISSING`; never search cwd/parents or fall back to the public package catalog.

Every private template declares `role`, field roles/relationships, mechanism, direction and reason, expected horizon, falsification, self-correlation impact, novelty family, settings arms, and horizon profiles. Probe templates require 4–6 operator occurrences and 2–4 economic fields; controls are the only 1–3 operator / single-field exception. Horizon values are restricted to `[5, 22, 66, 120, 255]`; multi-window profiles are ordered adjacent lattice periods and are not Cartesian products.

Operator coverage is a diversity objective, never a reason to add an operator without an explicit economic mechanism. Prefer broad coverage of verified operators across independent mechanisms, while preserving arity, semantic relation, novelty, and complexity gates. Numeric literals are classified fail-closed; only declared `RESEARCH_HORIZON` slots may rotate.

`AlphaFactory` and `CandidateBuilder` consume this owner. Do not add skeletons, fixed field combinations, parameter grids, or historical success rationale elsewhere.
