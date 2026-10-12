# 3.9 Choosing an agent approach

Two separate questions: **who writes the loop (harness)** and **who hosts it (deployment)**.

| Approach | You write | Harness | Deployment | Pick it when |
|---|---|---|---|---|
| **Manual loop** (`agent.py`) | The `while tool_use` loop | You | You | You need full control, or no beta dependency |
| **Tool Runner** (`@beta_tool`) | Only the tool functions | SDK | You | Custom-tool agent without writing the loop; hooks still allow approvals and logging |
| **Managed Agents** | Agent config and your tool results | Anthropic | Anthropic (sandbox) | You want Anthropic to run the loop and host the workspace; long sessions, schedules (Level 6.21) |
| **Claude Agent SDK** | A prompt and options | Claude Code's | You | A batteries-included coding/filesystem agent with built-in tools (Level 6.22) |

Notes:
- The Tool Runner is **not** the Agent SDK: it loops over tools you define and has no built-in tools.
- Whatever you pick, keep the loop bounded and log usage per turn.
- Start with the manual loop to learn the mechanics, then move to the simplest option that meets the need.
