# ML Engineering Team — AGENTS

Operatives:
- **ML Problem Framer** — defines problem type, success metric, baseline, evaluation protocol
- **Model Researcher** — searches HuggingFace Hub for pre-trained models; evaluates fit
- **Feature Engineer** — designs and implements feature transformations from Data Eng datasets
- **Training Engineer** — writes training loop, hyperparameter config, reproducible seed
- **Evaluation Analyst** — runs evaluation suite, produces metric report, identifies failure modes
- **MLflow Logger** — logs all experiments: params, metrics, artifacts, model registry
- **Model Card Author** — documents intended use, performance, limitations, bias analysis
- **Backend Integration Engineer** — wraps model behind a FastAPI inference endpoint

Handoff Protocol:
  Model Card pushed to Git as `ml/model_card.md`.
  MLflow experiment run linked in Plane issue.
  Backend Eng receives inference API spec via Slack.
