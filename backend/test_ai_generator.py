"""Tests for ai_generator.py — AIGenerator and its tool-handling logic."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from ai_generator import AIGenerator


# ---------------------------------------------------------------------------
# Helpers to build mock Anthropic response objects
# ---------------------------------------------------------------------------

def _make_text_block(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def _make_tool_use_block(tool_name: str, tool_input: dict, tool_id: str = "tool_1"):
    block = MagicMock()
    block.type = "tool_use"
    block.name = tool_name
    block.input = tool_input
    block.id = tool_id
    return block


def _make_response(content_blocks, stop_reason="end_turn"):
    resp = MagicMock()
    resp.content = content_blocks
    resp.stop_reason = stop_reason
    return resp


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def ai_gen():
    """AIGenerator with a mocked Anthropic client."""
    with patch("ai_generator.anthropic.Anthropic") as MockClient:
        gen = AIGenerator(api_key="test-key", model="claude-test")
        # Replace the real client with our mock
        gen.client = MockClient.return_value
        yield gen


@pytest.fixture
def mock_tool_manager():
    tm = MagicMock()
    tm.execute_tool.return_value = "tool result text"
    return tm


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestAIGeneratorInit:
    def test_base_params(self, ai_gen):
        assert ai_gen.base_params["model"] == "claude-test"
        assert ai_gen.base_params["temperature"] == 0
        assert ai_gen.base_params["max_tokens"] == 800

    def test_system_prompt_exists(self, ai_gen):
        assert "search_course_content" in AIGenerator.SYSTEM_PROMPT
        assert "get_course_outline" in AIGenerator.SYSTEM_PROMPT
        assert "One tool call per query maximum" not in AIGenerator.SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# generate_response — direct text (no tool use)
# ---------------------------------------------------------------------------

class TestDirectResponse:
    def test_returns_text(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("Hello!")], stop_reason="end_turn"
        )
        result = ai_gen.generate_response(query="Hi")
        assert result == "Hello!"

    def test_passes_system_prompt(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        ai_gen.generate_response(query="test")
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert AIGenerator.SYSTEM_PROMPT in call_kwargs["system"]

    def test_conversation_history_appended_to_system(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        ai_gen.generate_response(query="test", conversation_history="User: hi\nAssistant: hello")
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert "Previous conversation:" in call_kwargs["system"]
        assert "User: hi" in call_kwargs["system"]

    def test_no_history_no_previous_section(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        ai_gen.generate_response(query="test", conversation_history=None)
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert "Previous conversation:" not in call_kwargs["system"]

    def test_tools_passed_when_provided(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        tools = [{"name": "search_course_content", "input_schema": {}}]
        ai_gen.generate_response(query="test", tools=tools)
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert call_kwargs["tools"] == tools
        assert call_kwargs["tool_choice"] == {"type": "auto"}

    def test_no_tools_key_when_none(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        ai_gen.generate_response(query="test", tools=None)
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert "tools" not in call_kwargs


# ---------------------------------------------------------------------------
# generate_response — tool use flow
# ---------------------------------------------------------------------------

class TestToolExecution:
    def test_tool_use_triggers_second_api_call(self, ai_gen, mock_tool_manager):
        # First call returns tool_use
        tool_block = _make_tool_use_block("search_course_content", {"query": "ML"})
        first_resp = _make_response([tool_block], stop_reason="tool_use")
        # Second call returns final text
        final_resp = _make_response([_make_text_block("Final answer")])
        ai_gen.client.messages.create.side_effect = [first_resp, final_resp]

        result = ai_gen.generate_response(
            query="What is ML?",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )
        assert result == "Final answer"
        assert ai_gen.client.messages.create.call_count == 2
        mock_tool_manager.execute_tool.assert_called_once_with(
            "search_course_content", query="ML"
        )

    def test_tool_result_sent_back_to_api(self, ai_gen, mock_tool_manager):
        tool_block = _make_tool_use_block("search_course_content", {"query": "x"}, tool_id="t1")
        first_resp = _make_response([tool_block], stop_reason="tool_use")
        final_resp = _make_response([_make_text_block("done")])
        ai_gen.client.messages.create.side_effect = [first_resp, final_resp]

        ai_gen.generate_response(
            query="q", tools=[{}], tool_manager=mock_tool_manager
        )

        second_call_kwargs = ai_gen.client.messages.create.call_args_list[1][1]
        messages = second_call_kwargs["messages"]
        # Should have: user msg, assistant tool_use, user tool_result
        assert len(messages) == 3
        tool_result_msg = messages[2]
        assert tool_result_msg["role"] == "user"
        assert tool_result_msg["content"][0]["tool_use_id"] == "t1"
        assert tool_result_msg["content"][0]["content"] == "tool result text"

    def test_multiple_tool_calls_in_one_response(self, ai_gen, mock_tool_manager):
        block1 = _make_tool_use_block("search_course_content", {"query": "a"}, "t1")
        block2 = _make_tool_use_block("get_course_outline", {"course_name": "ML"}, "t2")
        first_resp = _make_response([block1, block2], stop_reason="tool_use")
        final_resp = _make_response([_make_text_block("combined")])
        ai_gen.client.messages.create.side_effect = [first_resp, final_resp]

        result = ai_gen.generate_response(
            query="q", tools=[{}], tool_manager=mock_tool_manager
        )
        assert result == "combined"
        assert mock_tool_manager.execute_tool.call_count == 2

    def test_no_tool_execution_without_tool_manager(self, ai_gen):
        """If stop_reason is tool_use but no tool_manager provided, return text."""
        text_block = _make_text_block("partial")
        resp = _make_response([text_block], stop_reason="tool_use")
        ai_gen.client.messages.create.return_value = resp

        result = ai_gen.generate_response(query="q")
        # Falls through to return content[0].text since tool_manager is None
        assert result == "partial"

    def test_intermediate_call_includes_tools(self, ai_gen, mock_tool_manager):
        """After round 1, the follow-up call includes tools (allowing a second round)."""
        tool_block = _make_tool_use_block("search_course_content", {"query": "x"})
        first_resp = _make_response([tool_block], stop_reason="tool_use")
        final_resp = _make_response([_make_text_block("done")])
        ai_gen.client.messages.create.side_effect = [first_resp, final_resp]

        ai_gen.generate_response(
            query="q", tools=[{"name": "t"}], tool_manager=mock_tool_manager
        )
        second_call_kwargs = ai_gen.client.messages.create.call_args_list[1][1]
        assert "tools" in second_call_kwargs


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_api_error_propagates(self, ai_gen):
        ai_gen.client.messages.create.side_effect = Exception("API down")
        with pytest.raises(Exception, match="API down"):
            ai_gen.generate_response(query="test")

    def test_empty_query(self, ai_gen):
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("I need more info")]
        )
        result = ai_gen.generate_response(query="")
        assert isinstance(result, str)

    def test_empty_conversation_history_string(self, ai_gen):
        """Empty string should be falsy, so no 'Previous conversation' section."""
        ai_gen.client.messages.create.return_value = _make_response(
            [_make_text_block("ok")]
        )
        ai_gen.generate_response(query="test", conversation_history="")
        call_kwargs = ai_gen.client.messages.create.call_args[1]
        assert "Previous conversation:" not in call_kwargs["system"]


# ---------------------------------------------------------------------------
# Multi-round tool execution
# ---------------------------------------------------------------------------

class TestMultiRoundToolExecution:
    def test_two_sequential_tool_rounds(self, ai_gen, mock_tool_manager):
        """Claude calls a tool, gets results, calls another tool, then gives final answer."""
        tool_block_1 = _make_tool_use_block("get_course_outline", {"course_name": "ML"}, "t1")
        resp1 = _make_response([tool_block_1], stop_reason="tool_use")
        tool_block_2 = _make_tool_use_block("search_course_content", {"query": "neural nets"}, "t2")
        resp2 = _make_response([tool_block_2], stop_reason="tool_use")
        resp_final = _make_response([_make_text_block("Two-round answer")])

        ai_gen.client.messages.create.side_effect = [resp1, resp2, resp_final]

        result = ai_gen.generate_response(
            query="Find courses related to lesson 4 of ML",
            tools=[{"name": "get_course_outline"}, {"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )
        assert result == "Two-round answer"
        assert ai_gen.client.messages.create.call_count == 3
        assert mock_tool_manager.execute_tool.call_count == 2

    def test_intermediate_call_includes_tools(self, ai_gen, mock_tool_manager):
        """Between round 1 and round 2, the API call includes tools."""
        tool_block_1 = _make_tool_use_block("search_course_content", {"query": "q"}, "t1")
        resp1 = _make_response([tool_block_1], stop_reason="tool_use")
        resp_text = _make_response([_make_text_block("done")], stop_reason="end_turn")

        ai_gen.client.messages.create.side_effect = [resp1, resp_text]

        tools = [{"name": "search_course_content"}]
        ai_gen.generate_response(query="q", tools=tools, tool_manager=mock_tool_manager)

        # round_count=0, not final round (0+1 < 2), so tools should be included
        second_call_kwargs = ai_gen.client.messages.create.call_args_list[1][1]
        assert "tools" in second_call_kwargs

    def test_final_round_omits_tools(self, ai_gen, mock_tool_manager):
        """After MAX_TOOL_ROUNDS tool rounds, the synthesis call omits tools."""
        tool_block_1 = _make_tool_use_block("search_course_content", {"query": "a"}, "t1")
        resp1 = _make_response([tool_block_1], stop_reason="tool_use")
        tool_block_2 = _make_tool_use_block("get_course_outline", {"course_name": "X"}, "t2")
        resp2 = _make_response([tool_block_2], stop_reason="tool_use")
        resp_final = _make_response([_make_text_block("final")])

        ai_gen.client.messages.create.side_effect = [resp1, resp2, resp_final]

        tools = [{"name": "search_course_content"}, {"name": "get_course_outline"}]
        ai_gen.generate_response(query="q", tools=tools, tool_manager=mock_tool_manager)

        # Third API call (after 2 tool rounds) must have no tools
        third_call_kwargs = ai_gen.client.messages.create.call_args_list[2][1]
        assert "tools" not in third_call_kwargs

    def test_messages_grow_correctly_across_rounds(self, ai_gen, mock_tool_manager):
        """Final call has 5 messages: user, asst(tool1), user(result1), asst(tool2), user(result2)."""
        tool_block_1 = _make_tool_use_block("search_course_content", {"query": "a"}, "t1")
        resp1 = _make_response([tool_block_1], stop_reason="tool_use")
        tool_block_2 = _make_tool_use_block("get_course_outline", {"course_name": "X"}, "t2")
        resp2 = _make_response([tool_block_2], stop_reason="tool_use")
        resp_final = _make_response([_make_text_block("done")])

        ai_gen.client.messages.create.side_effect = [resp1, resp2, resp_final]

        ai_gen.generate_response(query="q", tools=[{}], tool_manager=mock_tool_manager)

        third_call_kwargs = ai_gen.client.messages.create.call_args_list[2][1]
        messages = third_call_kwargs["messages"]
        assert len(messages) == 5
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"
        assert messages[3]["role"] == "assistant"
        assert messages[4]["role"] == "user"
        assert messages[2]["content"][0]["tool_use_id"] == "t1"
        assert messages[4]["content"][0]["tool_use_id"] == "t2"

    def test_early_exit_when_claude_stops_using_tools(self, ai_gen, mock_tool_manager):
        """If Claude returns text after round 1, only 2 API calls total."""
        tool_block_1 = _make_tool_use_block("search_course_content", {"query": "q"}, "t1")
        resp1 = _make_response([tool_block_1], stop_reason="tool_use")
        resp_text = _make_response([_make_text_block("Enough info")], stop_reason="end_turn")

        ai_gen.client.messages.create.side_effect = [resp1, resp_text]

        result = ai_gen.generate_response(
            query="q",
            tools=[{"name": "search_course_content"}],
            tool_manager=mock_tool_manager,
        )
        assert result == "Enough info"
        assert ai_gen.client.messages.create.call_count == 2

    def test_tool_error_returns_graceful_message(self, ai_gen, mock_tool_manager):
        """If tool raises an exception, error string is sent to Claude."""
        tool_block = _make_tool_use_block("search_course_content", {"query": "x"}, "t1")
        resp1 = _make_response([tool_block], stop_reason="tool_use")
        resp_final = _make_response([_make_text_block("Sorry, I could not search")])

        ai_gen.client.messages.create.side_effect = [resp1, resp_final]
        mock_tool_manager.execute_tool.side_effect = Exception("DB connection failed")

        result = ai_gen.generate_response(query="q", tools=[{}], tool_manager=mock_tool_manager)
        assert result == "Sorry, I could not search"

        second_call_msgs = ai_gen.client.messages.create.call_args_list[1][1]["messages"]
        tool_result_content = second_call_msgs[2]["content"][0]["content"]
        assert "Tool execution error" in tool_result_content
        assert "DB connection failed" in tool_result_content

    def test_max_rounds_constant(self):
        assert AIGenerator.MAX_TOOL_ROUNDS == 2
