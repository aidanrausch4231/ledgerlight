"""Duplicate Plaid links: refusal rule, safety net, cleanup. Fake Plaid only."""

import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from ledgerlight import data, money, plaid_client, sync
from ledgerlight.api import app
from ledgerlight.cli import cli
from ledgerlight.db import connect
from ledgerlight.plaid_client import FakePlaidClient

# Fake tokens "<identity>@<key>" are separate synthetic Items at institution
# <key>; every fake Item holds the same account masks (0001 checking, 0002 credit).
FIRST = "synthetic-first@synthbank"
SECOND = "synthetic-second@synthbank"


class SpyClient(FakePlaidClient):
    def __init__(self):
        self.exchanged = []
        self.removed = []

    def exchange_public_token(self, public_token):
        self.exchanged.append(public_token)
        return super().exchange_public_token(public_token)

    def remove_item(self, access_token):
        self.removed.append(access_token)


@pytest.fixture
def spy(monkeypatch):
    monkeypatch.setenv("LEDGERLIGHT_FAKE_PLAID", "1")
    client = SpyClient()
    monkeypatch.setattr(plaid_client, "get_client", lambda: client)
    return client


def access(public_token):
    """The fake access token for a public token (no spy side effects)."""
    return FakePlaidClient().exchange_public_token(public_token)[1]


def link_unchecked(monkeypatch, public_token):
    """Simulate an Item linked before duplicate checks existed."""
    with monkeypatch.context() as patch:
        patch.setattr(sync, "find_duplicate", lambda *args, **kwargs: None)
        return sync.link(public_token)


def invoke(*args, success=True):
    result = CliRunner().invoke(cli, ["--json", *args])
    assert (result.exit_code == 0) == success, result.output
    return json.loads(result.output)


def metadata(institution_id, name="Synthetic Bank", masks=("0001",)):
    return {
        "institution": {"institution_id": institution_id, "name": name},
        "accounts": [
            {
                "name": "Synthetic Checking",
                "mask": mask,
                "type": "depository",
                "subtype": "checking",
            }
            for mask in masks
        ],
    }


def stored_institution_id(item_id):
    with connect() as db:
        return db.execute(
            "SELECT institution_id FROM plaid_items WHERE id=?", (item_id,)
        ).fetchone()[0]


def count(table):
    with connect() as db:
        return db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_duplicate_via_metadata_refused_before_exchange(spy):
    first = sync.link(FIRST)
    institution_id = stored_institution_id(first["id"])
    # The first Item had no peers, so its initial sync backfilled the id.
    assert institution_id == FakePlaidClient().institution_id(access(FIRST))
    spy.exchanged.clear()
    with pytest.raises(sync.DuplicateLinkError) as error:
        sync.link(SECOND, metadata=metadata(institution_id))
    assert spy.exchanged == [] and spy.removed == []
    assert error.value.duplicate_of == first["id"]
    assert str(error.value) == (
        "Synthetic Bank is already linked (Synthetic Checking ••0001). "
        "Remove the old link first if you want to link it again."
    )
    assert len(sync.items()) == 1
    with TestClient(app) as client:
        response = client.post(
            "/api/plaid/exchange",
            json={"public_token": SECOND, "metadata": metadata(institution_id)},
        )
    assert response.status_code == 409
    assert response.json() == {
        "error": str(error.value),
        "duplicate_of": first["id"],
        "institution": "Synthetic Bank",
        "accounts": [
            {
                "name": "Synthetic Checking",
                "mask": "0001",
                "type": "depository",
                "subtype": "checking",
            }
        ],
    }
    assert spy.exchanged == [] and len(sync.items()) == 1


