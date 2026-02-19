"""Tests for search_tools.py — CourseSearchTool, CourseOutlineTool, and ToolManager."""

import pytest
from unittest.mock import MagicMock, patch
from search_tools import CourseSearchTool, CourseOutlineTool, ToolManager, Tool
from vector_store import SearchResults


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_vector_store():
    """Create a mock VectorStore with sensible defaults."""
    store = MagicMock()
    store.search.return_value = SearchResults(
        documents=["chunk text about ML"],
        metadata=[{"course_title": "Intro to ML", "lesson_number": 2}],
        distances=[0.15],
    )
    store.get_lesson_link.return_value = "https://example.com/ml/lesson2"
    store._resolve_course_name.return_value = "Intro to ML"
    store.course_catalog.get.return_value = {
        "metadatas": [{
            "title": "Intro to ML",
            "course_link": "https://example.com/ml",
            "lessons_json": '[{"lesson_number":1,"lesson_title":"Basics","lesson_link":"https://example.com/ml/1"},{"lesson_number":2,"lesson_title":"Advanced","lesson_link":"https://example.com/ml/2"}]',
            "lesson_count": 2,
        }],
        "ids": ["Intro to ML"],
    }
    return store


@pytest.fixture
def search_tool(mock_vector_store):
    return CourseSearchTool(mock_vector_store)


@pytest.fixture
def outline_tool(mock_vector_store):
    return CourseOutlineTool(mock_vector_store)


@pytest.fixture
def tool_manager(search_tool, outline_tool):
    tm = ToolManager()
    tm.register_tool(search_tool)
    tm.register_tool(outline_tool)
    return tm


# ---------------------------------------------------------------------------
# CourseSearchTool — unit tests
# ---------------------------------------------------------------------------

class TestCourseSearchTool:
    def test_tool_definition_has_required_fields(self, search_tool):
        defn = search_tool.get_tool_definition()
        assert defn["name"] == "search_course_content"
        assert "input_schema" in defn
        assert "query" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["required"] == ["query"]

    def test_execute_returns_formatted_results(self, search_tool, mock_vector_store):
        result = search_tool.execute(query="machine learning")
        assert "[Intro to ML - Lesson 2]" in result
        assert "chunk text about ML" in result
        mock_vector_store.search.assert_called_once_with(
            query="machine learning", course_name=None, lesson_number=None
        )

    def test_execute_with_course_and_lesson_filters(self, search_tool, mock_vector_store):
        search_tool.execute(query="neural nets", course_name="ML", lesson_number=3)
        mock_vector_store.search.assert_called_once_with(
            query="neural nets", course_name="ML", lesson_number=3
        )

    def test_execute_empty_results(self, search_tool, mock_vector_store):
        mock_vector_store.search.return_value = SearchResults(
            documents=[], metadata=[], distances=[]
        )
        result = search_tool.execute(query="nonexistent topic")
        assert "No relevant content found" in result

    def test_execute_empty_results_with_filters(self, search_tool, mock_vector_store):
        mock_vector_store.search.return_value = SearchResults(
            documents=[], metadata=[], distances=[]
        )
        result = search_tool.execute(
            query="x", course_name="Physics", lesson_number=5
        )
        assert "Physics" in result
        assert "lesson 5" in result

    def test_execute_error_from_store(self, search_tool, mock_vector_store):
        mock_vector_store.search.return_value = SearchResults.empty("Search error: timeout")
        result = search_tool.execute(query="anything")
        assert result == "Search error: timeout"

    def test_last_sources_tracked(self, search_tool):
        search_tool.execute(query="ML basics")
        assert len(search_tool.last_sources) == 1
        assert search_tool.last_sources[0]["label"] == "Intro to ML - Lesson 2"
        assert search_tool.last_sources[0]["link"] == "https://example.com/ml/lesson2"

    def test_sources_without_lesson_number(self, search_tool, mock_vector_store):
        mock_vector_store.search.return_value = SearchResults(
            documents=["overview text"],
            metadata=[{"course_title": "Intro to ML", "lesson_number": None}],
            distances=[0.1],
        )
        search_tool.execute(query="overview")
        src = search_tool.last_sources[0]
        assert src["label"] == "Intro to ML"
        assert src["link"] is None

    def test_multiple_results_formatted(self, search_tool, mock_vector_store):
        mock_vector_store.search.return_value = SearchResults(
            documents=["doc1", "doc2"],
            metadata=[
                {"course_title": "A", "lesson_number": 1},
                {"course_title": "B", "lesson_number": None},
            ],
            distances=[0.1, 0.2],
        )
        result = search_tool.execute(query="test")
        assert "[A - Lesson 1]" in result
        assert "[B]" in result
        assert len(search_tool.last_sources) == 2


