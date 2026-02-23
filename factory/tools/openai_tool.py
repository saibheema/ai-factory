"""OpenAI tool — direct LLM API calls for agent-driven tasks.

Used by ml_eng and solution_arch teams for:
 - Chat completions (GPT-4o, o1, o3-mini, etc.)
 - Text embeddings
 - Structured output / JSON mode
 - Function calling

Env vars:
  OPENAI_API_KEY   — required
  OPENAI_BASE_URL  — optional (for Azure OpenAI or proxy)
  OPENAI_ORG_ID    — optional organisation ID
  OPENAI_DEFAULT_MODEL — default model (default: gpt-4o-mini)
"""

import logging
import os

log = logging.getLogger(__name__)

API_KEY = os.getenv("OPENAI_API_KEY", "")
BASE_URL = os.getenv("OPENAI_BASE_URL", "")
ORG_ID = os.getenv("OPENAI_ORG_ID", "")
DEFAULT_MODEL = os.getenv("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")


def _client():
    try:
        from openai import OpenAI
        kwargs: dict = {"api_key": API_KEY}
        if BASE_URL:
            kwargs["base_url"] = BASE_URL
        if ORG_ID:
            kwargs["organization"] = ORG_ID
        return OpenAI(**kwargs)
    except ImportError:
        raise RuntimeError("openai not installed — pip install openai")


def _available() -> bool:
    return bool(API_KEY)


def chat_completion(
    messages: list[dict],
    model: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.7,
    response_format: str = "text",
    system_prompt: str = "",
) -> dict:
    """Run a chat completion request.

    Args:
      messages:        List of {"role": "user"|"assistant"|"system", "content": str}
      model:           Model ID (default: OPENAI_DEFAULT_MODEL)
      max_tokens:      Max output tokens (default 1024)
      temperature:     Sampling temperature 0-2 (default 0.7)
      response_format: "text" | "json_object" — JSON mode forces JSON output
      system_prompt:   Prepend a system message (shorthand)

    Returns:
      {"success": bool, "content": str, "model": str,
       "prompt_tokens": int, "completion_tokens": int, "error": str|None}
    """
    if not _available():
        return {"success": False, "content": "", "model": "", "error": "OPENAI_API_KEY not set"}
    all_messages = []
    if system_prompt:
        all_messages.append({"role": "system", "content": system_prompt})
    all_messages.extend(messages)
    try:
        client = _client()
        kwargs: dict = {
            "model": model or DEFAULT_MODEL,
            "messages": all_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if response_format == "json_object":
            kwargs["response_format"] = {"type": "json_object"}
        response = client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        return {
            "success": True,
            "content": choice.message.content or "",
            "finish_reason": choice.finish_reason,
            "model": response.model,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "content": "", "model": model or DEFAULT_MODEL, "error": str(e)}


def embeddings(texts: list[str], model: str = "text-embedding-3-small") -> dict:
    """Generate text embeddings.

    Args:
      texts: List of strings to embed
      model: Embedding model (default: text-embedding-3-small)

    Returns:
      {"success": bool, "embeddings": list[list[float]], "model": str,
       "total_tokens": int, "error": str|None}
    """
    if not _available():
        return {"success": False, "embeddings": [], "model": model, "error": "OPENAI_API_KEY not set"}
    try:
        client = _client()
        response = client.embeddings.create(input=texts, model=model)
        vecs = [item.embedding for item in sorted(response.data, key=lambda x: x.index)]
        return {
            "success": True,
            "embeddings": vecs,
            "model": response.model,
            "total_tokens": response.usage.total_tokens,
            "error": None,
        }
    except Exception as e:
        return {"success": False, "embeddings": [], "model": model, "error": str(e)}


def list_models() -> dict:
    """List available OpenAI models.

    Returns:
      {"success": bool, "models": list[str], "error": str|None}
    """
    if not _available():
        return {"success": False, "models": [], "error": "OPENAI_API_KEY not set"}
    try:
        client = _client()
        models = [m.id for m in client.models.list().data]
        models.sort()
        return {"success": True, "models": models, "error": None}
    except Exception as e:
        return {"success": False, "models": [], "error": str(e)}


def structured_extraction(text: str, schema_description: str, model: str = "") -> dict:
    """Extract structured data from text using JSON mode.

    Args:
      text:               Input text to extract from
      schema_description: Natural language description of desired JSON structure
      model:              Model to use (default: OPENAI_DEFAULT_MODEL)

    Returns:
      {"success": bool, "extracted": dict, "error": str|None}
    """
    import json

    prompt = f"""Extract the following information from the text and return ONLY valid JSON.

Schema to extract: {schema_description}

Text:
{text}"""
    result = chat_completion(
        messages=[{"role": "user", "content": prompt}],
        model=model,
        response_format="json_object",
        temperature=0.1,
    )
    if not result["success"]:
        return {"success": False, "extracted": {}, "error": result["error"]}
    try:
        extracted = json.loads(result["content"])
        return {"success": True, "extracted": extracted, "error": None}
    except json.JSONDecodeError as e:
        return {"success": False, "extracted": {}, "error": f"JSON parse error: {e}"}
