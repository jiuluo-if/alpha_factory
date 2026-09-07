"""Pure, bounded expression mutations shared by candidate and validation.

This module deliberately has no Agent, Simulator, client, filesystem, or
state dependency.  Keeping these transformations here prevents the
validation planner from importing the production candidate builder merely to
reuse deterministic string helpers.
"""

import re


# Knowledge-backed windows only; this is a finite mutation vocabulary rather
# than a parameter sweep.
WINDOW_STEPS = [5, 10, 20, 60, 63, 84, 126, 252]

_TS_OP_PATTERN = re.compile(
    r"(ts_(?:rank|mean|std_dev|sum|delta|min|max|zscore|av_diff)\([^,]+,\s*)(\d+)"
)


def _swap_field(expression, old_field, new_field):
    """Replace one field using token boundaries, never a textual prefix."""
    if not old_field or new_field == old_field:
        return None
    pattern = re.compile(r"\b" + re.escape(old_field) + r"\b")
    swapped = pattern.sub(lambda _match: new_field, expression)
    if swapped == expression:
        return None
    return swapped


def _window_change(expression, direction):
    """Move the last recognized time-series window by one finite step."""
    found = None
    for match in _TS_OP_PATTERN.finditer(expression or ""):
        found = match
    if not found:
        return None
    current = int(found.group(2))
    if direction > 0:
        target = next(
            (window for window in WINDOW_STEPS if window > current),
            WINDOW_STEPS[-1],
        )
    else:
        smaller = [window for window in WINDOW_STEPS if window < current]
        target = smaller[-1] if smaller else current
    if target == current:
        return None
    return (
        expression[: found.start()]
        + found.group(1)
        + str(target)
        + expression[found.end():]
    )


def _relative_window_changes(expression, ratios=(0.75, 1.25)):
    """Return bounded relative window perturbations, not a fixed +/- 1 sweep."""
    found = None
    for match in _TS_OP_PATTERN.finditer(expression or ""):
        found = match
    if not found:
        return []
    current = int(found.group(2))
    candidates = []
    for ratio in ratios:
        target_value = max(1, round(current * float(ratio)))
        # Keep the relative perturbation itself.  Snapping to a sparse
        # catalog can collapse a 25% change back to the original window.
        target = target_value
        if target != current and target not in candidates:
            candidates.append(target)
    return [
        expression[: found.start()] + found.group(1) + str(target) + expression[found.end():]
        for target in candidates
    ]
