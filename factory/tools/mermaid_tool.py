"""Mermaid diagram tool — generate architecture, sequence, and flow diagrams.

Produces Mermaid markdown that can be embedded in Google Docs or saved to GCS/Git.
"""

import logging

log = logging.getLogger(__name__)


def render_diagram(diagram_type: str, title: str, content: str) -> dict:
    """Generate a Mermaid diagram definition.

    diagram_type: "flowchart", "sequence", "class", "er", "c4", "gantt", "stateDiagram"
    Returns: {"type": str, "title": str, "mermaid": str, "preview_url": str}
    """
    # Validate/normalize type
    valid_types = {"flowchart", "sequence", "class", "er", "c4", "gantt", "stateDiagram", "graph"}
    if diagram_type not in valid_types:
        diagram_type = "flowchart"

    mermaid_code = content.strip()

    # Generate a mermaid.live preview URL
    import base64, json
    state_json = json.dumps({"code": mermaid_code, "mermaid": {"theme": "default"}})
    encoded = base64.urlsafe_b64encode(state_json.encode()).decode().rstrip("=")
    preview_url = f"https://mermaid.live/edit#base64:{encoded}"

    log.info("Generated %s diagram: %s", diagram_type, title)
    return {
        "type": diagram_type,
        "title": title,
        "mermaid": mermaid_code,
        "preview_url": preview_url,
    }
