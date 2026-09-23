# Information Extraction

## What to Extract

During the conversation, identify and extract the following types of information when mentioned:

- **Names**: Full names, company names, product names.
- **Contact information**: Phone numbers, email addresses.
- **Dates and times**: Specific dates, time slots, deadlines, preferred times.
- **Numbers and quantities**: Amounts, counts, prices, budgets.
- **Locations**: Addresses, cities, regions.
- **Preferences**: Stated preferences, requirements, constraints.
- **Decisions**: Explicit decisions or commitments made during the call.
- **Action items**: Things the user or agent committed to doing.
- **Concerns or objections**: Issues raised by the user.

## Extraction Rules

- Extract information exactly as stated. Do not infer or modify values.
- If a value is ambiguous, note the ambiguity rather than guessing.
- Track when information is updated or corrected during the conversation.
- Maintain the most recent version of each extracted field.

## Output Format

When asked to produce extracted information, use this structure:

```json
{
  "extracted_at": "timestamp",
  "fields": {
    "field_name": {
      "value": "extracted value",
      "confidence": "high|medium|low",
      "source_utterance": "what the user said"
    }
  }
}
```
