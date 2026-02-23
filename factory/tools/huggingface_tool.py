"""HuggingFace tool — model and dataset discovery on the Hugging Face Hub.

Used by ml_eng teams to search for pre-trained models, datasets,
and to retrieve model cards, evaluation metrics, and download links.

Env vars:
  HF_TOKEN     — HuggingFace API token (optional, needed for private repos)
  HF_ENDPOINT  — custom endpoint (default: https://huggingface.co)
"""

import logging
import os

import httpx

log = logging.getLogger(__name__)

HF_TOKEN = os.getenv("HF_TOKEN", "")
HF_API = "https://huggingface.co/api"
TIMEOUT = 15


def _headers() -> dict:
    h = {"Accept": "application/json"}
    if HF_TOKEN:
        h["Authorization"] = f"Bearer {HF_TOKEN}"
    return h


def search_models(query: str, task: str = "", limit: int = 10) -> dict:
    """Search HuggingFace for models by keyword and/or task.

    Args:
      query:  Keyword search (e.g. "sentence similarity", "code generation")
      task:   Pipeline task filter (e.g. "text-generation", "image-classification")
      limit:  Max models to return (default 10)

    Common task values: text-generation, text-classification, token-classification,
    question-answering, summarization, translation, fill-mask, image-classification,
    object-detection, automatic-speech-recognition, text-to-image, sentence-similarity

    Returns:
      {"success": bool, "models": list[{"id","author","downloads","likes","task","tags"}]}
    """
    params: dict = {"search": query, "limit": limit, "sort": "downloads", "direction": -1}
    if task:
        params["pipeline_tag"] = task
    try:
        resp = httpx.get(f"{HF_API}/models", headers=_headers(), params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        models = resp.json()
        results = [
            {
                "id": m.get("id", ""),
                "author": m.get("author", ""),
                "downloads": m.get("downloads", 0),
                "likes": m.get("likes", 0),
                "task": m.get("pipeline_tag", ""),
                "tags": m.get("tags", [])[:5],
                "url": f"https://huggingface.co/{m.get('id', '')}",
            }
            for m in models
        ]
        return {"success": True, "models": results, "error": None}
    except Exception as e:
        return {"success": False, "models": [], "error": str(e)}


def get_model_info(model_id: str) -> dict:
    """Get detailed info about a specific model.

    Args:
      model_id: HuggingFace model ID e.g. "openai-community/gpt2"

    Returns:
      {"success": bool, "id": str, "task": str, "downloads": int, "likes": int,
       "tags": list, "library": str, "created_at": str, "card_summary": str}
    """
    try:
        resp = httpx.get(f"{HF_API}/models/{model_id}", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        m = resp.json()
        return {
            "success": True,
            "id": m.get("id", ""),
            "task": m.get("pipeline_tag", ""),
            "downloads": m.get("downloads", 0),
            "likes": m.get("likes", 0),
            "tags": m.get("tags", []),
            "library": m.get("library_name", ""),
            "created_at": m.get("createdAt", ""),
            "private": m.get("private", False),
            "url": f"https://huggingface.co/{model_id}",
            "error": None,
        }
    except Exception as e:
        return {"success": False, "id": model_id, "error": str(e)}


def search_datasets(query: str, limit: int = 10) -> dict:
    """Search HuggingFace datasets.

    Returns:
      {"success": bool, "datasets": list[{"id","downloads","likes","tags"}]}
    """
    try:
        params = {"search": query, "limit": limit, "sort": "downloads", "direction": -1}
        resp = httpx.get(f"{HF_API}/datasets", headers=_headers(), params=params, timeout=TIMEOUT)
        resp.raise_for_status()
        datasets = resp.json()
        results = [
            {
                "id": d.get("id", ""),
                "downloads": d.get("downloads", 0),
                "likes": d.get("likes", 0),
                "tags": d.get("tags", [])[:5],
                "url": f"https://huggingface.co/datasets/{d.get('id', '')}",
            }
            for d in datasets
        ]
        return {"success": True, "datasets": results, "error": None}
    except Exception as e:
        return {"success": False, "datasets": [], "error": str(e)}


def get_model_card(model_id: str) -> dict:
    """Retrieve the README/model card markdown for a model.

    Returns:
      {"success": bool, "card": str (first 3000 chars), "error": str|None}
    """
    try:
        resp = httpx.get(
            f"https://huggingface.co/{model_id}/raw/main/README.md",
            headers=_headers(),
            timeout=TIMEOUT,
            follow_redirects=True,
        )
        if resp.status_code == 200:
            return {"success": True, "card": resp.text[:3000], "error": None}
        return {"success": False, "card": "", "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"success": False, "card": "", "error": str(e)}


def list_model_files(model_id: str) -> dict:
    """List files in a model repository.

    Returns:
      {"success": bool, "files": list[{"path": str, "size": int}]}
    """
    try:
        resp = httpx.get(f"{HF_API}/models/{model_id}", headers=_headers(), timeout=TIMEOUT)
        resp.raise_for_status()
        siblings = resp.json().get("siblings", [])
        files = [{"path": s.get("rfilename", ""), "size": s.get("size", 0)} for s in siblings]
        return {"success": True, "files": files, "error": None}
    except Exception as e:
        return {"success": False, "files": [], "error": str(e)}
