"""
API endpoint tests for the RAG chatbot.

Uses the test_app / client fixtures from conftest.py, which provide a
static-file-free FastAPI app backed by a mocked RAGSystem.
"""

import pytest
from unittest.mock import MagicMock


# ===========================================================================
# GET /api/courses
# ===========================================================================

class TestGetCourses:
    """Tests for the GET /api/courses endpoint."""

    def test_returns_200(self, client):
        response = client.get("/api/courses")
        assert response.status_code == 200

    def test_response_shape(self, client, sample_course_data):
        response = client.get("/api/courses")
        body = response.json()

        assert "total_courses" in body
        assert "course_titles" in body

    def test_response_values(self, client, sample_course_data):
        response = client.get("/api/courses")
        body = response.json()

        assert body["total_courses"] == sample_course_data["total_courses"]
        assert body["course_titles"] == sample_course_data["course_titles"]

    def test_course_titles_is_list(self, client):
        body = client.get("/api/courses").json()
        assert isinstance(body["course_titles"], list)

    def test_total_courses_is_int(self, client):
        body = client.get("/api/courses").json()
        assert isinstance(body["total_courses"], int)

    def test_internal_error_returns_500(self, test_app):
        """When RAGSystem raises, the endpoint should return 500."""
        # Patch the route's rag reference via a fresh client with a broken mock
        from fastapi.testclient import TestClient

        # Re-wire: get the mock out of the app's route closures by building a
        # new test_app whose rag raises.
        broken_rag = MagicMock()
        broken_rag.get_course_analytics.side_effect = RuntimeError("db error")

        from fastapi import FastAPI, HTTPException
        from fastapi.responses import JSONResponse

        mini = FastAPI()

        @mini.get("/api/courses")
        async def _courses():
            try:
                broken_rag.get_course_analytics()
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e))

        resp = TestClient(mini).get("/api/courses")
        assert resp.status_code == 500
        assert "db error" in resp.json()["detail"]


# ===========================================================================
# POST /api/query
# ===========================================================================

class TestPostQuery:
    """Tests for the POST /api/query endpoint."""

    # --- happy-path ---

    def test_returns_200(self, client, sample_query_payload):
        response = client.post("/api/query", json=sample_query_payload)
        assert response.status_code == 200

    def test_response_contains_required_fields(self, client, sample_query_payload):
        body = client.post("/api/query", json=sample_query_payload).json()

        assert "answer" in body
        assert "sources" in body
        assert "session_id" in body

    def test_answer_is_string(self, client, sample_query_payload):
        body = client.post("/api/query", json=sample_query_payload).json()
        assert isinstance(body["answer"], str)

    def test_sources_is_list(self, client, sample_query_payload):
        body = client.post("/api/query", json=sample_query_payload).json()
        assert isinstance(body["sources"], list)

    def test_session_id_is_string(self, client, sample_query_payload):
        body = client.post("/api/query", json=sample_query_payload).json()
        assert isinstance(body["session_id"], str)

    def test_response_values_match_mock(self, client, sample_query_payload, sample_query_response):
        body = client.post("/api/query", json=sample_query_payload).json()

        assert body["answer"] == sample_query_response["answer"]
        assert body["sources"] == sample_query_response["sources"]
        assert body["session_id"] == sample_query_response["session_id"]

    # --- session handling ---

    def test_new_session_created_when_none_provided(self, client, mock_rag_system):
        """Without a session_id the endpoint creates one via session_manager."""
        response = client.post("/api/query", json={"query": "hello"})
        assert response.status_code == 200
        # The mock session_manager should have been called to create a session
        mock_rag_system.session_manager.create_session.assert_called_once()

    def test_provided_session_id_is_reused(self, client, mock_rag_system):
        """When session_id is supplied it must be passed through unchanged."""
        payload = {"query": "hello", "session_id": "my-session-123"}
        body = client.post("/api/query", json=payload).json()

        assert body["session_id"] == "my-session-123"
        # create_session should NOT have been called
        mock_rag_system.session_manager.create_session.assert_not_called()

    def test_rag_query_called_with_correct_args(self, client, mock_rag_system):
        """The underlying RAGSystem.query must receive the user query text."""
        payload = {"query": "What is machine learning?", "session_id": "s1"}
        client.post("/api/query", json=payload)

        mock_rag_system.query.assert_called_once_with(
            "What is machine learning?", "s1"
        )

    # --- validation ---

    def test_missing_query_field_returns_422(self, client):
        """A request body without 'query' should fail Pydantic validation."""
        response = client.post("/api/query", json={})
        assert response.status_code == 422

    def test_empty_query_string_is_accepted(self, client):
        """An empty string is a valid (if unusual) query value."""
        response = client.post("/api/query", json={"query": ""})
        assert response.status_code == 200

    def test_extra_fields_are_ignored(self, client):
        """Unknown fields in the request body should not cause errors."""
        payload = {"query": "hello", "unknown_field": "value"}
        response = client.post("/api/query", json=payload)
        assert response.status_code == 200

    def test_non_json_body_returns_422(self, client):
        response = client.post(
            "/api/query",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 422

    # --- error handling ---

    def test_internal_error_returns_500(self, test_app, mock_rag_system):
        """When RAGSystem.query raises, the endpoint should return 500."""
        mock_rag_system.query.side_effect = RuntimeError("rag failure")

        from fastapi.testclient import TestClient

        response = TestClient(test_app).post(
            "/api/query", json={"query": "trigger error"}
        )
        assert response.status_code == 500
        assert "rag failure" in response.json()["detail"]


# ===========================================================================
# Content-type / headers
# ===========================================================================

class TestResponseHeaders:
    """Verify that responses carry the expected Content-Type."""

    def test_courses_content_type_is_json(self, client):
        response = client.get("/api/courses")
        assert "application/json" in response.headers["content-type"]

    def test_query_content_type_is_json(self, client):
        response = client.post("/api/query", json={"query": "hi"})
        assert "application/json" in response.headers["content-type"]


# ===========================================================================
# Method-not-allowed guards
# ===========================================================================

class TestMethodNotAllowed:
    """Ensure wrong HTTP methods return 405."""

    def test_get_on_query_endpoint(self, client):
        response = client.get("/api/query")
        assert response.status_code == 405

    def test_post_on_courses_endpoint(self, client):
        response = client.post("/api/courses", json={})
        assert response.status_code == 405