# ---------------------------------------------------------------------------
# CourseOutlineTool — unit tests
# ---------------------------------------------------------------------------

class TestCourseOutlineTool:
    def test_tool_definition(self, outline_tool):
        defn = outline_tool.get_tool_definition()
        assert defn["name"] == "get_course_outline"
        assert "course_name" in defn["input_schema"]["properties"]
        assert defn["input_schema"]["required"] == ["course_name"]

    def test_execute_returns_formatted_outline(self, outline_tool):
        result = outline_tool.execute(course_name="ML")
        assert "Course: Intro to ML" in result
        assert "Course Link: https://example.com/ml" in result
        assert "Total Lessons: 2" in result
        assert "Lesson 1: Basics" in result
        assert "Lesson 2: Advanced" in result

    def test_execute_no_matching_course(self, outline_tool, mock_vector_store):
        mock_vector_store._resolve_course_name.return_value = None
        result = outline_tool.execute(course_name="Nonexistent")
        assert "No course found" in result

    def test_execute_no_metadata(self, outline_tool, mock_vector_store):
        mock_vector_store.course_catalog.get.return_value = {
            "metadatas": [None], "ids": ["X"]
        }
        result = outline_tool.execute(course_name="ML")
        assert "No metadata found" in result

    def test_execute_empty_get_result(self, outline_tool, mock_vector_store):
        mock_vector_store.course_catalog.get.return_value = {
            "metadatas": [], "ids": []
        }
        result = outline_tool.execute(course_name="ML")
        assert "No metadata found" in result

    def test_execute_handles_exception(self, outline_tool, mock_vector_store):
        mock_vector_store._resolve_course_name.return_value = "Some Course"
        mock_vector_store.course_catalog.get.side_effect = Exception("DB error")
        result = outline_tool.execute(course_name="ML")
        assert "Error retrieving course outline" in result


# ---------------------------------------------------------------------------
# ToolManager — unit tests
# ---------------------------------------------------------------------------

class TestToolManager:
    def test_register_and_get_definitions(self, tool_manager):
        defs = tool_manager.get_tool_definitions()
        names = {d["name"] for d in defs}
        assert "search_course_content" in names
        assert "get_course_outline" in names

    def test_register_tool_without_name_raises(self):
        bad_tool = MagicMock(spec=Tool)
        bad_tool.get_tool_definition.return_value = {"description": "no name"}
        tm = ToolManager()
        with pytest.raises(ValueError, match="must have a 'name'"):
            tm.register_tool(bad_tool)

    def test_execute_registered_tool(self, tool_manager, mock_vector_store):
        result = tool_manager.execute_tool("search_course_content", query="test")
        assert isinstance(result, str)

    def test_execute_unknown_tool(self, tool_manager):
        result = tool_manager.execute_tool("nonexistent_tool", query="x")
        assert "not found" in result

    def test_get_last_sources(self, tool_manager, search_tool):
        search_tool.last_sources = [{"label": "src", "link": None}]
        assert tool_manager.get_last_sources() == [{"label": "src", "link": None}]

    def test_get_last_sources_empty(self, tool_manager):
        assert tool_manager.get_last_sources() == []

    def test_reset_sources(self, tool_manager, search_tool):
        search_tool.last_sources = [{"label": "x", "link": None}]
        tool_manager.reset_sources()
        assert search_tool.last_sources == []

    def test_execute_passes_kwargs(self, tool_manager, mock_vector_store):
        tool_manager.execute_tool(
            "search_course_content",
            query="q", course_name="C", lesson_number=1,
        )
        mock_vector_store.search.assert_called_once_with(
            query="q", course_name="C", lesson_number=1
        )
