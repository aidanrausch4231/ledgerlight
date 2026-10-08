# Stage 4 notes (lead, 2026-10-04) — what exists now

Merged as the stage 4 PR. `bash scripts/check.sh`: 273 pytest tests, 7 offline
Playwright tests (1 live Sandbox test skipped).

- Agent: `src/ledgerlight/agent.py` (native AG-UI SSE; frontend tools run in the
  browser via `web/src/lib/agentTools.ts` → `uiBus`). Backend tool is only
  `run_ledgerlight` (`agent_tools.py`: Click-parsed allowlist, writes only with
  `--propose`, `dashboard list` denied because it journals versions/events).
- Proposals: `src/ledgerlight/proposals.py` — `@proposable` wraps every stage 2
  mutation (`propose=True` stores command/summary/diff, returns
  `{proposal_id, summary, diff}`), `get(id)` (redacted),
  `GET /api/proposals/{id}`, `POST /api/proposals/{id}/apply|cancel`.
  There is NO web route `#/proposals/<id>` or pending list page yet — stage 5
  adds it (the Confirm card today lives in the chat).
- Secrets: `llm_client.redact(value)` covers provider keys + PLAID_SECRET/
  CLIENT_ID; backend tool args containing a secret are rejected before running.
  MCP tools must use the same check.
- Charts: `src/ledgerlight/charts.py` `validate_sql`, `build_spec`, `preview`,
  `add`, `list_charts`, `show`, `history` (read-only), `remove`;
  `chart_api.py` `/api/charts/preview|save|{id}/edit|{id}/history`.
- Voice: `voice.py`, `/api/stt` (fake/local faster-whisper/openai).
- Actor values: user, agent, cli (stage 5 adds `mcp`).
