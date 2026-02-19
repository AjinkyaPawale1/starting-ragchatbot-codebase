"""
Shared fixtures for the RAG chatbot test suite.

The production app.py mounts StaticFiles from ../frontend at startup, which
won't exist in the test environment. To avoid that import-time side effect we
build a lightweight test app here that declares the same API routes and uses
the same request/response models, but with a mocked RAGSystem injected via
dependency override.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from typing import List, Optional
from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Pydantic models (mirrors app.py so tests stay independent of the import)
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    query: str
    session_id: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: List[str]
    session_id: str


class CourseStats(BaseModel):
    total_courses: int
    course_titles: List[str]


# ---------------------------------------------------------------------------
# Fixture: mock RAGSystem
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_rag_system():
    """
    A MagicMock that matches the RAGSystem interface used by the API routes.

    Defaults:
      - query()               → ("Mock answer", ["source1", "source2"])
      - get_course_analytics() → {"total_courses": 2, "course_titles": [...]}
      - session_manager.create_session() → "session_test"
    """
    rag = MagicMock()

    rag.query.return_value = ("Mock answer", ["source1", "source2"])
    rag.get_course_analytics.return_value = {
        "total_courses": 2,
        "course_titles": ["Python Basics", "Advanced ML"],
    }
    rag.session_manager.create_session.return_value = "session_test"

    return rag


# ---------------------------------------------------------------------------
# Fixture: test FastAPI app (no static-file mount)
# ---------------------------------------------------------------------------

@pytest.fixture
def test_app(mock_rag_system):
    """
    Minimal FastAPI app with the same routes as app.py, but without the
    static-file mount so it works in a test environment without a frontend
    build. The RAGSystem is replaced by mock_rag_system.
    """
    app = FastAPI(title="RAG System – Test App")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.post("/api/query", response_model=QueryResponse)
    async def query_documents(request: QueryRequest):
        try:
            session_id = request.session_id
            if not session_id:
                session_id = mock_rag_system.session_manager.create_session()

            answer, sources = mock_rag_system.query(request.query, session_id)

            return QueryResponse(answer=answer, sources=sources, session_id=session_id)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/api/courses", response_model=CourseStats)
    async def get_course_stats():
        try:
            analytics = mock_rag_system.get_course_analytics()
            return CourseStats(
                total_courses=analytics["total_courses"],
                course_titles=analytics["course_titles"],
            )
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    return app


# ---------------------------------------------------------------------------
# Fixture: synchronous TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client(test_app):
    """Synchronous HTTPX TestClient wrapping the test app."""
    return TestClient(test_app)


# ---------------------------------------------------------------------------
# Fixture: sample course data
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_course_data():
    """Reusable course analytics payload."""
    return {
        "total_courses": 2,
        "course_titles": ["Python Basics", "Advanced ML"],
    }


# ---------------------------------------------------------------------------
# Fixture: sample query / response payloads
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_query_payload():
    """Valid /api/query request body."""
    return {"query": "What is Python?"}


@pytest.fixture
def sample_query_response():
    """Expected /api/query response body (matches mock_rag_system defaults)."""
    return {
        "answer": "Mock answer",
        "sources": ["source1", "source2"],
        "session_id": "session_test",
    }
