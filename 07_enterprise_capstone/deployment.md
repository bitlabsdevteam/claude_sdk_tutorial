# Deployment options

| Option | Good for | Cost to you | Notes |
|---|---|---|---|
| **Own infra** (implemented here) | Full control, data residency, existing ops tooling | You run the harness, scheduling, secrets, tracing | MCP server over stdio (sidecar) or HTTP with bearer auth (see `04_mcp/server_http`); run `ops_agent.handle_ticket` from a worker/queue |
| **Bedrock / Vertex / Foundry clients** | Org already standardised on a cloud and its IAM/billing | Same harness; swap the client | Check feature parity for tools, caching and fallbacks in that provider before relying on them; `fallbacks.middleware_client` in `06_harness` covers client-side retry |
| **Managed Agents** | Least operational burden, hosted sandbox | You give up harness control | Use for the loop and sandbox; keep approvals and the audit log in your own systems |

Common requirements whichever you pick: read the API key from the environment or a secret manager, separate read and write credentials for the ticket system (`TICKET_WRITE_ENABLED`), one run id per ticket, persist `workdir` (checkpoints, journal, traces, audit log) on durable storage, and set the daily cap in the cost ledger.
