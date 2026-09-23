# Call Summary

## When to Produce a Summary

Generate a structured call summary when the conversation ends (either by user request or natural conclusion).

## Summary Structure

Produce the summary in this format:

```json
{
  "call_summary": {
    "duration_estimate": "approximate duration",
    "outcome": "completed | transferred | dropped | user_ended | agent_ended",
    "summary": "2-3 sentence overview of the call",
    "key_topics": ["topic1", "topic2"],
    "user_sentiment": "positive | neutral | negative | mixed",
    "action_items": [
      {
        "description": "what needs to be done",
        "owner": "user | agent | other",
        "deadline": "if mentioned, otherwise null"
      }
    ],
    "decisions_made": ["decision1", "decision2"],
    "extracted_information": {},
    "unresolved_issues": ["issue1", "issue2"],
    "follow_up_required": true | false,
    "follow_up_notes": "what follow-up is needed, if any"
  }
}
```

## Summary Rules

- Be factual. Only include what was actually discussed.
- Do not add information that was not part of the conversation.
- Capture the user's sentiment based on their language and responses.
- Note any commitments or promises made by either party.
- Flag unresolved issues clearly.
