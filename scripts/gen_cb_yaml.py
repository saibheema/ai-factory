#!/usr/bin/env python3
"""Generate /tmp/cb-v6.yaml for Cloud Build deployment."""
import yaml

TAG = "release-tools-v6"
PROJECT = "unicon-494419"
REGISTRY = f"us-central1-docker.pkg.dev/{PROJECT}/ai-factory"

def img(svc): return f"{REGISTRY}/{svc}:{TAG}"

cfg = {
    "steps": [
        {"name": "gcr.io/cloud-builders/docker", "id": "build-orch",
         "args": ["build", "-f", "services/orchestrator/Dockerfile", "-t", img("orchestrator"), "."]},
        {"name": "gcr.io/cloud-builders/docker", "id": "build-fe",
         "args": ["build", "-f", "frontend/Dockerfile", "-t", img("frontend"), "frontend"]},
        {"name": "gcr.io/cloud-builders/docker", "id": "push-orch",
         "waitFor": ["build-orch"], "args": ["push", img("orchestrator")]},
        {"name": "gcr.io/cloud-builders/docker", "id": "push-fe",
         "waitFor": ["build-fe"], "args": ["push", img("frontend")]},
        {"name": "gcr.io/google.com/cloudsdktool/cloud-sdk", "id": "deploy-orch",
         "waitFor": ["push-orch"], "entrypoint": "gcloud",
         "args": ["run", "deploy", "ai-factory-orchestrator",
                  f"--image={img('orchestrator')}", "--region=us-central1", "--quiet"]},
        {"name": "gcr.io/google.com/cloudsdktool/cloud-sdk", "id": "deploy-fe",
         "waitFor": ["push-fe"], "entrypoint": "gcloud",
         "args": ["run", "deploy", "ai-factory-frontend",
                  f"--image={img('frontend')}", "--region=us-central1", "--quiet"]},
    ],
    "images": [img("orchestrator"), img("frontend")],
}

out = "/tmp/cb-v6-clean.yaml"
with open(out, "w") as f:
    yaml.dump(cfg, f, default_flow_style=False)
print(f"Written to {out}")
