import pytest

from ledgerlight import price_client


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    for name in (
        "PLAID_CLIENT_ID",
        "PLAID_SECRET",
        "LEDGERLIGHT_FAKE_PLAID",
        "LEDGERLIGHT_FAKE_PRICES",
        "LEDGERLIGHT_TODAY",
        "LEDGERLIGHT_HISTORY_DAYS",
        "LEDGERLIGHT_LLM_PROVIDER",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "OLLAMA_HOST",
        "OLLAMA_MODEL",
        "LEDGERLIGHT_OPENAI_MODEL",
        "LEDGERLIGHT_CLAUDE_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.setenv("LEDGERLIGHT_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("LEDGERLIGHT_CONFIG_DIR", str(tmp_path / "config"))


@pytest.fixture(autouse=True)
def no_price_network(monkeypatch):
    """The real price client must never be called in tests: fail loudly."""

    def refuse(self, url, params, headers=None):
        raise AssertionError("price_client network call in tests")

    monkeypatch.setattr(price_client.PriceClient, "_request", refuse)