def test_duplicate_via_safety_net_removes_new_item(spy):
    first = sync.link(FIRST)
    before = count("transactions"), count("accounts"), count("plaid_items")
    with TestClient(app) as client:
        response = client.post("/api/plaid/exchange", json={"public_token": SECOND})
    assert response.status_code == 409
    body = response.json()
    assert body["duplicate_of"] == first["id"]
    assert {row["mask"] for row in body["accounts"]} == {"0001", "0002"}
    assert "Synthetic Checking ••0001, Synthetic Credit ••0002" in body["error"]
    assert spy.exchanged[-1] == SECOND
    assert spy.removed == [access(SECOND)]
    assert [row["id"] for row in sync.items()] == [first["id"]]
    assert (count("transactions"), count("accounts"), count("plaid_items")) == before


def test_cli_exchange_duplicate_exits_nonzero_with_json(spy):
    first = sync.link(FIRST)
    body = invoke("plaid", "exchange", SECOND, success=False)
    assert body["duplicate_of"] == first["id"]
    assert body["institution"] == "Synthetic Bank"
    assert "already linked" in body["error"] and len(body["accounts"]) == 2
    assert spy.removed == [access(SECOND)] and len(sync.items()) == 1
    result = CliRunner().invoke(cli, ["plaid", "exchange", SECOND])
    assert result.exit_code == 1 and "already linked" in result.output


def test_same_institution_disjoint_accounts_allowed(spy):
    first = sync.link(FIRST)
    institution_id = stored_institution_id(first["id"])
    original = spy.accounts
    second_token = access(SECOND)

    def other_accounts(token):
        rows = original(token)
        if token == second_token:
            for row in rows:
                row["mask"] = "9" + row["mask"][1:]
        return rows

    spy.accounts = other_accounts
    second = sync.link(SECOND, metadata=metadata(institution_id, masks=("9001",)))
    assert {row["id"] for row in sync.items()} == {first["id"], second["id"]}
    assert stored_institution_id(second["id"]) == institution_id
    assert spy.removed == [] and sync.duplicates() == []


def test_null_masks_never_match(spy):
    first = sync.link(FIRST)
    with connect() as db:
        db.execute("UPDATE accounts SET mask=NULL WHERE item_id=?", (first["id"],))
    original = spy.accounts
    spy.accounts = lambda token: [{**row, "mask": None} for row in original(token)]
    assert sync.link(SECOND, metadata={
        "institution": {"institution_id": stored_institution_id(first["id"])},
        "accounts": [{"mask": None, "type": "depository", "subtype": "checking"}],
    })
    assert len(sync.items()) == 2 and spy.removed == []


def test_different_institution_same_mask_allowed(spy):
    first = sync.link(FIRST)
    other = sync.link("synthetic-other@synthcu")
    assert len(sync.items()) == 2 and spy.removed == []
    # Same display name and masks, but Plaid institution ids differ.
    assert other["institution"] == first["institution"] == "Synthetic Bank"
    assert stored_institution_id(other["id"]) != stored_institution_id(first["id"])
    third = sync.link(
        "synthetic-third@third", metadata=metadata("ins_other", "Other Bank")
    )
    assert len(sync.items()) == 3 and spy.removed == []
    with pytest.raises(sync.DuplicateLinkError) as error:
        sync.link("synthetic-fourth@synthcu")
    assert error.value.duplicate_of == other["id"]
    assert third["id"] not in {error.value.duplicate_of}


def test_legacy_item_without_institution_id_uses_name_and_backfills(spy):
    first = sync.link(FIRST)
    with connect() as db:
        db.execute(
            "UPDATE plaid_items SET institution_id=NULL WHERE id=?", (first["id"],)
        )
    # Different metadata id, same display name (any case) → same institution.
    with pytest.raises(sync.DuplicateLinkError):
        sync.link(SECOND, metadata=metadata("ins_new", name="SYNTHETIC bank"))
    assert SECOND not in spy.exchanged
    # The safety net also falls back to the name for the legacy row.
    with pytest.raises(sync.DuplicateLinkError):
        sync.link("synthetic-elsewhere@elsewhere")
    assert spy.removed == [access("synthetic-elsewhere@elsewhere")]
    assert stored_institution_id(first["id"]) is None
    assert sync.sync_all()["ok"]
    assert stored_institution_id(first["id"]) == FakePlaidClient().institution_id(
        access(FIRST)
    )
    # Once backfilled, the institution id decides, not the shared display name.
    assert sync.link("synthetic-elsewhere@elsewhere")
    assert len(sync.items()) == 2


