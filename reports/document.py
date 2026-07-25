"""Shared report document model — consumed by Excel and PDF exporters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence


@dataclass
class ReportSheet:
    name: str
    headers: Sequence[str]
    rows: list[Sequence[Any]]
    money_cols: Sequence[int] = field(default_factory=list)


@dataclass
class ReportDocument:
    title: str
    subtitle: str
    filename: str
    sheets: list[ReportSheet]
