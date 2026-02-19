"""Tests for rag_system.py — RAGSystem orchestration, unit and integration tests."""

import os
import pytest
from unittest.mock import MagicMock, patch, call
from rag_system import RAGSystem
from models import Course, Lesson, CourseChunk
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.CHUNK_SIZE = 800
    cfg.CHUNK_OVERLAP = 100
    cfg.CHROMA_PATH = "/tmp/test_chroma"
    cfg.EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    cfg.MAX_RESULTS = 5
    cfg.ANTHROPIC_API_KEY = "test-key"
    cfg.ANTHROPIC_MODEL = "claude-test"
    cfg.MAX_HISTORY = 2
    return cfg


@pytest.fixture
def rag(mock_config):
    """Build a RAGSystem with all heavy dependencies mocked out."""
    with patch("rag_system.DocumentProcessor") as MockDP, \
         patch("rag_system.VectorStore") as MockVS, \
         patch("rag_system.AIGenerator") as MockAI, \
         patch("rag_system.SessionManager") as MockSM:

        system = RAGSystem(mock_config)

        # Expose mocks for assertions
        system._mock_dp = MockDP.return_value
        system._mock_vs = MockVS.return_value
        system._mock_ai = MockAI.return_value
        system._mock_sm = MockSM.return_value

        yield system


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInit:
    def test_components_initialized(self, rag):
        assert rag.document_processor is rag._mock_dp
        assert rag.vector_store is rag._mock_vs
        assert rag.ai_generator is rag._mock_ai
        assert rag.session_manager is rag._mock_sm

    def test_tools_registered(self, rag):
        defs = rag.tool_manager.get_tool_definitions()
        names = {d["name"] for d in defs}
        assert "search_course_content" in names
        assert "get_course_outline" in names


# ---------------------------------------------------------------------------
# add_course_document
# ---------------------------------------------------------------------------

class TestAddCourseDocument:
    def _make_course_and_chunks(self):
        course = Course(
            title="Test Course",
            course_link="https://example.com",
            instructor="Prof X",
            lessons=[Lesson(lesson_number=1, title="Intro")],
        )
        chunks = [
            CourseChunk(content="chunk1", course_title="Test Course", lesson_number=1, chunk_index=0),
            CourseChunk(content="chunk2", course_title="Test Course", lesson_number=1, chunk_index=1),
        ]
        return course, chunks

    def test_successful_add(self, rag):
        course, chunks = self._make_course_and_chunks()
        rag._mock_dp.process_course_document.return_value = (course, chunks)

        result_course, result_count = rag.add_course_document("/path/to/file.txt")

        assert result_course.title == "Test Course"
        assert result_count == 2
        rag._mock_vs.add_course_metadata.assert_called_once_with(course)
        rag._mock_vs.add_course_content.assert_called_once_with(chunks)

    def test_processing_error_returns_none(self, rag):
        rag._mock_dp.process_course_document.side_effect = Exception("parse error")

        result_course, result_count = rag.add_course_document("/bad/file.txt")

        assert result_course is None
        assert result_count == 0


# ---------------------------------------------------------------------------
# add_course_folder
# ---------------------------------------------------------------------------