def test_same_item_relink_still_upserts(spy):
    first = sync.link(FIRST)
    sync.link("synthetic-other@other")
    assert sync.link(FIRST) == first
    assert len(sync.items()) == 2 and spy.removed == []


def owned_rows(item_id):
    owned = "SELECT id FROM accounts WHERE item_id=?"
    txns = f"SELECT id FROM transactions WHERE account_id IN ({owned})"
    queries = {
        "accounts": "SELECT COUNT(*) FROM accounts WHERE item_id=?",
        "transactions": "SELECT COUNT(*) FROM transactions "
        f"WHERE account_id IN ({owned})",
        "recurring_streams": "SELECT COUNT(*) FROM recurring_streams "
        f"WHERE account_id IN ({owned})",
        "balance_snapshots": "SELECT COUNT(*) FROM balance_snapshots "
        f"WHERE account_id IN ({owned})",
        "alerts": f"SELECT COUNT(*) FROM alerts WHERE account_id IN ({owned})",
        "transaction_tags": "SELECT COUNT(*) FROM transaction_tags "
        f"WHERE transaction_id IN ({txns})",
        "transaction_splits": "SELECT COUNT(*) FROM transaction_splits "
        f"WHERE transaction_id IN ({txns})",
    }
    with connect() as db:
        return {
            table: db.execute(sql, (item_id,)).fetchone()[0]
            for table, sql in queries.items()
        }


def annotate(item_id):
    with connect() as db:
        account, txn = db.execute(
            "SELECT a.id, t.id FROM transactions t JOIN accounts a "
            "ON a.id=t.account_id WHERE a.item_id=? AND t.amount=2500",
            (item_id,),
        ).fetchone()
        db.execute(
            "INSERT INTO alerts (kind,key,account_id,title,detail) "
            "VALUES ('low_balance',?,?,'Synthetic','Synthetic')",
            (f"synthetic-{item_id}", account),
        )
    money.txn_change(txn, "tag", tags=["kept"])
    money.txn_change(txn, "split", parts=["Income=2499", "Other=1"])
    return account, txn


def test_remove_delete_local_deletes_only_that_item(spy, monkeypatch):
    first = sync.link(FIRST)
    second = link_unchecked(monkeypatch, SECOND)
    assert sync.sync_all()["ok"]
    assert len(sync.duplicates()) == 1
    account, txn = annotate(second["id"])
    annotate(first["id"])
    kept, doomed = owned_rows(first["id"]), owned_rows(second["id"])
    assert all(doomed.values()) and kept == doomed
    held = data.accounts_overview()["groups"]
    net = data.networth()[-1]["total"]

    result = invoke("plaid", "remove", second["id"], "--delete-local")
    assert result == {
        "removed": second["id"],
        "retained_transactions": False,
        "deleted": {**doomed, "goals_updated": 0},
    }
    assert spy.removed == [access(SECOND)]
    assert owned_rows(second["id"]) == dict.fromkeys(doomed, 0)
    assert owned_rows(first["id"]) == kept
    with connect() as db:
        for table, column, value in (
            ("accounts", "id", account),
            ("transactions", "id", txn),
            ("transaction_tags", "transaction_id", txn),
            ("transaction_splits", "transaction_id", txn),
            ("balance_snapshots", "account_id", account),
            ("recurring_streams", "account_id", account),
            ("alerts", "account_id", account),
        ):
            assert not db.execute(
                f"SELECT 1 FROM {table} WHERE {column}=?", (value,)
            ).fetchone()
    assert [row["id"] for row in sync.items()] == [first["id"]]
    assert sync.duplicates() == []
    groups = data.accounts_overview()["groups"]
    after = {group["key"]: group["total"] for group in groups}
    assert after == {group["key"]: group["total"] / 2 for group in held}
    assert data.networth()[-1]["total"] == net / 2


