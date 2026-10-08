import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "ledgerlight"


def test_plugin_skill_matches_packaged_skill():
    packaged = (ROOT / "src" / "ledgerlight" / "SKILL.md").read_bytes()
    plugin = (PLUGIN / "skills" / "ledgerlight" / "SKILL.md").read_bytes()
    assert plugin == packaged, (
        "plugins/ledgerlight/skills/ledgerlight/SKILL.md differs from "
        "src/ledgerlight/SKILL.md; run: "
        "cp src/ledgerlight/SKILL.md plugins/ledgerlight/skills/ledgerlight/SKILL.md"
    )


def test_marketplace_points_at_plugin():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == "ledgerlight")
    assert (ROOT / entry["source"]).resolve() == PLUGIN.resolve()
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["name"] == "ledgerlight"


def test_plugin_mcp_launches_stdio_server():
    server = json.loads((PLUGIN / ".mcp.json").read_text())["mcpServers"]["ledgerlight"]
    assert server["command"] == "uvx"
    assert server["args"][-2:] == ["ledgerlight", "mcp"]
