from __future__ import annotations

from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

try:
    from .setup import DB_URL, DEFAULT_MODEL, run_sql_workflow
except ImportError:
    from setup import DB_URL, DEFAULT_MODEL, run_sql_workflow


app = FastAPI(title="M2 SQL Agent API", version="0.1.0")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, description="Natural language question")
    model_generation: str = Field(DEFAULT_MODEL, description="Model for SQL generation")
    model_evaluation: str = Field(DEFAULT_MODEL, description="Model for SQL reflection")


class AskResponse(BaseModel):
    question: str
    sql_v1: str
    sql_v2: str
    feedback: str
    rows: list[dict[str, Any]]
    summary: str
    latency_ms: float


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    start = perf_counter()
    try:
        result = run_sql_workflow(
            db_url=DB_URL,
            question=request.question,
            model_generation=request.model_generation,
            model_evaluation=request.model_evaluation,
        )
    except Exception as error:
        raise HTTPException(status_code=500, detail=str(error)) from error

    df_v2 = result["result_v2"]
    rows = df_v2.to_dict(orient="records")
    summary = f"Returned {len(rows)} rows with {len(df_v2.columns)} columns."
    latency_ms = round((perf_counter() - start) * 1000, 2)

    return AskResponse(
        question=result["question"],
        sql_v1=result["sql_v1"],
        sql_v2=result["sql_v2"],
        feedback=result["feedback"],
        rows=rows,
        summary=summary,
        latency_ms=latency_ms,
    )
