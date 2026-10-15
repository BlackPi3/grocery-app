"""The developer's copies of people's uploads last 30 days (owner, 2026-10-15)."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import dev_inbox  # noqa: E402


def test_copies_older_than_30_days_are_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_inbox, "INBOX", tmp_path)
    now = time.time()
    for name, days in (("old.jpg", 31), ("old.json", 31), ("new.jpg", 2)):
        (tmp_path / name).write_text("x")
        os.utime(tmp_path / name, (now - days * 86400,) * 2)

    assert dev_inbox.forget_old(now) == 2
    assert sorted(f.name for f in tmp_path.iterdir()) == ["new.jpg"]


def test_no_inbox_yet_is_nothing_to_delete(tmp_path, monkeypatch):
    monkeypatch.setattr(dev_inbox, "INBOX", tmp_path / "missing")
    assert dev_inbox.forget_old() == 0
