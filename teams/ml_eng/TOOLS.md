# ML Engineering Team — TOOLS

Research:
- **Tavily Search**: ML model landscape, benchmarks, dataset availability
- **HuggingFace Hub**: Model search and download (text generation, classification, embeddings, etc.)
- **OpenAI API**: LLM task prototyping and evaluation

Experiment Tracking:
- **MLflow**: Log experiments, metrics, params, artifacts; register production model version

Code:
- **Git** (push): Training scripts and model card to `ml/` in project branch
- **GitHub API**: Open PRs for model updates
- **GCS**: Store model checkpoints and evaluation artifacts
- **BigQuery**: Query training and evaluation datasets
- **mypy**: Type-check ML Python code
- **Sandbox**: Run training/inference in isolated environment

Tracking:
- **Plane**: ML issue per experiment, linked to Data Eng dataset

Notifications:
- **Slack**: #ml-eng channel — model trained + eval metrics summary
- **Notification**: Stage-complete broadcast to Security Eng and Backend Eng
