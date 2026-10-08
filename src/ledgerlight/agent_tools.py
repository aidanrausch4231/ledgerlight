"""Strict CLI capability boundary: no shell, bounded time and output."""

import json
import selectors
import subprocess
import sys
import time

READS = {
    ("version",),
    ("accounts", "list"),
    ("accounts", "overview"),
    ("transactions", "list"),
    ("recurring", "list"),
    ("networth",),
    ("rules", "list"),
    ("budgets", "list"),
    ("budgets", "report"),
    ("spending", "summary"),
    ("spending", "ask"),
    ("cashflow",),
    ("bills", "upcoming"),
    ("alerts", "list"),
    ("settings", "get"),
    ("goals", "list"),
    ("manual", "list"),
    ("manual", "payments"),
    ("holdings", "list"),
    ("plaid", "items"),
    ("plaid", "duplicates"),
    ("chart", "preview"),
    ("chart", "show"),
    ("chart", "list"),
    ("chart", "history"),
}
WRITES = {
    ("rules", "add"),
    ("rules", "remove"),
    ("rules", "apply"),
    ("budgets", "set"),
    ("budgets", "remove"),
    *(
        ("txn", action)
        for action in ("note", "hide", "unhide", "tag", "untag", "split", "unsplit")
    ),
    ("recurring", "mark"),
    ("alerts", "dismiss"),
    ("alerts", "refresh"),
    ("settings", "set"),
    ("goals", "add"),
    ("goals", "update"),
    ("goals", "archive"),
    # Refresh/apply-paydown write balances and snapshots, so they need --propose.
    *(
        ("manual", action)
        for action in ("add", "update", "remove", "apply-paydown", "apply-payments")
    ),
    *(("holdings", action) for action in ("add", "update", "remove", "refresh")),
}
TIMEOUT = 30
OUTPUT_CAP = 64 * 1024


def validate_args(args):
    # Parse with the real Click command: a value named --propose is not consent.
    from ledgerlight.cli import cli

    if (
        not isinstance(args, list)
        or not args
        or not all(isinstance(arg, str) and "\0" not in arg for arg in args)
    ):
        raise ValueError("args must be a nonempty list of strings")
    key = (args[0],) if (args[0],) in READS else tuple(args[:2])
    if key not in READS | WRITES or any(a in {"--help", "--json"} for a in args):
        raise ValueError("Command is not allowed for the agent")
    command = cli.commands[key[0]]
    if len(key) == 2:
        command = command.commands[key[1]]
    try:
        with command.make_context("agent", args[len(key) :]) as context:
            if key in WRITES and not context.params.get("propose"):
                raise ValueError("Data changes require --propose and user confirmation")
            if key == ("settings", "set") and not (
                context.params["key"] in {"bill_days", "low_balance_threshold"}
                or context.params["key"].startswith("low_balance_threshold:")
            ):
                raise ValueError("Agent cannot change provider or credentials")
    except SystemExit as exc:
        raise ValueError("Invalid command") from exc
    return args


def run_ledgerlight(args):
    try:
        validate_args(args)
    except Exception:
        return {
            "error": "Command refused: use allowed reads or --propose money changes"
        }
    process = subprocess.Popen(
        [sys.executable, "-m", "ledgerlight.cli", "--json", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        shell=False,
    )
    output = bytearray()
    deadline = time.monotonic() + TIMEOUT
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"error": "CLI timed out after 30 seconds"}
                if not selector.select(remaining):
                    return {"error": "CLI timed out after 30 seconds"}
                chunk = process.stdout.read1(min(8192, OUTPUT_CAP + 1 - len(output)))
                if not chunk:
                    break
                output.extend(chunk)
                if len(output) > OUTPUT_CAP:
                    return {"error": "CLI output exceeded 64 KiB"}
        process.wait(timeout=max(0.01, deadline - time.monotonic()))
        try:
            result = json.loads(output)
        except (ValueError, UnicodeError):
            return {"error": "CLI returned invalid JSON"}
        return result
    except subprocess.TimeoutExpired:
        return {"error": "CLI timed out after 30 seconds"}
    finally:
        if process.poll() is None:
            process.kill()
        process.wait()
        process.stdout.close()
