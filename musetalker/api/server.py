from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import json
import yaml

from musetalker.llm.orchestrator import LLMOrchestrator

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

orch = LLMOrchestrator()
DOMAIN_PRIOR_PATH = Path(__file__).parents[1] / "configs" / "domain_prior.json"
PERSONAS_PATH = Path(__file__).parents[1] / "configs" / "personas.yaml"


class LLMRequest(BaseModel):
    text: str
    persona_id: str = "woman_demo"
    session_id: str | None = None


@app.post("/api/llm")
def run_llm(req: LLMRequest):
    return orch.run(req.text, req.persona_id, req.session_id)


@app.get("/api/domain_prior")
def get_domain_prior():
    with open(DOMAIN_PRIOR_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/personas")
def get_personas():
    with open(PERSONAS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return data.get("personas", {})