class TestAddCourseFolder:
    def test_nonexistent_folder(self, rag):
        courses, chunks = rag.add_course_folder("/does/not/exist")
        assert courses == 0
        assert chunks == 0

    @patch("os.listdir", return_value=["course1.txt", "course2.txt", "readme.md"])
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_adds_new_courses_skips_existing(self, mock_exists, mock_isfile, mock_listdir, rag):
        rag._mock_vs.get_existing_course_titles.return_value = ["Already Exists"]

        course_new = Course(title="New Course", lessons=[])
        course_existing = Course(title="Already Exists", lessons=[])

        chunks_new = [CourseChunk(content="c", course_title="New Course", chunk_index=0)]

        def process_side_effect(path):
            if "course1" in path:
                return course_new, chunks_new
            elif "course2" in path:
                return course_existing, []
            return None, []

        rag._mock_dp.process_course_document.side_effect = process_side_effect

        total_courses, total_chunks = rag.add_course_folder("/courses")

        assert total_courses == 1
        assert total_chunks == 1

    @patch("os.listdir", return_value=["course1.txt"])
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_clear_existing_flag(self, mock_exists, mock_isfile, mock_listdir, rag):
        rag._mock_vs.get_existing_course_titles.return_value = []
        rag._mock_dp.process_course_document.return_value = (
            Course(title="C", lessons=[]),
            [CourseChunk(content="x", course_title="C", chunk_index=0)],
        )

        rag.add_course_folder("/courses", clear_existing=True)
        rag._mock_vs.clear_all_data.assert_called_once()

    @patch("os.listdir", return_value=["notes.pdf", "image.png"])
    @patch("os.path.isfile", return_value=True)
    @patch("os.path.exists", return_value=True)
    def test_skips_non_supported_extensions(self, mock_exists, mock_isfile, mock_listdir, rag):
        rag._mock_vs.get_existing_course_titles.return_value = []
        rag._mock_dp.process_course_document.return_value = (
            Course(title="PDF Course", lessons=[]),
            [CourseChunk(content="x", course_title="PDF Course", chunk_index=0)],
        )

        total_courses, _ = rag.add_course_folder("/courses")
        # .pdf is supported, .png is not — so only 1 processed
        assert total_courses == 1


# ---------------------------------------------------------------------------
# query — unit tests
# ---------------------------------------------------------------------------

class TestQuery:
    def test_basic_query_no_session(self, rag):
        rag._mock_ai.generate_response.return_value = "AI answer"
        rag.tool_manager.get_last_sources = MagicMock(return_value=[])
        rag.tool_manager.reset_sources = MagicMock()

        response, sources = rag.query("What is ML?")

        assert response == "AI answer"
        assert sources == []
        rag._mock_ai.generate_response.assert_called_once()
        # No session → no history lookup
        rag._mock_sm.get_conversation_history.assert_not_called()

    def test_query_with_session(self, rag):
        rag._mock_ai.generate_response.return_value = "AI answer"
        rag._mock_sm.get_conversation_history.return_value = "User: hi\nAssistant: hello"
        rag.tool_manager.get_last_sources = MagicMock(return_value=[])
        rag.tool_manager.reset_sources = MagicMock()

        response, sources = rag.query("Follow-up question", session_id="s1")

        rag._mock_sm.get_conversation_history.assert_called_once_with("s1")
        rag._mock_sm.add_exchange.assert_called_once_with(
            "s1", "Follow-up question", "AI answer"
        )

    def test_query_passes_tools_to_ai(self, rag):
        rag._mock_ai.generate_response.return_value = "ok"
        rag.tool_manager.get_last_sources = MagicMock(return_value=[])
        rag.tool_manager.reset_sources = MagicMock()

        rag.query("test")

        call_kwargs = rag._mock_ai.generate_response.call_args[1]
        assert "tools" in call_kwargs
        assert call_kwargs["tool_manager"] is rag.tool_manager

    def test_query_returns_sources_from_tools(self, rag):
        rag._mock_ai.generate_response.return_value = "answer"
        expected_sources = [{"label": "ML Course - Lesson 1", "link": "http://x"}]
        rag.tool_manager.get_last_sources = MagicMock(return_value=expected_sources)
        rag.tool_manager.reset_sources = MagicMock()

        _, sources = rag.query("question")
        assert sources == expected_sources

    def test_query_resets_sources_after_retrieval(self, rag):
        rag._mock_ai.generate_response.return_value = "answer"
        rag.tool_manager.get_last_sources = MagicMock(return_value=[])
        rag.tool_manager.reset_sources = MagicMock()

        rag.query("q")
        rag.tool_manager.reset_sources.assert_called_once()

    def test_query_prompt_includes_user_question(self, rag):
        rag._mock_ai.generate_response.return_value = "ok"
        rag.tool_manager.get_last_sources = MagicMock(return_value=[])
        rag.tool_manager.reset_sources = MagicMock()

        rag.query("How does backpropagation work?")

        call_kwargs = rag._mock_ai.generate_response.call_args[1]
        assert "backpropagation" in call_kwargs["query"]


