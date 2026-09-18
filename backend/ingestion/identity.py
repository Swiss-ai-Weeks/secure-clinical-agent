"""Durable, owner-restricted source identity and provenance registry."""

import os
from pathlib import Path
import sqlite3
import uuid

from worker import BatchError, canonical

NAMESPACE = "patient360-synthea-demo-v1"


class Registry:
    def __init__(self, path):
        self.path = Path(path)
        if not self.path.is_file() or self.path.is_symlink():
            raise BatchError("registry_missing_restore_required")
        if self.path.stat().st_mode & 0o077 or self.path.parent.stat().st_mode & 0o077:
            raise BatchError("registry_permissions_too_broad")
        try:
            self.db = sqlite3.connect(f"file:{self.path}?mode=rw", uri=True)
            if self.db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BatchError("registry_corrupt_restore_required")
            metadata = dict(self.db.execute("SELECT key, value FROM metadata"))
            if metadata.get("namespace") != NAMESPACE or metadata.get("version") != "1":
                raise BatchError("registry_contract_mismatch")
            self.identity = metadata["identity"]
            # Additive local provenance upgrade; existing mappings stay untouched.
            self.db.execute("""CREATE TABLE IF NOT EXISTS resource_links (
                batch TEXT NOT NULL, source TEXT NOT NULL, relation TEXT NOT NULL,
                target TEXT NOT NULL, PRIMARY KEY (batch, source, relation, target))""")
            self.db.commit()
        except (sqlite3.Error, KeyError) as error:
            raise BatchError("registry_corrupt_restore_required") from error

    @classmethod
    def initialize(cls, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if path.parent.stat().st_mode & 0o077:
            raise BatchError("registry_permissions_too_broad")
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE identities (
                    source TEXT PRIMARY KEY, opaque TEXT NOT NULL UNIQUE,
                    patient TEXT NOT NULL, cite TEXT NOT NULL UNIQUE);
                CREATE TABLE provenance (
                    batch TEXT NOT NULL, source TEXT NOT NULL, digest TEXT NOT NULL,
                    detail TEXT NOT NULL, PRIMARY KEY (batch, source));
            """)
            db.executemany("INSERT INTO metadata VALUES (?,?)", [
                ("version", "1"), ("namespace", NAMESPACE), ("identity", uuid.uuid4().hex)])
        return cls(path)

    def allocate(self, source, patient):
        old = self.db.execute(
            "SELECT opaque, patient, cite FROM identities WHERE source=?", (source,)).fetchone()
        if old:
            if old[1] != patient:
                raise BatchError("source_patient_changed")
            return old[0], old[2]
        kind = source.split("/", 1)[0]
        opaque = "p_" + uuid.uuid4().hex if kind == "Patient" else str(uuid.uuid4())
        prefix = {"Patient": "pat", "Encounter": "enc", "Condition": "cond",
                  "Observation": "obs", "DocumentReference": "note"}[kind]
        cite = prefix + "_" + uuid.uuid4().hex[:16]
        self.db.execute("INSERT INTO identities VALUES (?,?,?,?)", (source, opaque, patient, cite))
        return opaque, cite

    def record(self, batch, source, digest, detail):
        serialized = canonical(detail).decode()
        old = self.db.execute("SELECT digest, detail FROM provenance WHERE batch=? AND source=?",
                              (batch, source)).fetchone()
        if old and old != (digest, serialized):
            raise BatchError("immutable_provenance_changed")
        self.db.execute("INSERT OR IGNORE INTO provenance VALUES (?,?,?,?)",
                        (batch, source, digest, serialized))

    def link(self, batch, source, relation, target):
        self.db.execute("INSERT OR IGNORE INTO resource_links VALUES (?,?,?,?)",
                        (batch, source, relation, target))

    def backup(self, destination):
        destination = Path(destination)
        fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        with sqlite3.connect(destination) as target:
            self.db.backup(target)

    def close(self):
        self.db.close()
