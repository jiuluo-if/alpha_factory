# Research Quality Audit — aggregate summary (2026-09-11)

The raw audit data for this review is local-only and intentionally excluded from
the public repository (see the privacy rules in `.gitignore` and
`scripts/check_repo_privacy.py`). This file keeps only the sanitized engineering
summary: problem, root cause, contract, fix and a small aggregate validation
result. It contains no local paths, field rankings, platform payloads or
per-Alpha evidence.

## Problem

The discovery keyword matcher admitted English function words as hypothesis focus
terms, so a structured research question could return semantically unrelated
coverage-only fields.

## Root cause and contract

- A focus term must be a content word; a function word is never a valid keyword
  match.
- A single machine review candidate is not evidence to change semantic
  admission, the template registry, the relationship gate, mechanism identity or
  budget selection. Those contracts stay as they are.

## Fix

- Added an English function-word stop list on the discovery keyword path, with
  two regression tests (red before the fix, green after).

## Aggregate validation

- Function words no longer select coverage-only fields.
- Small aggregate result from one local audit run: semantic admission ALLOW 59 /
  REVIEW 32 / UNKNOWN 9; field pairs REVIEW 15 / REJECT 15; mechanism identity 8
  seen keys plus 37 UNKNOWN; budget priority NORMAL 92 / LOW 8.
- The audit performed no Simulation POST, no Alpha submission and no
  `.wqb_state` write.
