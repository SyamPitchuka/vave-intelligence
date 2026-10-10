"""Read CSV and XLSX workbooks without assuming column order."""

from __future__ import annotations

import io
from typing import Any

import pandas as pd


def read_tabular(content: bytes, filename: str, sheet_name: str | None) -> tuple[str, list[str], list[str], list[dict[str, Any]]]:
    lower = filename.lower()
    buffer = io.BytesIO(content)
    if lower.endswith(".csv"):
        frame = pd.read_csv(buffer, dtype=object)
        sheets = ["CSV"]
        selected = "CSV"
    elif lower.endswith(".xlsx") or lower.endswith(".xlsm"):
        workbook = pd.ExcelFile(buffer)
        sheets = list(workbook.sheet_names)
        if not sheets:
            raise ValueError("The workbook has no sheets.")
        if sheet_name:
            if sheet_name not in sheets:
                raise ValueError(
                    f"Sheet '{sheet_name}' was not found. Available sheets: {', '.join(sheets)}."
                )
            selected = sheet_name
        else:
            selected = "Ideas" if "Ideas" in sheets else sheets[0]
        frame = pd.read_excel(workbook, sheet_name=selected, dtype=object)
    else:
        raise ValueError("Upload a .xlsx, .xlsm, or .csv file.")

    frame = frame.dropna(how="all")
    headers = [str(column).strip() for column in frame.columns]
    frame.columns = headers
    rows = frame.where(frame.notna(), None).to_dict(orient="records")
    return selected, sheets, headers, rows
