# Specifications context

Purpose: durable settled decisions and stage boundaries, not executable features.
Key file/entrypoint: `project-brief.md` records the owner's 2026-09-24 decisions,
scaffold scope, planned v1, security, acceptance and deferrals.
Inputs: approved decisions. Outputs: implementation contract and future
Playwright/Sandbox acceptance. Dependencies: root context and component contracts;
no runtime dependencies.

Current implementation also follows `task-briefs/ledgerlight-v1/decisions.md`
and `stage2-budgets-rules-alerts.md`. Root `bash scripts/check.sh` validates v1 stage 2
with locked installs, Ruff, pytest, web build and offline Playwright. The original
project brief remains a historical scope record; its later-stage acceptance
(chat/Save) is not yet executable; budgets/alerts now have offline coverage. Configuration/secret names are documentation only:
LEDGERLIGHT_DATA_DIR, LEDGERLIGHT_CONFIG_DIR, PLAID_CLIENT_ID, PLAID_SECRET,
PLAID_ENV, LEDGERLIGHT_LLM_PROVIDER, OLLAMA_MODEL, ANTHROPIC_API_KEY, OPENAI_API_KEY.
Never include actual values from .env or bank data.

Constraints: architecture/interface/schema/dependency changes require lead
approval (v1 stages 1–2 are approved by the binding decisions). License and specified
deferrals stay deferred. Built/tested offline: bank linking/sync, recurring,
transactions, snapshots/net worth, printable systemd units, budgets, rules,
alerts, transaction extras, spending/cash flow, bills and savings goals. Not yet
built: agent chat, providers and HTML sandbox. Never treat
remaining documented plans as completed work.
