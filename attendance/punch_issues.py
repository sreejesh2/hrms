"""Detect incomplete punch patterns for dashboard + day editors."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PunchIssue:
    code: str
    label: str


def analyze_punches(punches) -> list[PunchIssue]:
    """
    Inspect ordered punches for a single day.
    Flags missing OUT, open break, single punch, empty day (caller decides workday).
    """
    punches = list(punches)
    if not punches:
        return [PunchIssue("no_punches", "No punches")]

    open_in = False
    open_break = False
    saw_in = False
    saw_out = False
    issues: list[PunchIssue] = []

    for p in punches:
        t = getattr(p, "punch_type", None) or "auto"
        if t == "auto":
            # Mirror engine pairing heuristically
            if not open_in and not open_break:
                t = "in"
            elif open_break:
                t = "break_in"
            else:
                t = "out"

        if t == "in":
            open_in = True
            saw_in = True
        elif t == "break_out":
            if open_in:
                open_in = False
            open_break = True
        elif t == "break_in":
            open_break = False
            open_in = True
        elif t == "out":
            open_in = False
            open_break = False
            saw_out = True

    if len(punches) == 1:
        issues.append(PunchIssue("single_punch", "Only one punch (likely missing Out)"))
    if saw_in and not saw_out and open_in:
        issues.append(PunchIssue("missing_out", "In punched — Out missing"))
    if open_break:
        issues.append(PunchIssue("missing_break_in", "Break out — Break in missing"))
    if open_in and saw_out is False and len(punches) >= 2 and not any(
        i.code == "missing_out" for i in issues
    ):
        # Multiple punches but still open segment
        issues.append(PunchIssue("open_segment", "Last segment still open (no Out)"))

    # De-dupe by code preserving order
    seen = set()
    unique = []
    for issue in issues:
        if issue.code not in seen:
            seen.add(issue.code)
            unique.append(issue)
    return unique


def issue_labels(punches) -> list[str]:
    return [i.label for i in analyze_punches(punches)]
