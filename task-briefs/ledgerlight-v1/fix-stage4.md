# Stage 4 correction (builder)

Fix exactly this reviewer finding on branch `v1-stage4-agent`, then run
`bash scripts/check.sh` until it exits 0. Do not change anything else. Never use
git stash, never commit. Never touch `.env*`, `task-briefs/`, `design/`, `web/public/`.

HIGH — `src/ledgerlight/agent.py:176` and `src/ledgerlight/proposals.py:89`:
provider tool arguments are redacted only for SSE, while the original arguments
execute. A malicious provider can place a configured API key (e.g.
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PLAID_SECRET`) inside a proposed
mutation; the key is persisted and returned unredacted by
`GET /api/proposals/{id}`.

Fix:
1. Before executing any backend tool call, reject it (tool error result
   returned to the model, nothing executed, nothing stored) when its arguments
   contain any configured secret value (reuse `llm_client.redact` / its secret
   list; do not add a second secret list).
2. Defensively redact proposal `command`, `summary` and `diff` on read
   (`get`/list/API) and refuse to apply a stored proposal whose command contains
   a configured secret.
3. Regression tests: a fake provider returns a `run_ledgerlight` propose call
   whose args include the `OPENAI_API_KEY` value → no proposal row is created,
   the SSE stream and every `/api/proposals` response never contain the key;
   a proposal row inserted directly with a secret in it is redacted on read and
   cannot be applied.

Reply: STATUS / FILES (path:line) / CHECKS (command + result).
