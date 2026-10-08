"""Only LLM/remote transcription network boundary. httpx, no vendor SDKs."""

import json
import os
import re
from uuid import uuid4

import httpx

from ledgerlight import money

DEFAULTS = {
    "local": ("OLLAMA_MODEL", "hf.co/unsloth/Qwen3.6-35B-A3B-GGUF:UD-Q4_K_M"),
    "claude": ("LEDGERLIGHT_CLAUDE_MODEL", "claude-sonnet-5-5"),
    "openai": ("LEDGERLIGHT_OPENAI_MODEL", "gpt-5.5"),
    "fake": ("", "synthetic-test-model"),
}
KEYS = {"claude": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def redact(value):
    def scrub(item):
        if isinstance(item, str):
            for name in (*KEYS.values(), "PLAID_SECRET", "PLAID_CLIENT_ID"):
                secret = os.environ.get(name)
                if secret:
                    item = item.replace(secret, "[redacted]")
        elif isinstance(item, dict):
            return {scrub(key): scrub(value) for key, value in item.items()}
        elif isinstance(item, (list, tuple)):
            return [scrub(value) for value in item]
        return item

    # Scrub strings before serialization so JSON escaping cannot hide secrets.
    value = scrub(value)
    return value if isinstance(value, str) else json.dumps(value)


def status():
    provider = os.environ.get("LEDGERLIGHT_LLM_PROVIDER") or money.settings_get().get(
        "llm_provider", "local"
    )
    if provider not in DEFAULTS:
        raise ValueError("Unknown LLM provider")
    # Fake is only selectable by an explicit environment variable, never settings.
    if provider == "fake" and os.environ.get("LEDGERLIGHT_LLM_PROVIDER") != "fake":
        raise ValueError("Fake provider requires explicit test environment")
    env, default = DEFAULTS[provider]
    return {
        "provider": provider,
        "model": redact(os.environ.get(env) or default),
        "key_present": bool(os.environ.get(KEYS.get(provider, ""))),
        "overridden": bool(os.environ.get("LEDGERLIGHT_LLM_PROVIDER")),
    }


def call(name, args):
    return {"id": str(uuid4()), "name": name, "arguments": args}


def fake(messages, state):
    """Deterministic scripted scenarios exercise the same CLI/frontend loop."""
    user_index = max(
        (i for i, m in enumerate(messages) if m["role"] == "user"), default=0
    )
    text = str(messages[user_index].get("content", "")).lower()
    results = [m for m in messages[user_index + 1 :] if m["role"] == "tool"]
    calls = [c for m in messages[user_index + 1 :] for c in m.get("tool_calls", [])]
    if results:
        last = json.loads(results[-1]["content"])
        if calls and calls[-1]["function"]["name"] == "run_ledgerlight":
            if "proposal_id" in last:
                return "Please review this change.", [call("propose_change", last)]
            if "charts" in last:
                summary = (
                    f"Your matched spending totals ${last['total']:.2f}, "
                    f"averaging ${last['average_per_month']:.2f} per month. "
                    f"This month: ${last['this_month']:.2f}; "
                    f"last month: ${last['last_month']:.2f}."
                )
                if not last["charts"]:
                    summary = "No matching posted expenses. Try: " + ", ".join(
                        last.get("suggestions", [])
                    )
                return summary, [
                    call(
                        "show_answer",
                        {
                            "title": "Spending answer",
                            "summary": summary,
                            "charts": last["charts"],
                        },
                    )
                ]
            if "spec" in last:
                return "Here is your chart. Save it to keep it on Home.", [
                    call("show_chart", {"chart": last})
                ]
            return json.dumps(last), []
        if "budgets" in text and "open" in text:
            return "Navigation result received.", []
        return "Done. Review the result in the app.", []
    if "coffee" in text or "how much" in text or "my" in text and "spend" in text:
        return "Looking up your spending.", [
            call("run_ledgerlight", {"args": ["spending", "ask", text]})
        ]
    if "reset" in text and "home" in text:
        return "Restoring your default Home layout.", [call("reset_home", {})]
    if "move" in text:
        cards = (state or {}).get("dashboard", {}).get("cards", [])
        card = next((c for c in cards if c["kind"] == "spending_vs_last_month"), None)
        return "Moving the comparison card.", [
            call(
                "dashboard_move",
                {
                    "id": card["id"] if card else "spending_vs_last_month",
                    "x": 0,
                    "y": 0,
                },
            )
        ]
    if "budget" in text and "set" in text:
        amount = re.search(r"\d+(?:\.\d+)?", text)
        return "I will propose that budget, not apply it.", [
            call(
                "run_ledgerlight",
                {
                    "args": [
                        "budgets",
                        "set",
                        "Dining",
                        amount[0] if amount else "400",
                        "--propose",
                    ],
                },
            )
        ]
    if "category" in text or "html" in text:
        args = [
            "chart",
            "preview",
            "--title",
            "Spending by category",
            "--sql",
            "SELECT category, SUM(-amount) AS spent FROM transactions "
            "WHERE amount < 0 AND pending=0 AND hidden=0 GROUP BY category",
            "--type",
            "html" if "html" in text else "bar",
        ]
        if "html" in text:
            args += [
                "--html",
                '<div id="result">Waiting</div><script>'
                'onmessage=e=>{document.querySelector("#result").textContent='
                '"Rows: "+e.data.rows.length;fetch("https://example.invalid/")'
                '.catch(()=>document.body.dataset.blocked="yes")}</script>',
            ]
        return "Looking up posted spending.", [call("run_ledgerlight", {"args": args})]
    if "open" in text:
        page = next(
            (p for p in ("budgets", "transactions", "settings", "home") if p in text),
            "home",
        )
        return "Opening " + page + ".", [call("ui_navigate", {"page": page})]
    return "Reading your spending summary.", [
        call("run_ledgerlight", {"args": ["spending", "summary"]})
    ]


def anthropic_messages(messages):
    result = []
    for message in messages:
        role = message["role"]
        if role == "tool":
            item = {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": message["tool_call_id"],
                        "content": message["content"],
                    }
                ],
            }
        else:
            content = []
            if message.get("content"):
                content.append({"type": "text", "text": message["content"]})
            for tool in message.get("tool_calls", []):
                content.append(
                    {
                        "type": "tool_use",
                        "id": tool["id"],
                        "name": tool["function"]["name"],
                        "input": json.loads(tool["function"]["arguments"]),
                    }
                )
            item = {"role": role, "content": content or [{"type": "text", "text": " "}]}
        if result and result[-1]["role"] == item["role"]:
            result[-1]["content"].extend(item["content"])
        else:
            result.append(item)
    return result


