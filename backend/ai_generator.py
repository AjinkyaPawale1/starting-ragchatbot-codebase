import anthropic
from typing import List, Optional, Dict, Any

class AIGenerator:
    """Handles interactions with Anthropic's Claude API for generating responses"""
    
    MAX_TOOL_ROUNDS = 2

    # Static system prompt to avoid rebuilding on each call
    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Tool Usage:
- Use the **search_course_content** tool for questions about specific course content or detailed educational materials
- Use the **get_course_outline** tool for questions about course structure, syllabus, outline, or lesson listings
  - When presenting outline results, always include: the course title, the course link, and for each lesson its number and title
- You may use up to 2 sequential tool calls per query when needed (e.g., first get an outline, then search based on results)
- Most questions require only one tool call
- Synthesize tool results into accurate, fact-based responses
- If a tool yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course outline/structure questions**: Use get_course_outline, then present the full outline with course title, course link, and all lessons
- **Course content questions**: Use search_course_content, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results" or "based on the tool results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""
    
    def __init__(self, api_key: str, model: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        
        # Pre-build base API parameters
        self.base_params = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": 800
        }
    
    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.
        
        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use
            tool_manager: Manager to execute tools
            
        Returns:
            Generated response as string
        """
        
        # Build system content efficiently - avoid string ops when possible
        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history 
            else self.SYSTEM_PROMPT
        )
        
        # Prepare API call parameters efficiently
        api_params = {
            **self.base_params,
            "messages": [{"role": "user", "content": query}],
            "system": system_content
        }
        
        # Add tools if available
        if tools:
            api_params["tools"] = tools
            api_params["tool_choice"] = {"type": "auto"}
        
        # Get response from Claude
        response = self.client.messages.create(**api_params)
        
        # Handle tool execution if needed
        if response.stop_reason == "tool_use" and tool_manager:
            return self._handle_tool_execution(response, api_params, tool_manager)
        
        # Return direct response
        return response.content[0].text
    
    def _handle_tool_execution(self, initial_response, base_params: Dict[str, Any], tool_manager):
        """
        Handle sequential tool calls (up to MAX_TOOL_ROUNDS) and return final text.

        Args:
            initial_response: The first response containing tool use requests
            base_params: API parameters from generate_response (includes messages/system)
            tool_manager: Manager to execute tools

        Returns:
            Final response text after all tool rounds complete
        """
        messages = base_params["messages"].copy()
        current_response = initial_response
        tools = base_params.get("tools")
        system = base_params["system"]

        for round_count in range(self.MAX_TOOL_ROUNDS):
            # Append the assistant's tool_use response
            messages.append({"role": "assistant", "content": current_response.content})

            # Execute all tool calls in the current response
            tool_results = []
            for content_block in current_response.content:
                if content_block.type == "tool_use":
                    try:
                        tool_result = tool_manager.execute_tool(
                            content_block.name,
                            **content_block.input
                        )
                    except Exception as e:
                        tool_result = f"Tool execution error: {e}"

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": content_block.id,
                        "content": tool_result
                    })

            # Append tool results as user message
            if tool_results:
                messages.append({"role": "user", "content": tool_results})

            # Include tools in intermediate rounds, omit on final round
            is_final_round = (round_count + 1) >= self.MAX_TOOL_ROUNDS
            next_params = {
                **self.base_params,
                "messages": messages,
                "system": system,
            }
            if not is_final_round and tools:
                next_params["tools"] = tools
                next_params["tool_choice"] = {"type": "auto"}

            current_response = self.client.messages.create(**next_params)

            # Exit early if Claude didn't request more tools
            if current_response.stop_reason != "tool_use":
                break

        return current_response.content[0].text