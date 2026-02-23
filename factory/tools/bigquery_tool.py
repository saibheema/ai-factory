"""BigQuery tool — run SQL queries and inspect schemas on Google BigQuery.

Used by data_eng and ml_eng teams for analytical queries,
data validation, feature engineering, and model training data prep.

Env vars:
  BIGQUERY_PROJECT   — GCP project ID (default: GCP_PROJECT env)
  BIGQUERY_LOCATION  — dataset location (default: US)
  GOOGLE_APPLICATION_CREDENTIALS — path to service account JSON (optional if
                                    running on GCE/Cloud Run with workload identity)
  BIGQUERY_MAX_ROWS  — max rows returned from queries (default: 1000)
"""

import logging
import os

log = logging.getLogger(__name__)

PROJECT = os.getenv("BIGQUERY_PROJECT") or os.getenv("GCP_PROJECT", "")
LOCATION = os.getenv("BIGQUERY_LOCATION", "US")
MAX_ROWS = int(os.getenv("BIGQUERY_MAX_ROWS", "1000"))


def _client():
    try:
        from google.cloud import bigquery
        return bigquery.Client(project=PROJECT or None)
    except ImportError:
        raise RuntimeError("google-cloud-bigquery not installed — pip install google-cloud-bigquery")


def run_query(sql: str, params: dict | None = None, max_rows: int = 0) -> dict:
    """Execute a BigQuery SQL query.

    Args:
      sql:      Standard SQL query string
      params:   Optional named query parameters {name: value}
      max_rows: Override MAX_ROWS (0 = use default)

    Returns:
      {"success": bool, "columns": list[str], "rows": list[dict], "row_count": int,
       "bytes_processed": int, "error": str|None}
    """
    from google.cloud import bigquery as bq
    limit = max_rows or MAX_ROWS
    try:
        client = _client()
        job_config = bq.QueryJobConfig()
        if params:
            job_config.query_parameters = [
                bq.ScalarQueryParameter(k, _bq_type(v), v)
                for k, v in params.items()
            ]
        job = client.query(sql, job_config=job_config, location=LOCATION)
        rows = list(job.result(max_results=limit))
        columns = [f.name for f in job.result().schema]
        data = [dict(zip(columns, row.values())) for row in rows]
        return {
            "success": True,
            "columns": columns,
            "rows": data,
            "row_count": len(data),
            "bytes_processed": job.total_bytes_processed or 0,
            "error": None,
        }
    except Exception as e:
        log.warning("BigQuery query failed: %s", e)
        return {"success": False, "columns": [], "rows": [], "row_count": 0,
                "bytes_processed": 0, "error": str(e)}


def _bq_type(value) -> str:
    if isinstance(value, bool):
        return "BOOL"
    if isinstance(value, int):
        return "INT64"
    if isinstance(value, float):
        return "FLOAT64"
    return "STRING"


def list_datasets(project: str = "") -> dict:
    """List all datasets in a project.

    Returns:
      {"success": bool, "datasets": list[str], "error": str|None}
    """
    try:
        client = _client()
        p = project or PROJECT or client.project
        datasets = [d.dataset_id for d in client.list_datasets(project=p)]
        return {"success": True, "datasets": datasets, "error": None}
    except Exception as e:
        return {"success": False, "datasets": [], "error": str(e)}


def list_tables(dataset_id: str, project: str = "") -> dict:
    """List tables in a BigQuery dataset.

    Returns:
      {"success": bool, "tables": list[str], "error": str|None}
    """
    try:
        client = _client()
        p = project or PROJECT or client.project
        tables = [t.table_id for t in client.list_tables(f"{p}.{dataset_id}")]
        return {"success": True, "tables": tables, "error": None}
    except Exception as e:
        return {"success": False, "tables": [], "error": str(e)}


def get_table_schema(dataset_id: str, table_id: str, project: str = "") -> dict:
    """Get the schema of a BigQuery table.

    Returns:
      {"success": bool, "columns": list[{"name","type","mode","description"}], "error": str|None}
    """
    try:
        client = _client()
        p = project or PROJECT or client.project
        table = client.get_table(f"{p}.{dataset_id}.{table_id}")
        columns = [
            {
                "name": f.name,
                "type": f.field_type,
                "mode": f.mode,
                "description": f.description or "",
            }
            for f in table.schema
        ]
        return {
            "success": True,
            "columns": columns,
            "num_rows": table.num_rows,
            "num_bytes": table.num_bytes,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "columns": [], "error": str(e)}


def dry_run_query(sql: str) -> dict:
    """Estimate query cost without executing it.

    Returns:
      {"success": bool, "bytes_processed": int, "estimated_gb": float, "error": str|None}
    """
    from google.cloud import bigquery as bq
    try:
        client = _client()
        job_config = bq.QueryJobConfig(dry_run=True, use_query_cache=False)
        job = client.query(sql, job_config=job_config, location=LOCATION)
        bytes_processed = job.total_bytes_processed or 0
        return {
            "success": True,
            "bytes_processed": bytes_processed,
            "estimated_gb": round(bytes_processed / 1e9, 4),
            "error": None,
        }
    except Exception as e:
        return {"success": False, "bytes_processed": 0, "estimated_gb": 0, "error": str(e)}
