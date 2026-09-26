from __future__ import annotations

import hashlib
import json
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from .db import user_root


FORMAT = "halo-toefl-portable-save"
VERSION = 1


def _rows(store, table: str, where: str = "", params=()):
    query = f"SELECT * FROM {table}" + (f" WHERE {where}" if where else "")
    return [dict(row) for row in store.db.execute(query, params)]


def _safe_component(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
    return cleaned[:80] or "item"


def export_save(store, destination: str | Path) -> dict:
    destination = Path(destination)
    attempts = _rows(store, "attempts")
    attempt_ids = {row["id"] for row in attempts}
    test_ids = {row["test_id"] for row in attempts}

    data = {
        "format": FORMAT,
        "version": VERSION,
        "exported_at": datetime.now().astimezone().isoformat(),
        "tests": [], "sections": [], "questions": [], "explanations": [],
        "attempts": attempts, "section_timers": [], "question_timers": [],
        "answers": [], "writing_responses": [], "speaking_recordings": [],
    }
    for test_id in sorted(test_ids):
        test = store.db.execute("SELECT * FROM tests WHERE id=?", (test_id,)).fetchone()
        if test:
            data["tests"].append(dict(test))
            data["sections"].extend(_rows(store, "sections", "test_id=?", (test_id,)))
            data["questions"].extend(_rows(store, "questions", "test_id=?", (test_id,)))
            data["explanations"].extend(_rows(store, "question_explanations", "test_id=?", (test_id,)))
    for attempt_id in sorted(attempt_ids):
        data["section_timers"].extend(_rows(store, "attempt_section_timers", "attempt_id=?", (attempt_id,)))
        data["question_timers"].extend(_rows(store, "attempt_question_timers", "attempt_id=?", (attempt_id,)))
        data["answers"].extend(_rows(store, "answers", "attempt_id=?", (attempt_id,)))
        data["writing_responses"].extend(_rows(store, "writing_responses", "attempt_id=?", (attempt_id,)))

    recording_files = []
    recording_keys = set()
    for row in (record for attempt_id in sorted(attempt_ids) for record in _rows(store, "speaking_recordings", "attempt_id=?", (attempt_id,))):
        recording_keys.add((row["attempt_id"], row["question_id"]))
        source = Path(row.get("path", ""))
        archived = dict(row)
        archived["archive_path"] = ""
        archived["sha256"] = ""
        if source.is_file():
            suffix = source.suffix.lower() or ".wav"
            token = hashlib.sha256(f"{row['attempt_id']}:{row['question_id']}".encode()).hexdigest()[:16]
            archive_path = f"recordings/{_safe_component(row['attempt_id'])}/{token}{suffix}"
            archived["archive_path"] = archive_path
            archived["sha256"] = hashlib.sha256(source.read_bytes()).hexdigest()
            recording_files.append((source, archive_path))
        archived.pop("path", None)
        data["speaking_recordings"].append(archived)
    for answer in data["answers"]:
        if (answer["attempt_id"], answer["question_id"]) in recording_keys:
            answer["answer"] = "[recorded speaking response]"

    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    manifest = {
        "format": FORMAT,
        "version": VERSION,
        "created_at": data["exported_at"],
        "progress_sha256": hashlib.sha256(payload).hexdigest(),
        "attempt_count": len(attempts),
        "answer_count": len(data["answers"]),
        "recording_count": len(recording_files),
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        archive.writestr("progress.json", payload)
        for source, archive_path in recording_files:
            archive.write(source, archive_path)
    return manifest


def _valid_archive_path(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts and path.parts[:1] == ("recordings",)


def import_save(store, source: str | Path) -> dict:
    source = Path(source)
    if not zipfile.is_zipfile(source):
        raise ValueError("This is not a valid HALO TOEFL save file.")
    with zipfile.ZipFile(source, "r") as archive:
        manifest = json.loads(archive.read("manifest.json"))
        payload = archive.read("progress.json")
        if manifest.get("format") != FORMAT or int(manifest.get("version", 0)) != VERSION:
            raise ValueError("Unsupported HALO TOEFL save format.")
        if hashlib.sha256(payload).hexdigest() != manifest.get("progress_sha256"):
            raise ValueError("The save file failed its integrity check.")
        data = json.loads(payload.decode("utf-8"))

        db = store.db
        for row in data.get("tests", []):
            if not db.execute("SELECT 1 FROM tests WHERE id=?", (row["id"],)).fetchone():
                db.execute("INSERT INTO tests(id,name,provider,category,status,source_pdf,audio_notice) VALUES(?,?,?,?,?,?,?)",
                           (row["id"], row["name"], row.get("provider", "Imported save"), "IMPORTED_ARCHIVE",
                            "PARTIAL", row.get("source_pdf", ""), row.get("audio_notice", "")))
        for row in data.get("sections", []):
            db.execute("INSERT OR IGNORE INTO sections(test_id,name,question_count) VALUES(?,?,?)",
                       (row["test_id"], row["name"], row["question_count"]))
        for row in data.get("questions", []):
            db.execute("""INSERT OR IGNORE INTO questions
                (test_id,id,section,module,number,type,stimulus,prompt,choices,correct,transcript,audio,duration)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["test_id"], row["id"], row["section"], row["module"], row["number"], row["type"],
                 row.get("stimulus", ""), row.get("prompt", ""), row.get("choices", "{}"), row.get("correct", ""),
                 row.get("transcript", ""), row.get("audio", ""), row.get("duration", 0)))
        for row in data.get("explanations", []):
            db.execute("INSERT OR IGNORE INTO question_explanations(test_id,question_id,zh,en) VALUES(?,?,?,?)",
                       (row["test_id"], row["question_id"], row.get("zh", ""), row.get("en", "")))

        imported_ids = set()
        skipped = 0
        for row in data.get("attempts", []):
            if db.execute("SELECT 1 FROM attempts WHERE id=?", (row["id"],)).fetchone():
                skipped += 1
                continue
            if not db.execute("SELECT 1 FROM tests WHERE id=?", (row["test_id"],)).fetchone():
                skipped += 1
                continue
            db.execute("""INSERT INTO attempts
                (id,test_id,mode,sections,started,ended,status,index_position,elapsed_seconds,countdown_enabled)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (row["id"], row["test_id"], row["mode"], row["sections"], row["started"], row.get("ended"),
                 row["status"], row.get("index_position", 0), row.get("elapsed_seconds", 0), row.get("countdown_enabled", 1)))
            imported_ids.add(row["id"])

        related = {
            "section_timers": ("attempt_section_timers", ("attempt_id", "section", "remaining_seconds", "updated")),
            "question_timers": ("attempt_question_timers", ("attempt_id", "question_id", "remaining_seconds", "updated")),
            "answers": ("answers", ("attempt_id", "question_id", "answer", "updated")),
            "writing_responses": ("writing_responses", ("attempt_id", "question_id", "response", "updated")),
        }
        for key, (table, columns) in related.items():
            marks = ",".join("?" for _ in columns)
            names = ",".join(columns)
            for row in data.get(key, []):
                if row.get("attempt_id") in imported_ids:
                    db.execute(f"INSERT OR IGNORE INTO {table}({names}) VALUES({marks})", tuple(row.get(c) for c in columns))

        recordings_imported = 0
        recordings_root = (user_root() / "recordings" / "imported").resolve()
        for row in data.get("speaking_recordings", []):
            if row.get("attempt_id") not in imported_ids:
                continue
            archive_path = row.get("archive_path", "")
            if not archive_path or not _valid_archive_path(archive_path) or archive_path not in archive.namelist():
                continue
            content = archive.read(archive_path)
            if row.get("sha256") and hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError("A recording in the save file failed its integrity check.")
            suffix = Path(archive_path).suffix or ".wav"
            target_dir = (recordings_root / _safe_component(row["attempt_id"])).resolve()
            if recordings_root not in target_dir.parents:
                raise ValueError("Unsafe recording path in save file.")
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / f"{_safe_component(row['question_id'])}{suffix}"
            target.write_bytes(content)
            db.execute("INSERT OR IGNORE INTO speaking_recordings(attempt_id,question_id,path,duration,created) VALUES(?,?,?,?,?)",
                       (row["attempt_id"], row["question_id"], str(target), row.get("duration", 0), row.get("created", "")))
            db.execute("UPDATE answers SET answer=? WHERE attempt_id=? AND question_id=?",
                       (str(target), row["attempt_id"], row["question_id"]))
            recordings_imported += 1
        db.commit()
    return {"imported": len(imported_ids), "skipped": skipped, "recordings": recordings_imported}


def clear_local_records(store) -> None:
    db = store.db
    db.executescript("""
        DELETE FROM speaking_recordings;
        DELETE FROM writing_responses;
        DELETE FROM answers;
        DELETE FROM attempt_question_timers;
        DELETE FROM attempt_section_timers;
        DELETE FROM attempts;
        DELETE FROM daily_activity;
        DELETE FROM question_explanations WHERE test_id IN (SELECT id FROM tests WHERE category='IMPORTED_ARCHIVE');
        DELETE FROM questions WHERE test_id IN (SELECT id FROM tests WHERE category='IMPORTED_ARCHIVE');
        DELETE FROM sections WHERE test_id IN (SELECT id FROM tests WHERE category='IMPORTED_ARCHIVE');
        DELETE FROM tests WHERE category='IMPORTED_ARCHIVE';
    """)
    db.commit()
    root = user_root().resolve()
    recordings = (root / "recordings").resolve()
    if root not in recordings.parents:
        raise RuntimeError("Refusing to clear a recordings folder outside the application data directory.")
    if recordings.exists():
        shutil.rmtree(recordings)
