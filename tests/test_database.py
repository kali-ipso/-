"""Tests for DatabaseManager."""

import os
import tempfile
import pytest
from src.database import DatabaseManager


@pytest.fixture
def db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    mgr = DatabaseManager(path)
    mgr.initialize()
    yield mgr
    mgr.close()
    os.unlink(path)


def test_initialize_creates_tables(db):
    tables = [r[0] for r in db.connect().execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()]
    assert "emulators" in tables
    assert "accounts" in tables
    assert "media_files" in tables
    assert "error_log" in tables
    assert "workflow_runs" in tables


def test_emulator_crud(db):
    eid = db.add_emulator(0, "emu-0")
    assert eid == 1
    emu = db.get_emulator(eid)
    assert emu["name"] == "emu-0"
    assert emu["status"] == "CREATED"

    db.update_emulator_status(eid, "READY", adb_serial="127.0.0.1:5555")
    emu = db.get_emulator(eid)
    assert emu["status"] == "READY"
    assert emu["adb_serial"] == "127.0.0.1:5555"

    ready = db.get_emulators_by_status("READY")
    assert len(ready) == 1


def test_bridge_verified(db):
    eid = db.add_emulator(1, "emu-1")
    db.set_bridge_verified(eid, True)
    assert db.get_emulator(eid)["bridge_verified"] == 1


def test_account_crud(db):
    eid = db.add_emulator(0, "emu-0")
    aid = db.add_account("EXT-1", "Mia", "Johnson", email="mia@test.com", emulator_id=eid)
    assert aid == 1
    acc = db.get_account(aid)
    assert acc["first_name"] == "Mia"
    assert acc["status"] == "PENDING"

    db.update_account_status(aid, "SUCCESS")
    assert db.get_account(aid)["status"] == "SUCCESS"

    db.update_account_profile_url(aid, "https://example.com/mia")
    assert db.get_account(aid)["profile_url"] == "https://example.com/mia"

    accs = db.get_accounts_for_emulator(eid)
    assert len(accs) == 1


def test_media_dedup(db):
    mid = db.add_media_file("vid.mp4", "/videos/vid.mp4", 1024, "abc123")
    assert not db.is_hash_used("abc123")  # AVAILABLE doesn't count

    aid = db.add_account("EXT-1", "A", "B")
    db.assign_media_to_account(mid, aid)
    assert db.is_hash_used("abc123")

    available = db.get_available_media()
    assert len(available) == 0

    assigned = db.get_media_for_account(aid)
    assert len(assigned) == 1


def test_upload_history(db):
    aid = db.add_account("EXT-1", "A", "B")
    mid = db.add_media_file("v.mp4", "/v.mp4", 512, "hash1")
    uid = db.add_upload(aid, mid)
    db.complete_upload(uid, "SUCCESS")

    row = db.connect().execute("SELECT * FROM upload_history WHERE id=?", (uid,)).fetchone()
    assert row["status"] == "SUCCESS"
    assert row["completed_at"] is not None


def test_verification_log(db):
    aid = db.add_account("EXT-1", "A", "B")
    vid = db.add_verification(aid, "EMAIL")
    db.update_verification(vid, "RECEIVED", code="123456")

    row = db.connect().execute("SELECT * FROM verification_log WHERE id=?", (vid,)).fetchone()
    assert row["code"] == "123456"
    assert row["received_at"] is not None


def test_workflow_runs(db):
    rid = db.start_workflow_run("onboarding", account_id=None)
    db.complete_workflow_run(rid, "SUCCESS", result_data='{"ok": true}')

    row = db.connect().execute("SELECT * FROM workflow_runs WHERE id=?", (rid,)).fetchone()
    assert row["status"] == "SUCCESS"


def test_dashboard_stats(db):
    db.add_emulator(0, "e0")
    db.add_emulator(1, "e1")
    db.update_emulator_status(1, "READY")
    db.add_account("X1", "A", "B")

    stats = db.get_dashboard_stats()
    assert stats["emulators_total"] == 2
    assert stats["emulators_ready"] == 1
    assert stats["accounts_total"] == 1


def test_duplicate_external_id_rejected(db):
    db.add_account("EXT-1", "A", "B")
    with pytest.raises(Exception):
        db.add_account("EXT-1", "C", "D")


def test_duplicate_hash_rejected(db):
    db.add_media_file("a.mp4", "/a.mp4", 100, "samehash")
    with pytest.raises(Exception):
        db.add_media_file("b.mp4", "/b.mp4", 200, "samehash")
