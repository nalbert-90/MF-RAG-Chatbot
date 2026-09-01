"""FastAPI application: stateless facts-only ask API (Phase 4)."""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from src.api.schemas import (
    AskRequest,
    AskResponseBody,
    ExamplesResponse,
    HealthResponse,
    SchemeItem,
    SchemesResponse,
)
from src.guardrails.models import DISCLAIMER
from src.guardrails.scheme_resolver import resolve_scheme_id
from src.ingest.embed_index import IndexNotReadyError
from src.rag.groq_client import GroqClient
from src.rag.orchestrator import ask as run_ask
from src.rag.retriever import warmup_retriever
from src.registry import load_schemes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        warmup_retriever()
        logger.info("retriever warmup complete")
    except IndexNotReadyError:
        logger.warning(
            "vector index not ready at startup — run `python -m src.ingest.run`"
        )
    except Exception:
        logger.exception("retriever warmup failed")
    yield



EXAMPLE_QUESTIONS: tuple[str, ...] = (
    "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
    "What is the exit load for HDFC Mid Cap Fund Direct Growth?",
    "What is the lock-in period for HDFC ELSS Tax Saver Fund?",
)

app = FastAPI(
    title="Mutual Fund FAQ Assistant",
    description=(
        "Facts-only RAG API for five HDFC schemes sourced from allowlisted "
        f"Groww pages. {DISCLAIMER}"
    ),
    version="0.1.0",
    lifespan=lifespan,
)
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
router = APIRouter(prefix="/api/v1")


def get_optional_groq_client() -> GroqClient | None:
    """Process-local Groq client when a key is configured; never a user session."""
    try:
        return GroqClient()
    except ValueError:
        return None


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/schemes", response_model=SchemesResponse)
def list_schemes() -> SchemesResponse:
    schemes = [
        SchemeItem(
            scheme_id=entry["scheme_id"],
            name=entry["name"],
            category=entry["category"],
            groww_url=entry["groww_url"],
        )
        for entry in load_schemes()
    ]
    return SchemesResponse(schemes=schemes)


@router.get("/examples", response_model=ExamplesResponse)
def list_examples() -> ExamplesResponse:
    return ExamplesResponse(questions=list(EXAMPLE_QUESTIONS))


@router.post("/ask", response_model=AskResponseBody)
def ask_question(
    body: AskRequest,
    groq_client: Annotated[GroqClient | None, Depends(get_optional_groq_client)],
) -> AskResponseBody:
    started = time.perf_counter()
    try:
        result = run_ask(
            body.question,
            groq_client=groq_client,
            use_groq=groq_client is not None,
        )
    except Exception:
        logger.exception("ask failed")
        raise HTTPException(
            status_code=500,
            detail="Unable to process this question right now.",
        ) from None

    elapsed_ms = int((time.perf_counter() - started) * 1000)
    intent = result.intent.value if result.intent is not None else None
    scheme_id = resolve_scheme_id(body.question.strip())
    logger.info(
        "ask status=%s intent=%s scheme_id=%s latency_ms=%s",
        result.status,
        intent,
        scheme_id,
        elapsed_ms,
    )
    return AskResponseBody(
        status=result.status,
        answer=result.answer,
        citation_url=result.citation_url,
        last_updated=result.last_updated,
        disclaimer=result.disclaimer,
    )


app.include_router(router)