def test_remove_delete_local_keeps_rows_when_plaid_fails(spy):
    first = sync.link(FIRST)
    before = owned_rows(first["id"])

    def fail(token):
        raise plaid_client.PlaidError("Plaid item_remove failed; check settings")

    spy.remove_item = fail
    with TestClient(app) as client:
        response = client.post(
            f"/api/plaid/items/{first['id']}/remove", json={"delete_local": True}
        )
    assert response.status_code == 400
    assert owned_rows(first["id"]) == before and len(sync.items()) == 1


def test_remove_default_and_api_delete_local(spy):
    first = sync.link(FIRST)
    other = sync.link("synthetic-other@other")
    with TestClient(app) as client:
        default = client.post(f"/api/plaid/items/{first['id']}/remove")
        assert default.json() == {"removed": first["id"], "retained_transactions": True}
        with connect() as db:
            detached = db.execute(
                "SELECT COUNT(*) FROM accounts WHERE item_id IS NULL"
            ).fetchone()[0]
        assert detached == 2
        response = client.post(
            f"/api/plaid/items/{other['id']}/remove", json={"delete_local": True}
        )
        assert response.status_code == 200
        assert response.json()["deleted"]["accounts"] == 2
    assert sync.items() == []
    # Only the detached (default-removed) Item's accounts and history remain.
    assert count("accounts") == 2 and count("transactions") == 30


def test_duplicates_groups_and_keep_selection(spy, monkeypatch):
    assert sync.duplicates() == [] and invoke("plaid", "duplicates") == []
    first = sync.link(FIRST)
    second = link_unchecked(monkeypatch, SECOND)
    third = link_unchecked(monkeypatch, "synthetic-third@synthbank")
    lone = link_unchecked(monkeypatch, "synthetic-lone@lone")
    assert invoke("plaid", "duplicates") == sync.duplicates()
    with connect() as db:
        # Legacy rows: no institution ids, so the shared display name decides.
        db.execute("UPDATE plaid_items SET institution_id=NULL")
        # Equal transaction counts: the earliest link wins.
        db.execute(
            "UPDATE plaid_items SET created_at=CASE id WHEN ? THEN '2026-01-02' "
            "WHEN ? THEN '2026-01-01' ELSE '2026-01-03' END",
            (first["id"], second["id"]),
        )
    others = sorted([first["id"], third["id"], lone["id"]])
    assert sync.duplicates() == [
        {
            "institution": "Synthetic Bank",
            "keep": second["id"],
            "duplicates": others,
            "accounts": [
                {"name": "Synthetic Checking", "mask": "0001", "subtype": "checking"},
                {"name": "Synthetic Credit", "mask": "0002", "subtype": "credit card"},
            ],
        }
    ]
    # Most transactions wins over the earlier link (this sync also backfills).
    assert sync.sync_all(item_id=third["id"])["ok"]
    assert sync.duplicates()[0]["keep"] == third["id"]
    assert invoke("plaid", "duplicates") == sync.duplicates()
    with TestClient(app) as client:
        assert client.get("/api/plaid/duplicates").json() == sync.duplicates()
    # Backfilled institution ids split the unrelated institution out of the group.
    assert sync.sync_all()["ok"]
    groups = sync.duplicates()
    assert len(groups) == 1
    assert groups[0]["keep"] == second["id"]
    assert groups[0]["duplicates"] == sorted([first["id"], third["id"]])


def account_id(item_id, kind):
    with connect() as db:
        return db.execute(
            "SELECT id FROM accounts WHERE item_id=? AND type=?", (item_id, kind)
        ).fetchone()[0]


def goal(goal_id):
    return next(row for row in money.goals_list() if row["id"] == goal_id)


def duplicate_pair(monkeypatch):
    first = sync.link(FIRST)
    second = link_unchecked(monkeypatch, SECOND)
    assert sync.sync_all()["ok"]
    return first["id"], second["id"]


