"""SQLite database manager with schema migrations and CRUD helpers."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS emulators (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ldplayer_index INTEGER UNIQUE NOT NULL,
    name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'CREATED',
    adb_serial TEXT,
    bridge_verified INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    first_name TEXT,
    last_name TEXT,
    email TEXT,
    phone TEXT,
    emulator_id INTEGER,
    profile_url TEXT,
    status TEXT NOT NULL DEFAULT 'PENDING',
    iteration INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY (emulator_id) REFERENCES emulators(id)
);

CREATE TABLE IF NOT EXISTS media_files (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT NOT NULL,
    filepath TEXT NOT NULL,
    file_size INTEGER,
    sha256_hash TEXT NOT NULL UNIQUE,
    assigned_account_id INTEGER,
    status TEXT NOT NULL DEFAULT 'AVAILABLE',
    created_at TEXT NOT NULL,
    FOREIGN KEY (assigned_account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS upload_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    media_file_id INTEGER NOT NULL,
    emulator_id INTEGER,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TEXT,
    completed_at TEXT,
    error_message TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id),
    FOREIGN KEY (media_file_id) REFERENCES media_files(id),
    FOREIGN KEY (emulator_id) REFERENCES emulators(id)
);

CREATE TABLE IF NOT EXISTS verification_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    method TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'WAITING',
    code TEXT,
    requested_at TEXT NOT NULL,
    received_at TEXT,
    error_message TEXT,
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);

CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    emulator_id INTEGER,
    account_id INTEGER,
    stage TEXT,
    message TEXT NOT NULL,
    screenshot_path TEXT,
    recovery_info TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_name TEXT NOT NULL,
    emulator_id INTEGER,
    account_id INTEGER,
    status TEXT NOT NULL DEFAULT 'PENDING',
    started_at TEXT,
    completed_at TEXT,
    result_data TEXT,
    FOREIGN KEY (emulator_id) REFERENCES emulators(id),
    FOREIGN KEY (account_id) REFERENCES accounts(id)
);
"""


