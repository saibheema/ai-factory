"""SQL tool — execute queries against PostgreSQL and return structured results.

Useful for database_eng (schema inspection), data_eng (data validation),
ml_eng (feature store queries), and qa_eng (data quality checks).

Env vars:
  DB_HOST      — default: localhost
  DB_PORT      — default: 5432
  DB_NAME      — default: factory
  DB_USER      — default: factory_user
  DB_PASSWORD  — default: (empty)
  DB_MAX_ROWS  — max rows to return (default: 200)
"""

import logging
import os

log = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "5432"))
DB_NAME = os.getenv("DB_NAME", "factory")
DB_USER = os.getenv("DB_USER", "factory_user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
MAX_ROWS = int(os.getenv("DB_MAX_ROWS", "200"))


def _connect():
    import psycopg2  # type: ignore[import]
    return psycopg2.connect(
        host=DB_HOST, port=DB_PORT, dbname=DB_NAME,
        user=DB_USER, password=DB_PASSWORD, connect_timeout=10,
    )


def execute_query(sql: str, params: list | None = None) -> dict:
    """Execute a SELECT query and return rows as list of dicts.

    Returns:
      {"success": bool, "columns": list[str], "rows": list[list], "row_count": int, "error": str|None}
    """
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute(sql, params or [])
        columns = [d[0] for d in (cur.description or [])]
        rows = cur.fetchmany(MAX_ROWS)
        cur.close()
        conn.close()
        return {
            "success": True,
            "columns": columns,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "error": None,
        }
    except Exception as e:
        log.warning("SQL query failed: %s", e)
        return {"success": False, "columns": [], "rows": [], "row_count": 0, "error": str(e)}


def execute_ddl(sql: str) -> dict:
    """Execute DDL/DML (CREATE TABLE, INSERT, UPDATE, ALTER, etc.).

    Returns:
      {"success": bool, "status_message": str, "error": str|None}
    """
    try:
        conn = _connect()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        msg = cur.statusmessage or "OK"
        cur.close()
        conn.close()
        return {"success": True, "status_message": msg, "error": None}
    except Exception as e:
        log.warning("DDL execution failed: %s", e)
        return {"success": False, "status_message": "", "error": str(e)}


def describe_table(table_name: str, schema: str = "public") -> dict:
    """Return column definitions for a table.

    Returns:
      {"success": bool, "columns": list[dict], "error": str|None}
    """
    sql = """
        SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
    """
    result = execute_query(sql, [schema, table_name])
    if not result["success"]:
        return result
    cols = [
        {"name": r[0], "type": r[1], "nullable": r[2] == "YES", "default": r[3]}
        for r in result["rows"]
    ]
    return {"success": True, "columns": cols, "error": None}


def list_tables(schema: str = "public") -> dict:
    """List all tables in a schema.

    Returns:
      {"success": bool, "tables": list[str], "error": str|None}
    """
    sql = """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name
    """
    result = execute_query(sql, [schema])
    if not result["success"]:
        return result
    return {"success": True, "tables": [r[0] for r in result["rows"]], "error": None}


def validate_schema(expected_columns: dict[str, str], table_name: str, schema: str = "public") -> dict:
    """Check that a table has the expected columns with correct types.

    Args:
      expected_columns: {"column_name": "expected_type_substring", ...}

    Returns:
      {"passed": bool, "mismatches": list[dict], "missing": list[str]}
    """
    result = describe_table(table_name, schema)
    if not result["success"]:
        return {"passed": False, "mismatches": [], "missing": list(expected_columns.keys()),
                "error": result.get("error")}
    actual = {c["name"]: c["type"] for c in result["columns"]}
    mismatches = []
    missing = []
    for col, expected_type in expected_columns.items():
        if col not in actual:
            missing.append(col)
        elif expected_type.lower() not in actual[col].lower():
            mismatches.append({"column": col, "expected": expected_type, "actual": actual[col]})
    return {"passed": not mismatches and not missing, "mismatches": mismatches, "missing": missing}
