"""CSV tool — parse, validate, transform, and summarise CSV data.

Used by data_eng, qa_eng, and biz_analysis teams for
data quality checks, schema validation, and lightweight ETL.
"""

import csv
import io
import json
import logging
import os
from typing import Any

log = logging.getLogger(__name__)

MAX_ROWS = int(os.getenv("CSV_MAX_ROWS", "5000"))


def parse_csv(content: str, delimiter: str = ",", has_header: bool = True) -> dict:
    """Parse CSV content into a list of dicts (or lists if no header).

    Args:
      content:    Raw CSV string
      delimiter:  Field separator (default: ,)
      has_header: First row is header (default: True)

    Returns:
      {"success": bool, "columns": list[str], "rows": list[dict], "row_count": int}
    """
    try:
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter) if has_header \
            else csv.reader(io.StringIO(content), delimiter=delimiter)
        rows = []
        for i, row in enumerate(reader):
            if i >= MAX_ROWS:
                break
            rows.append(dict(row) if has_header else list(row))
        columns = list(rows[0].keys()) if (has_header and rows) else []
        return {"success": True, "columns": columns, "rows": rows, "row_count": len(rows)}
    except Exception as e:
        return {"success": False, "columns": [], "rows": [], "row_count": 0, "error": str(e)}


def validate_csv(content: str, expected_columns: list[str],
                 required_columns: list[str] | None = None,
                 delimiter: str = ",") -> dict:
    """Validate CSV structure against an expected schema.

    Args:
      content:          Raw CSV string
      expected_columns: All expected column names
      required_columns: Columns that must not contain blanks
      delimiter:        Field separator

    Returns:
      {"passed": bool, "missing_columns": list, "extra_columns": list,
       "blank_violations": list[{"column","row_index"}], "row_count": int}
    """
    parsed = parse_csv(content, delimiter)
    if not parsed["success"]:
        return {"passed": False, "error": parsed.get("error")}

    actual_cols = set(parsed["columns"])
    expected_set = set(expected_columns)
    missing = list(expected_set - actual_cols)
    extra = list(actual_cols - expected_set)

    blank_violations = []
    if required_columns:
        for i, row in enumerate(parsed["rows"]):
            for col in required_columns:
                if col in row and not str(row[col]).strip():
                    blank_violations.append({"column": col, "row_index": i + 2})  # +2 for header + 1-based

    passed = not missing and not blank_violations
    return {
        "passed": passed,
        "missing_columns": missing,
        "extra_columns": extra,
        "blank_violations": blank_violations[:50],
        "row_count": parsed["row_count"],
    }


def describe_csv(content: str, delimiter: str = ",") -> dict:
    """Compute basic statistics for each column.

    Returns:
      {"success": bool, "row_count": int, "columns": list[{"name","non_null","null_count","unique","sample"}]}
    """
    parsed = parse_csv(content, delimiter)
    if not parsed["success"]:
        return {"success": False, "error": parsed.get("error")}

    rows = parsed["rows"]
    stats = []
    for col in parsed["columns"]:
        values = [row.get(col, "") for row in rows]
        non_null = [v for v in values if str(v).strip()]
        numeric_vals = []
        for v in non_null:
            try:
                numeric_vals.append(float(v))
            except ValueError:
                pass

        col_stat: dict[str, Any] = {
            "name": col,
            "non_null": len(non_null),
            "null_count": len(values) - len(non_null),
            "unique": len(set(non_null)),
            "sample": non_null[:3],
        }
        if numeric_vals:
            col_stat["min"] = min(numeric_vals)
            col_stat["max"] = max(numeric_vals)
            col_stat["mean"] = round(sum(numeric_vals) / len(numeric_vals), 4)
        stats.append(col_stat)

    return {"success": True, "row_count": len(rows), "columns": stats}


def csv_to_json(content: str, delimiter: str = ",") -> dict:
    """Convert CSV to a JSON array of objects.

    Returns:
      {"success": bool, "json_str": str, "row_count": int}
    """
    parsed = parse_csv(content, delimiter)
    if not parsed["success"]:
        return {"success": False, "json_str": "[]", "error": parsed.get("error")}
    return {
        "success": True,
        "json_str": json.dumps(parsed["rows"], default=str),
        "row_count": parsed["row_count"],
    }


def transform_csv(content: str, transforms: list[dict], delimiter: str = ",") -> dict:
    """Apply a list of column transforms to a CSV.

    Transform spec (each is a dict):
      {"op": "rename",  "from": "old_name", "to": "new_name"}
      {"op": "drop",    "column": "col_name"}
      {"op": "upper",   "column": "col_name"}
      {"op": "lower",   "column": "col_name"}
      {"op": "strip",   "column": "col_name"}
      {"op": "fill_na", "column": "col_name", "value": "default"}

    Returns:
      {"success": bool, "csv_str": str, "row_count": int}
    """
    parsed = parse_csv(content, delimiter)
    if not parsed["success"]:
        return {"success": False, "csv_str": "", "error": parsed.get("error")}

    rows = parsed["rows"]
    columns = list(parsed["columns"])

    for t in transforms:
        op = t.get("op", "")
        if op == "rename":
            old, new = t["from"], t["to"]
            rows = [{(new if k == old else k): v for k, v in row.items()} for row in rows]
            columns = [new if c == old else c for c in columns]
        elif op == "drop":
            col = t["column"]
            rows = [{k: v for k, v in row.items() if k != col} for row in rows]
            columns = [c for c in columns if c != col]
        elif op == "upper":
            col = t["column"]
            rows = [{k: (v.upper() if k == col else v) for k, v in row.items()} for row in rows]
        elif op == "lower":
            col = t["column"]
            rows = [{k: (v.lower() if k == col else v) for k, v in row.items()} for row in rows]
        elif op == "strip":
            col = t["column"]
            rows = [{k: (v.strip() if k == col else v) for k, v in row.items()} for row in rows]
        elif op == "fill_na":
            col, fill = t["column"], t.get("value", "")
            rows = [{k: (fill if k == col and not str(v).strip() else v) for k, v in row.items()} for row in rows]

    # Serialise back to CSV
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return {"success": True, "csv_str": out.getvalue(), "row_count": len(rows)}
