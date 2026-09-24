"""Append-only, hash-chained audit receipts for the demo control plane."""

import hashlib
import json
import time
import uuid
from pathlib import Path


class ReceiptLog:
    def __init__(self, path: Path):
        self.path = path

    def append(self, event: str, **fields: object) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        entry = {"receipt_id": f"rcpt_{uuid.uuid4().hex[:12]}", "event": event,
                 "ts": time.time(), "prev_hash": self._head_hash(), **fields}
        entry["event_hash"] = self._hash(entry)
        with self.path.open("a", encoding="utf-8") as audit_file:
            audit_file.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> dict:
        expected = "GENESIS"
        checked = 0
        for event in self.read():
            event_hash = event.pop("event_hash", None)
            if event.get("prev_hash") != expected or event_hash != self._hash(event):
                return {"valid": False, "events_checked": checked, "head_hash": expected}
            expected, checked = event_hash, checked + 1
        return {"valid": True, "events_checked": checked, "head_hash": expected}

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text(encoding="utf-8").splitlines() if line]

    def _head_hash(self) -> str:
        events = self.read()
        return events[-1]["event_hash"] if events else "GENESIS"

    @staticmethod
    def _hash(entry: dict) -> str:
        return hashlib.sha256(json.dumps(entry, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
