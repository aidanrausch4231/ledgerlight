import json
import stat
import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import charts
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.config import config_dir
from ledgerlight.crypto import decrypt, encrypt, get_or_create_key
from ledgerlight.db import connect
from ledgerlight.demo import seed

SQL = "SELECT category, SUM(-amount) AS spend FROM transactions GROUP BY category"


def test_crypto():
    key = get_or_create_key()
    encrypted = encrypt("synthetic-token-☕")
    assert encrypted != "synthetic-token-☕"
    assert decrypt(encrypted) == "synthetic-token-☕"
    assert get_or_create_key() == key
    assert stat.S_IMODE((config_dir() / "key").stat().st_mode) == 0o600
    assert stat.S_IMODE(config_dir().stat().st_mode) == 0o700


@pytest.mark.parametrize("operation", ["fsync", "link"])
def test_key_creation_failure_cleans_temporary(monkeypatch, operation):
    def fail(*args):
        raise OSError("synthetic key creation failure")

    with monkeypatch.context() as patch:
        patch.setattr(f"ledgerlight.crypto.os.{operation}", fail)
        with pytest.raises(OSError, match="synthetic key creation failure"):
            get_or_create_key()
    assert list(config_dir().iterdir()) == []
    get_or_create_key()
    assert [path.name for path in config_dir().iterdir()] == ["key"]


def test_key_paths_are_ignored():
    paths = ["key", ".key-synthetic", "config/key", "config/.key-synthetic"]
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "--stdin"],
        input="\n".join(paths) + "\n",
        text=True,
        capture_output=True,
        check=True,
        cwd=Path(__file__).resolve().parents[1],
    )
    assert result.stdout.splitlines() == paths


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO accounts (id, name) VALUES ('bad', 'bad')",
        "DELETE FROM transactions",
        "DROP TABLE transactions",
        "SELECT 1; SELECT 2",
        "not SQL",
        "PRAGMA user_version = 99",
        "ATTACH DATABASE ':memory:' AS extra",
        "WITH x AS (SELECT 1) DELETE FROM transactions",
        "",
    ],
)
def test_sql_rejects(sql):
    seed()
    with pytest.raises(ValueError):
        charts.validate_sql(sql)
    with connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 124
        )


def test_seed_select_specs_and_versions():
    assert seed() == seed() == {"synthetic": True, "accounts": 2, "transactions": 124}
    columns, rows = charts.validate_sql(SQL + "; -- one trailing terminator is fine")
    assert columns == ["category", "spend"] and rows
    with connect() as connection:
        assert (
            connection.execute("SELECT COUNT(*) FROM transactions").fetchone()[0] == 124
        )
    for kind in ["bar", "line", "area", "arc"]:
        spec = charts.build_spec(kind, columns)
        assert spec["mark"] == kind
        assert ("theta" if kind == "arc" else "y") in spec["encoding"]
    saved = charts.add("Demo", SQL, "bar")
    edited = charts.add("Updated", SQL, "line", chart_id=saved["id"])
    assert edited["version"] == 2
    assert edited["created_at"] == saved["created_at"]
    with pytest.raises(ValueError):
        charts.add("Bad", "SELECT 1", "bar")
    assert len(charts.list_charts()) == 1


def test_cli_chart_lifecycle_and_errors():
    runner = CliRunner()

    def run(*args, success=True):
        result = runner.invoke(cli, ["--json", *args])
        assert (result.exit_code == 0) == success, result.output
        return json.loads(result.output)

    assert run("version")["version"]
    assert run("demo", "seed")["synthetic"]
    saved = run("chart", "add", "--title", "Spend", "--sql", SQL, "--type", "bar")
    assert run("chart", "list") == [saved]
    assert run("chart", "show", str(saved["id"])) == saved
    assert run(
        "chart",
        "add",
        "--title",
        "x",
        "--type",
        "bar",
        "--sql",
        "DELETE FROM transactions",
        success=False,
    )["error"]
    assert run("chart", "show", "999", success=False)["error"]
    assert run("chart", "add", success=False)["error"]
    assert run("no-such-command", success=False)["error"]
    assert run("chart", "remove", str(saved["id"])) == {"removed": saved["id"]}
    assert run("chart", "list") == []
    assert run("chart", "remove", "999", success=False)["error"]


@pytest.mark.parametrize(
    "expression, expected",
    [
        ("X'00ff80'", "00ff80"),
        ("X''", ""),
        ("randomblob(2)", None),
        ("1e999", None),
        ("-1e999", None),
    ],
)
def test_chart_json_safe_rows(expression, expected):
    runner = CliRunner()
    sql = f"SELECT {expression} AS category, 1 AS value"
    saved = runner.invoke(
        cli,
        ["--json", "chart", "add", "--title", "Safe", "--sql", sql, "--type", "bar"],
    )
    assert saved.exit_code == 0, saved.output
    chart_id = json.loads(saved.output)["id"]
    listed = runner.invoke(cli, ["--json", "chart", "list"])
    shown = runner.invoke(cli, ["--json", "chart", "show", str(chart_id)])
    assert listed.exit_code == shown.exit_code == 0
    with TestClient(app) as client:
        response = client.get("/api/charts")
    assert response.status_code == 200
    results = [
        json.loads(saved.output),
        json.loads(listed.output)[0],
        json.loads(shown.output),
        response.json()[0],
    ]
    for result in results:
        json.dumps(result, allow_nan=False)
        row = result["rows"][0]
        assert row["value"] == 1
        if expression == "randomblob(2)":
            assert isinstance(row["category"], str)
            assert len(row["category"]) == 4
            assert len(bytes.fromhex(row["category"])) == 2
        else:
            assert row["category"] == expected


def test_nonfinite_scalar_normalization():
    # SQLite maps NaN to NULL itself; exercise the boundary explicitly too.
    for value in [float("nan"), float("inf"), -float("inf")]:
        assert charts._json_value(value) is None
    for value in [None, "text", 42, 1.25]:
        assert charts._json_value(value) == value


def test_api():
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/api/charts").json() == []
        seed()
        saved = charts.add("Spend", SQL, "bar")
        response = client.get("/api/charts")
        assert response.status_code == 200
        assert response.json() == [saved]
        assert response.json()[0]["rows"]
        assert response.json()[0]["spec"]["mark"] == "bar"


def test_serve_loopback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "ledgerlight.cli.uvicorn.run", lambda *a, **kw: calls.append(kw)
    )
    result = CliRunner().invoke(cli, ["--json", "serve", "--port", "8765"])
    assert result.exit_code == 0
    assert json.loads(result.output) == {"host": "127.0.0.1", "port": 8765}
    assert calls == [{"host": "127.0.0.1", "port": 8765}]
    rejected = CliRunner().invoke(cli, ["--json", "serve", "--host", "0.0.0.0"])
    assert rejected.exit_code != 0 and json.loads(rejected.output)["error"]

    def failed_start(*args, **kwargs):
        raise SystemExit(1)

    monkeypatch.setattr("ledgerlight.cli.uvicorn.run", failed_start)
    failed = CliRunner().invoke(cli, ["--json", "serve"])
    assert failed.exit_code != 0
    assert json.loads(failed.output.splitlines()[-1])["error"]