def stream(messages, tools, system, state=None):
    """Yield text deltas and assembled tool calls from native streaming APIs."""
    info = status()
    provider = info["provider"]
    if provider == "fake":
        text, calls = fake(messages, state)
        yield "text", text
        for value in calls:
            yield "call", value
        return
    if provider in KEYS and not info["key_present"]:
        raise ValueError("Provider API key is not configured")
    headers = {"Content-Type": "application/json"}
    if provider == "claude":
        url = "https://api.anthropic.com/v1/messages"
        headers.update(
            {"x-api-key": os.environ[KEYS[provider]], "anthropic-version": "2023-06-01"}
        )
        payload = {
            "model": info["model"],
            "system": system,
            "max_tokens": 4096,
            "messages": anthropic_messages(messages),
            "stream": True,
            "tools": [
                {
                    "name": t["name"],
                    "description": t["description"],
                    "input_schema": t["parameters"],
                }
                for t in tools
            ],
        }
    else:
        base = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
        url = (
            base + "/v1/chat/completions"
            if provider == "local"
            else "https://api.openai.com/v1/chat/completions"
        )
        if provider == "openai":
            headers["Authorization"] = "Bearer " + os.environ[KEYS[provider]]
        payload = {
            "model": info["model"],
            "stream": True,
            "messages": [{"role": "system", "content": system}, *messages],
            "tools": [{"type": "function", "function": t} for t in tools],
        }
    calls = {}
    try:
        with httpx.Client(timeout=90, trust_env=False) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data: ") or line[6:] == "[DONE]":
                        continue
                    event = json.loads(line[6:])
                    if provider == "claude":
                        kind = event.get("type")
                        if kind == "error":
                            raise ValueError("Provider request failed")
                        if kind == "content_block_start":
                            block = event["content_block"]
                            if block["type"] == "tool_use":
                                calls[event["index"]] = {
                                    "id": block["id"],
                                    "name": block["name"],
                                    "arguments": "",
                                }
                        elif kind == "content_block_delta":
                            delta = event["delta"]
                            if delta["type"] == "text_delta":
                                yield "text", delta["text"]
                            elif delta["type"] == "input_json_delta":
                                calls[event["index"]]["arguments"] += delta[
                                    "partial_json"
                                ]
                    else:
                        for choice in event.get("choices", []):
                            delta = choice.get("delta", {})
                            if delta.get("content"):
                                yield "text", delta["content"]
                            for tool in delta.get("tool_calls", []):
                                target = calls.setdefault(
                                    tool["index"],
                                    {"id": "", "name": "", "arguments": ""},
                                )
                                target["id"] += tool.get("id", "")
                                for key in ("name", "arguments"):
                                    target[key] += tool.get("function", {}).get(key, "")
        for value in calls.values():
            value["arguments"] = json.loads(value["arguments"] or "{}")
            yield "call", value
    except Exception as exc:
        # Never include response bodies, request headers, URLs or exception text.
        raise ValueError(
            "Provider request failed; check configuration and availability"
        ) from exc


def transcribe_openai(audio, filename):
    try:
        with httpx.Client(timeout=120, trust_env=False) as client:
            response = client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": "Bearer " + os.environ["OPENAI_API_KEY"]},
                data={"model": "whisper-1"},
                files={"file": (filename, audio)},
            )
            response.raise_for_status()
            return redact(response.json()["text"])
    except Exception as exc:
        raise ValueError("Transcription failed; check provider configuration") from exc