def test_delete_local_remaps_drops_and_archives_goals(spy, monkeypatch):
    kept, doomed = duplicate_pair(monkeypatch)
    kept_checking = account_id(kept, "depository")
    doomed_checking = account_id(doomed, "depository")
    doomed_credit = account_id(doomed, "credit")
    # The kept Item's credit card no longer matches, so that id cannot remap.
    with connect() as db:
        db.execute(
            "UPDATE accounts SET mask='7777' WHERE item_id=? AND type='credit'",
            (kept,),
        )
    remapped = money.goals_add("Remapped", 5000, [doomed_checking])["id"]
    dropped = money.goals_add("Dropped", 5000, [kept_checking, doomed_credit])["id"]
    emptied = money.goals_add("Emptied", 5000, [doomed_credit])["id"]
    untouched = money.goals_add("Untouched", 5000, [kept_checking])["id"]
    progress = goal(remapped)["progress"]
    assert progress == 2500

    result = invoke("plaid", "remove", doomed, "--delete-local")
    assert result["deleted"]["goals_updated"] == 3
    assert goal(remapped)["account_ids"] == [kept_checking]
    assert goal(remapped)["progress"] == progress
    assert goal(remapped)["archived_at"] is None
    updated = money.goals_update(remapped, name="Still editable")
    assert updated["name"] == "Still editable"
    assert updated["account_ids"] == [kept_checking]
    assert goal(dropped)["account_ids"] == [kept_checking]
    assert goal(dropped)["archived_at"] is None
    assert goal(emptied)["account_ids"] == []
    assert goal(emptied)["archived_at"]
    assert goal(untouched)["account_ids"] == [kept_checking]
    assert goal(untouched)["archived_at"] is None


def test_delete_local_without_goals_reports_zero(spy):
    first = sync.link(FIRST)
    result = sync.remove_item(first["id"], delete_local=True)
    assert result["deleted"]["goals_updated"] == 0


def test_default_remove_leaves_goals_alone(spy, monkeypatch):
    _, doomed = duplicate_pair(monkeypatch)
    goal_id = money.goals_add("Detached", 5000, [account_id(doomed, "depository")])[
        "id"
    ]
    before = goal(goal_id)
    assert sync.remove_item(doomed) == {
        "removed": doomed,
        "retained_transactions": True,
    }
    assert goal(goal_id) == before
    assert money.goals_update(goal_id, name="Still valid")["applied"]


def test_safety_net_cleanup_failure_still_refuses(spy):
    first = sync.link(FIRST)

    def fail(token):
        raise plaid_client.PlaidError("Plaid item_remove failed; check settings")

    spy.remove_item = fail
    with TestClient(app) as client:
        response = client.post("/api/plaid/exchange", json={"public_token": SECOND})
    assert response.status_code == 409
    body = response.json()
    assert body["cleanup_failed"] is True and body["duplicate_of"] == first["id"]
    assert "already linked" in body["error"]
    assert [row["id"] for row in sync.items()] == [first["id"]]
    assert invoke("plaid", "exchange", SECOND, success=False)["cleanup_failed"]
    # A clean refusal does not carry the flag.
    del spy.remove_item
    assert "cleanup_failed" not in invoke("plaid", "exchange", SECOND, success=False)
    assert len(spy.removed) == 1


@pytest.mark.parametrize("name", ["Unknown institution", "unknown INSTITUTION", ""])
def test_placeholder_names_never_identify_an_institution(spy, name):
    assert not sync._same_institution(None, name, None, name)
    assert not sync._same_institution("ins_1", name, None, name)
    assert sync._same_institution(None, "Synthetic Bank", "ins_1", "synthetic bank")
    first = sync.link(FIRST)
    with connect() as db:
        db.execute(
            "UPDATE plaid_items SET institution_id=NULL, institution=? WHERE id=?",
            (name, first["id"]),
        )
    spy.institution_name = lambda token: name
    spy.institution_id = lambda token: None
    # Same masks, but neither Item has a usable institution identity.
    second = sync.link(SECOND)
    assert {row["id"] for row in sync.items()} == {first["id"], second["id"]}
    assert spy.removed == [] and sync.duplicates() == []
