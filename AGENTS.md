# ledgerlight contributor instructions

Read root `context.md` and the `context.md` of every component you touch (including
`src/ledgerlight/context.md` for Python implementation). Follow the settled scope
in `specs/project-brief.md` and binding `task-briefs/ledgerlight-v1/decisions.md`.

- Never read or commit `.env`, database files, or encryption keys. Configuration
  documentation uses names and safe placeholders only.
- Tests use only synthetic or Plaid Sandbox data, with temporary
  `LEDGERLIGHT_DATA_DIR` and `LEDGERLIGHT_CONFIG_DIR`; never personal storage.
- The CLI is the only data interface the agent uses. Every command supports the
  global `--json` flag; keep `src/ledgerlight/SKILL.md` in sync and packaged.
- Serve only on 127.0.0.1; use SSH tunnels for remote access.
- Preserve read-only chart validation and key permissions. v1 is the agreed
  scope change: Plaid/LLM calls go only through their client modules and tests
  use fakes or Sandbox. Stage briefs approve named dependencies and printable
  systemd units; do not install schedulers or make production calls in tests.
- Run `bash scripts/check.sh` before completion (locked installs, Ruff, pytest,
  frontend build and offline Playwright).
- License: MIT (see LICENSE). Never commit secrets; CI gitleaks must remain enabled.
