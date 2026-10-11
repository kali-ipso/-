"""Structured logging with screenshot capture on errors."""

import logging
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


class Logger:
    def __init__(self, db_path: str, log_dir: str = "logs", level: int = logging.INFO):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.screenshot_dir = self.log_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._level = level

        self._file_logger = logging.getLogger("fleet_manager")
        self._file_logger.setLevel(level)
        if not self._file_logger.handlers:
            fh = logging.FileHandler(self.log_dir / "fleet_manager.log", encoding="utf-8")
            fh.setFormatter(logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
            ))
            self._file_logger.addHandler(fh)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
            self._file_logger.addHandler(ch)

    @property
    def level(self) -> int:
        return self._level

    @level.setter
    def level(self, value: int):
        self._level = value
        self._file_logger.setLevel(value)

    def info(self, message: str, **ctx):
        self._file_logger.info(self._fmt(message, ctx))

    def warning(self, message: str, **ctx):
        self._file_logger.warning(self._fmt(message, ctx))

    def debug(self, message: str, **ctx):
        self._file_logger.debug(self._fmt(message, ctx))

    def error(
        self,
        message: str,
        emulator_id: int | None = None,
        account_id: int | None = None,
        stage: str | None = None,
        recovery_info: str | None = None,
        take_screenshot: bool = False,
        adb_serial: str | None = None,
    ) -> int | None:
        """Log an error to file and DB. Returns the error_log row id."""
        self._file_logger.error(
            self._fmt(message, {"emulator_id": emulator_id, "stage": stage})
        )
        screenshot_path = None
        if take_screenshot and adb_serial:
            screenshot_path = self._capture_screenshot(adb_serial, emulator_id)

        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.execute(
                """INSERT INTO error_log
                   (emulator_id, account_id, stage, message, screenshot_path, recovery_info, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    emulator_id,
                    account_id,
                    stage,
                    message,
                    screenshot_path,
                    recovery_info,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()
            row_id = cur.lastrowid
            conn.close()
            return row_id
        except sqlite3.Error as e:
            self._file_logger.error(f"Failed to write error to DB: {e}")
            return None

    def _capture_screenshot(self, adb_serial: str, emulator_id: int | None) -> str | None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        emu_tag = emulator_id if emulator_id is not None else "unknown"
        filename = f"err_{emu_tag}_{ts}.png"
        local_path = str(self.screenshot_dir / filename)
        remote_path = "/sdcard/screenshot_tmp.png"
        try:
            subprocess.run(
                ["adb", "-s", adb_serial, "shell", "screencap", "-p", remote_path],
                capture_output=True, timeout=10,
            )
            subprocess.run(
                ["adb", "-s", adb_serial, "pull", remote_path, local_path],
                capture_output=True, timeout=10,
            )
            return local_path
        except Exception as e:
            self._file_logger.warning(f"Screenshot capture failed: {e}")
            return None

    @staticmethod
    def _fmt(message: str, ctx: dict) -> str:
        parts = [message]
        for k, v in ctx.items():
            if v is not None:
                parts.append(f"{k}={v}")
        return " | ".join(parts)
