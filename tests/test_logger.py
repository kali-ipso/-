"""Tests for Logger."""

import os
import tempfile
from src.database import DatabaseManager
from src.logger import Logger


def test_logger_error_writes_to_db():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(db_path)
    db.initialize()

    with tempfile.TemporaryDirectory() as log_dir:
        logger = Logger(db_path, log_dir=log_dir)
        row_id = logger.error(
            "Test error",
            emulator_id=1,
            stage="boot",
            recovery_info="retry",
        )
        assert row_id is not None

        row = db.connect().execute(
            "SELECT * FROM error_log WHERE id=?", (row_id,)
        ).fetchone()
        assert row["message"] == "Test error"
        assert row["stage"] == "boot"
        assert row["emulator_id"] == 1

    db.close()
    os.unlink(db_path)


def test_logger_info_no_crash():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with tempfile.TemporaryDirectory() as log_dir:
        logger = Logger(db_path, log_dir=log_dir)
        logger.info("hello", emulator_id=1)
        logger.warning("warn")
        logger.debug("debug")
        assert (os.path.join(log_dir, "fleet_manager.log"))
    os.unlink(db_path)


def test_logger_level_setter():
    import logging
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    with tempfile.TemporaryDirectory() as log_dir:
        logger = Logger(db_path, log_dir=log_dir)
        logger.level = logging.DEBUG
        assert logger.level == logging.DEBUG
    os.unlink(db_path)
