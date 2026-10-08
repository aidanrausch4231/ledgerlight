# ledgerlight web shell

See [component context](context.md) and [root setup](../README.md).

From the repository root run `uv run ledgerlight serve`. In this directory:

```sh
pnpm install --frozen-lockfile
pnpm dev
pnpm lint
pnpm build
```

Vite proxies `/api` to 127.0.0.1:8000. For production, build and restart the API
from the source checkout to serve `dist/`. This is a saved-chart gallery, not the
planned bank-linking or chat UI. Never add secrets to frontend environment vars.
