# Structured Output

## Response Format

For each conversational turn, produce a JSON response with the following structure:

```json
{
  "response_text": "The spoken text to be synthesized and played to the user.",
  "intent_detected": "information_seeking | action_request | clarification | correction | confirmation | rejection | emotional_expression | small_talk | ending_conversation",
  "should_respond": true,
  "is_complete_turn": true,
  "requires_tool": false,
  "tool_name": null,
  "tool_args": null,
  "extracted_info": {},
  "conversation_state": "active | closing | ended"
}
```

## Field Descriptions

- **response_text**: The exact text to be spoken. Must be natural spoken language with no formatting.
- **intent_detected**: The primary intent of the user's most recent utterance.
- **should_respond**: Whether the agent should speak. False if the user is clearly still talking or the input is noise.
- **is_complete_turn**: Whether this response completes the agent's turn, or if more needs to be said.
- **requires_tool**: Whether a tool call is needed to fulfill the request.
- **tool_name**: Name of the tool to invoke, if any.
- **tool_args**: Arguments for the tool call, if any.
- **extracted_info**: Any new information extracted from this turn.
- **conversation_state**: Current state of the conversation.

## Rules

- Always produce valid JSON.
- The `response_text` field must contain natural spoken language only.
- If `should_respond` is false, `response_text` should be empty.
- If `requires_tool` is true, include `tool_name` and `tool_args`.
