"""Playwright server with temporary storage and explicit fake/live selection."""

import os
import shutil
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory


def main():
    env = os.environ.copy()
    live = env.get("LEDGERLIGHT_E2E_PLAID") == "sandbox"
    if live and not (env.get("PLAID_CLIENT_ID") and env.get("PLAID_SECRET")):
        raise SystemExit("Live Sandbox requires PLAID_CLIENT_ID and PLAID_SECRET")
    env["PLAID_ENV"] = "sandbox"
    env["LEDGERLIGHT_FAKE_PLAID"] = "0" if live else "1"
    if not live:
        env["LEDGERLIGHT_TODAY"] = "2026-03-15"
        env["LEDGERLIGHT_LLM_PROVIDER"] = "fake"
        env["LEDGERLIGHT_FAKE_PRICES"] = "1"
    else:
        env.pop("LEDGERLIGHT_TODAY", None)
        env.pop("LEDGERLIGHT_FAKE_PRICES", None)
    with TemporaryDirectory(prefix="ledgerlight-e2e-") as directory:
        directory = env.get("LEDGERLIGHT_E2E_STORAGE", directory)
        env["LEDGERLIGHT_DATA_DIR"] = directory + "/data"
        env["LEDGERLIGHT_CONFIG_DIR"] = directory + "/config"
        process = subprocess.Popen(
            ["uv", "run", "ledgerlight", "serve", "--port", sys.argv[1]],
            env=env,
        )

        def stop(*args):
            process.terminate()

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        try:
            raise SystemExit(process.wait())
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
            if env.get("LEDGERLIGHT_E2E_STORAGE"):
                shutil.rmtree(directory, ignore_errors=True)


if __name__ == "__main__":
    main()
