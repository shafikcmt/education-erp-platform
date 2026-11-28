"""Cells that spreadsheets never evaluate (shared by imports and reports; Phase 8 M6).

A downloaded CSV opened in a spreadsheet must not run a formula a user typed (CSV injection):
any cell starting with ``= + - @``, a tab or a carriage return is prefixed with a quote.
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable, Sequence
from typing import Any

FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    return f"'{text}" if text.startswith(FORMULA_START) else text


def csv_text(header: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([safe_cell(h) for h in header])
    for row in rows:
        writer.writerow([safe_cell(v) for v in row])
    return out.getvalue()
