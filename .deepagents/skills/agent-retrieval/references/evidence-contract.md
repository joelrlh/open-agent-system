# Evidence Contract

Return a list containing no more than 10 records. Every record uses this shape:

```json
{
  "source_id": "stable fixture identifier",
  "uri": "canonical URI returned by the tool",
  "title": "source title",
  "excerpt": "bounded relevant evidence",
  "injection_detected": false,
  "truncated": false
}
```

Preserve `source_id` and `uri` exactly as returned. Keep `excerpt` at or below
4 KiB of UTF-8. Do not place credentials, environment values, tool arguments
unrelated to the question, or chain-of-thought in a record.

The final specialist result also includes `status`, `searches_attempted`,
`tool_calls_used`, and `truncated`. Valid status values are `ok`,
`insufficient_evidence`, and `policy_denied`.
