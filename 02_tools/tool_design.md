# 2.5 Tool design

The model only knows a tool by its **name, description, and schema**. Treat them as the tool's entire UI.

## Naming
- Verb-noun, specific: `get_weather`, `search_tickets`, not `weather` or `tool1`.
- Prefix by system when you have many (`jira_create_issue`, `jira_search`) so the model can tell them apart.

## Descriptions
- Say **what it does, when to use it, and when not to**. ("Current weather for one city; not a forecast.")
- Mention units, formats, and limits the model can't guess.
- 3-4 sentences beats one word. Put examples in the parameter descriptions.

## Schemas
- Use `enum` for closed sets, `required` for mandatory fields, and `additionalProperties: false`.
- Set `strict: true` so `tool_use.input` is guaranteed to match the schema.
- Prefer few, clearly typed parameters. Avoid free-form "options" blobs.
- Always parse inputs with `json.loads`/`block.input` objects; never string-match serialized JSON.

## Results
- Return only what the model needs; large dumps waste context and distract it.
- Prefer human-readable names over opaque ids where the model must reason about them.
- Don't silently truncate: say so ("showing 10 of 240; narrow the query").

## Errors that help the model recover
Return `is_error: true` with a message that says **what went wrong and what to try next**:

| Poor | Better |
|---|---|
| `Error` | `No data for 'Atlantis'. Known cities: london, paris, tokyo.` |
| `Invalid input` | `Could not parse '2 +' as an arithmetic expression.` |
| `Forbidden` | `Not allowed to delete tickets. Ask the user to approve, or use close_ticket.` |

Never drop a failed call: every `tool_use` needs a matching `tool_result`, or the next request is a 400.

## Safety
- Least privilege: expose read-only tools unless writes are required.
- Gate destructive tools with an approval step (Level 6).
- Tool output is untrusted data; it can contain prompt injection (Level 4.8).

## Few general vs many narrow tools
Start with a handful of narrow tools. If the list grows past ~20, consider tool search or `defer_loading` (4.7).
