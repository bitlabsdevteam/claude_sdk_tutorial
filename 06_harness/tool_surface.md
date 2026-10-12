# 6.6 Tool surface design

The **tool surface** is the set of actions you let the model take. It decides what the model can do, what your harness can control, and how many tokens every request costs. Claude emits tool calls; your harness decides what happens to them. The *shape* of those calls is what you get to gate.

## Few general tools or many narrow ones?

| | General (bash, text editor) | Narrow (`send_email`, `delete_ticket`) |
|---|---|---|
| Breadth | Almost any action | Only what you built |
| What the harness sees | An opaque command string | Typed arguments, a named action |
| Gating / audit | Hard (`bash -c "curl -X POST ..."`) | Easy (approve `send_email`, log `delete_ticket`) |
| Parallel safety | Unknown (`grep` vs `git push`) | Known per tool |
| Tokens | One small definition | Every definition is paid on every request |

**Rule of thumb:** start general for breadth, then *promote* an action to a dedicated tool when you need to **gate, render, audit, or parallelize** it.

Promote when the action is:
- **Irreversible or outward-facing** (delete, send, pay, deploy): gate it behind approval (`common/harness.py`, 6.9).
- **Sensitive to staleness** (an edit tool can reject a write if the file changed since it was read; bash can't).
- **Read-only and common** (glob, grep): mark it safe to run in parallel.

Anthropic-provided tools (bash, text editor, code execution, web search/fetch, memory) are good starting points: the model is trained on their shapes.

## Keeping the surface small

- **Least privilege:** read-only by default; a tool that can write needs a reason. Narrow credentials per tool.
- **Defer what's rarely used:** `defer_loading` plus tool search (4.7) keeps dozens of tools from bloating every request.
- **Batch many calls with code:** programmatic tool calling (6.7) lets the model loop over a tool in a script and return only the summary.
- **Make errors teach:** return `is_error` with a recovery hint (02_tools/tool_design.md), and make denials do the same (`common/harness.py`).

## Checklist for a new tool

1. Could an existing tool do it? (Don't add a tool for one prompt.)
2. Is it reversible? If not: dedicated tool, approval gate, audit event.
3. What is the worst a confused or manipulated model could do with it? Limit to that.
4. Are arguments validated and paths confined (`common/workspace_tools.py`)?
5. Is its output bounded (size cap, explicit truncation)?
6. Is there a test showing the policy denies what it should?