# ---------------------------------------------------------------------------
# get_course_analytics
# ---------------------------------------------------------------------------

class TestGetCourseAnalytics:
    def test_returns_analytics(self, rag):
        rag._mock_vs.get_course_count.return_value = 3
        rag._mock_vs.get_existing_course_titles.return_value = ["A", "B", "C"]

        analytics = rag.get_course_analytics()

        assert analytics["total_courses"] == 3
        assert analytics["course_titles"] == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# Integration-style tests (mocking only the external boundaries)
# ---------------------------------------------------------------------------

class TestIntegration:
    """
    These tests exercise the full query pipeline through RAGSystem → ToolManager
    → CourseSearchTool → (mocked) VectorStore, verifying the components wire
    together correctly.
    """

    def test_search_tool_called_through_pipeline(self, rag):
        """Verify that when AI requests a tool, the pipeline executes it."""
        # Set up the vector store mock (used by the real CourseSearchTool)
        rag.vector_store.search.return_value = SearchResults(
            documents=["relevant content"],
            metadata=[{"course_title": "ML101", "lesson_number": 1}],
            distances=[0.1],
        )
        rag.vector_store.get_lesson_link.return_value = "http://link"

        # Execute the search tool directly through the tool_manager
        result = rag.tool_manager.execute_tool(
            "search_course_content", query="neural networks"
        )

        assert "ML101" in result
        assert "relevant content" in result

    def test_sources_flow_through_pipeline(self, rag):
        """Sources set by search tool should be retrievable via tool_manager."""
        rag.vector_store.search.return_value = SearchResults(
            documents=["doc"],
            metadata=[{"course_title": "DL", "lesson_number": 3}],
            distances=[0.1],
        )
        rag.vector_store.get_lesson_link.return_value = "http://dl/3"

        rag.tool_manager.execute_tool("search_course_content", query="CNN")

        sources = rag.tool_manager.get_last_sources()
        assert len(sources) == 1
        assert sources[0]["label"] == "DL - Lesson 3"
        assert sources[0]["link"] == "http://dl/3"

        # Reset and verify
        rag.tool_manager.reset_sources()
        assert rag.tool_manager.get_last_sources() == []

    def test_outline_tool_through_pipeline(self, rag):
        """Verify outline tool works end-to-end through the tool_manager."""
        rag.vector_store._resolve_course_name.return_value = "Deep Learning"
        rag.vector_store.course_catalog.get.return_value = {
            "metadatas": [{
                "title": "Deep Learning",
                "course_link": "https://dl.com",
                "lessons_json": '[{"lesson_number":1,"lesson_title":"Intro","lesson_link":"http://1"}]',
                "lesson_count": 1,
            }],
            "ids": ["Deep Learning"],
        }

        result = rag.tool_manager.execute_tool(
            "get_course_outline", course_name="DL"
        )

        assert "Course: Deep Learning" in result
        assert "Lesson 1: Intro" in result

    def test_unknown_tool_handled_gracefully(self, rag):
        result = rag.tool_manager.execute_tool("fake_tool", param="x")
        assert "not found" in result

    def test_search_with_no_results(self, rag):
        """Empty vector store results should produce a clear message."""
        rag.vector_store.search.return_value = SearchResults(
            documents=[], metadata=[], distances=[]
        )

        result = rag.tool_manager.execute_tool(
            "search_course_content", query="quantum computing"
        )
        assert "No relevant content found" in result

    def test_search_with_error(self, rag):
        """Vector store error should propagate as a readable string."""
        rag.vector_store.search.return_value = SearchResults.empty(
            "Search error: connection refused"
        )

        result = rag.tool_manager.execute_tool(
            "search_course_content", query="anything"
        )
        assert "connection refused" in result