class DatabaseManager:
    def __init__(self, db_path: str = "fleet_manager.db"):
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    def initialize(self):
        conn = self.connect()
        conn.executescript(SCHEMA_SQL)
        row = conn.execute("SELECT version FROM schema_version").fetchone()
        if row is None:
            conn.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    # --- Emulators ---

    def add_emulator(self, ldplayer_index: int, name: str) -> int:
        conn = self.connect()
        now = self._now()
        cur = conn.execute(
            "INSERT INTO emulators (ldplayer_index, name, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (ldplayer_index, name, now, now),
        )
        conn.commit()
        return cur.lastrowid

    def update_emulator_status(self, emulator_id: int, status: str, adb_serial: str | None = None):
        conn = self.connect()
        if adb_serial is not None:
            conn.execute(
                "UPDATE emulators SET status=?, adb_serial=?, updated_at=? WHERE id=?",
                (status, adb_serial, self._now(), emulator_id),
            )
        else:
            conn.execute(
                "UPDATE emulators SET status=?, updated_at=? WHERE id=?",
                (status, self._now(), emulator_id),
            )
        conn.commit()

    def set_bridge_verified(self, emulator_id: int, verified: bool):
        conn = self.connect()
        conn.execute(
            "UPDATE emulators SET bridge_verified=?, updated_at=? WHERE id=?",
            (int(verified), self._now(), emulator_id),
        )
        conn.commit()

    def get_emulator(self, emulator_id: int) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM emulators WHERE id=?", (emulator_id,)
        ).fetchone()

    def get_emulators_by_status(self, status: str) -> list[sqlite3.Row]:
        return self.connect().execute(
            "SELECT * FROM emulators WHERE status=? ORDER BY id", (status,)
        ).fetchall()

    def get_all_emulators(self) -> list[sqlite3.Row]:
        return self.connect().execute("SELECT * FROM emulators ORDER BY id").fetchall()

    # --- Accounts ---

    def add_account(self, external_id: str, first_name: str, last_name: str,
                    email: str | None = None, phone: str | None = None,
                    emulator_id: int | None = None) -> int:
        conn = self.connect()
        now = self._now()
        cur = conn.execute(
            """INSERT INTO accounts
               (external_id, first_name, last_name, email, phone, emulator_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (external_id, first_name, last_name, email, phone, emulator_id, now, now),
        )
        conn.commit()
        return cur.lastrowid

    def update_account_status(self, account_id: int, status: str):
        conn = self.connect()
        conn.execute(
            "UPDATE accounts SET status=?, updated_at=? WHERE id=?",
            (status, self._now(), account_id),
        )
        conn.commit()

    def update_account_profile_url(self, account_id: int, profile_url: str):
        conn = self.connect()
        conn.execute(
            "UPDATE accounts SET profile_url=?, updated_at=? WHERE id=?",
            (profile_url, self._now(), account_id),
        )
        conn.commit()

    def get_account(self, account_id: int) -> sqlite3.Row | None:
        return self.connect().execute(
            "SELECT * FROM accounts WHERE id=?", (account_id,)
        ).fetchone()

    def get_accounts_by_status(self, status: str) -> list[sqlite3.Row]:
        return self.connect().execute(
            "SELECT * FROM accounts WHERE status=? ORDER BY id", (status,)
        ).fetchall()

    def get_accounts_for_emulator(self, emulator_id: int) -> list[sqlite3.Row]:
        return self.connect().execute(
            "SELECT * FROM accounts WHERE emulator_id=? ORDER BY id", (emulator_id,)
        ).fetchall()

    # --- Media Files ---

    def add_media_file(self, filename: str, filepath: str, file_size: int, sha256_hash: str) -> int:
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO media_files (filename, filepath, file_size, sha256_hash, created_at) VALUES (?, ?, ?, ?, ?)",
            (filename, filepath, file_size, sha256_hash, self._now()),
        )
        conn.commit()
        return cur.lastrowid

    def assign_media_to_account(self, media_id: int, account_id: int):
        conn = self.connect()
        conn.execute(
            "UPDATE media_files SET assigned_account_id=?, status='ASSIGNED' WHERE id=?",
            (account_id, media_id),
        )
        conn.commit()

    def get_available_media(self) -> list[sqlite3.Row]:
        return self.connect().execute(
            "SELECT * FROM media_files WHERE status='AVAILABLE' ORDER BY id"
        ).fetchall()

    def get_media_for_account(self, account_id: int) -> list[sqlite3.Row]:
        return self.connect().execute(
            "SELECT * FROM media_files WHERE assigned_account_id=? ORDER BY id",
            (account_id,),
        ).fetchall()

    def is_hash_used(self, sha256_hash: str) -> bool:
        row = self.connect().execute(
            "SELECT 1 FROM media_files WHERE sha256_hash=? AND status IN ('ASSIGNED','PUBLISHED')",
            (sha256_hash,),
        ).fetchone()
        return row is not None

    def update_media_status(self, media_id: int, status: str):
        conn = self.connect()
        conn.execute("UPDATE media_files SET status=? WHERE id=?", (status, media_id))
        conn.commit()

    # --- Upload History ---

    def add_upload(self, account_id: int, media_file_id: int, emulator_id: int | None = None) -> int:
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO upload_history (account_id, media_file_id, emulator_id, started_at) VALUES (?, ?, ?, ?)",
            (account_id, media_file_id, emulator_id, self._now()),
        )
        conn.commit()
        return cur.lastrowid

    def complete_upload(self, upload_id: int, status: str, error_message: str | None = None):
        conn = self.connect()
        conn.execute(
            "UPDATE upload_history SET status=?, completed_at=?, error_message=? WHERE id=?",
            (status, self._now(), error_message, upload_id),
        )
        conn.commit()

    # --- Verification Log ---

    def add_verification(self, account_id: int, method: str) -> int:
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO verification_log (account_id, method, requested_at) VALUES (?, ?, ?)",
            (account_id, method, self._now()),
        )
        conn.commit()
        return cur.lastrowid

    def update_verification(self, verification_id: int, state: str, code: str | None = None,
                            error_message: str | None = None):
        conn = self.connect()
        received = self._now() if state == "RECEIVED" else None
        conn.execute(
            "UPDATE verification_log SET state=?, code=?, received_at=?, error_message=? WHERE id=?",
            (state, code, received, error_message, verification_id),
        )
        conn.commit()

    # --- Workflow Runs ---

    def start_workflow_run(self, workflow_name: str, emulator_id: int | None = None,
                           account_id: int | None = None) -> int:
        conn = self.connect()
        cur = conn.execute(
            "INSERT INTO workflow_runs (workflow_name, emulator_id, account_id, status, started_at) VALUES (?, ?, ?, 'RUNNING', ?)",
            (workflow_name, emulator_id, account_id, self._now()),
        )
        conn.commit()
        return cur.lastrowid

    def complete_workflow_run(self, run_id: int, status: str, result_data: str | None = None):
        conn = self.connect()
        conn.execute(
            "UPDATE workflow_runs SET status=?, completed_at=?, result_data=? WHERE id=?",
            (status, self._now(), result_data, run_id),
        )
        conn.commit()

    # --- Stats ---

    def get_dashboard_stats(self) -> dict:
        conn = self.connect()
        emu_total = conn.execute("SELECT COUNT(*) FROM emulators").fetchone()[0]
        emu_ready = conn.execute("SELECT COUNT(*) FROM emulators WHERE status='READY'").fetchone()[0]
        emu_active = conn.execute("SELECT COUNT(*) FROM emulators WHERE status='RUNNING'").fetchone()[0]
        acc_total = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        acc_success = conn.execute("SELECT COUNT(*) FROM accounts WHERE status='SUCCESS'").fetchone()[0]
        acc_failed = conn.execute("SELECT COUNT(*) FROM accounts WHERE status='FAILED'").fetchone()[0]
        media_published = conn.execute(
            "SELECT COUNT(*) FROM upload_history WHERE status='SUCCESS'"
        ).fetchone()[0]
        error_count = conn.execute("SELECT COUNT(*) FROM error_log").fetchone()[0]
        return {
            "emulators_total": emu_total,
            "emulators_ready": emu_ready,
            "emulators_active": emu_active,
            "accounts_total": acc_total,
            "accounts_success": acc_success,
            "accounts_failed": acc_failed,
            "media_published": media_published,
            "error_count": error_count,
        }

    # --- Export ---

    def export_errors(self, limit: int = 100) -> list[dict]:
        rows = self.connect().execute(
            "SELECT * FROM error_log ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
