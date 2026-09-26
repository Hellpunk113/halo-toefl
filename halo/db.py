from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def bundle_root():
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))


def user_root():
    override = os.environ.get("HALO_VOCAB_DATA")
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    root = Path(override) if override else base / "HALO TOEFL"
    legacy = base / "HaloVocab"
    if not override and not root.exists() and legacy.exists():
        shutil.copytree(legacy, root, dirs_exist_ok=True)
    root.mkdir(parents=True, exist_ok=True)
    return root


class Store:
    def __init__(self):
        self.path = user_root() / "halo-vocab.sqlite3"
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS sources (source_id TEXT, source_url TEXT, status TEXT, metadata TEXT, PRIMARY KEY(source_id,source_url));
        CREATE TABLE IF NOT EXISTS tests (id TEXT PRIMARY KEY, name TEXT, provider TEXT, category TEXT, status TEXT, source_pdf TEXT, audio_notice TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS sections (test_id TEXT, name TEXT, question_count INTEGER, PRIMARY KEY(test_id,name));
        CREATE TABLE IF NOT EXISTS questions (test_id TEXT, id TEXT, section TEXT, module INTEGER, number INTEGER, type TEXT, stimulus TEXT, prompt TEXT, choices TEXT, correct TEXT, transcript TEXT, audio TEXT, duration INTEGER, PRIMARY KEY(test_id,id));
        CREATE TABLE IF NOT EXISTS question_explanations (test_id TEXT, question_id TEXT, zh TEXT, en TEXT, PRIMARY KEY(test_id,question_id));
        CREATE TABLE IF NOT EXISTS audio_assets (test_id TEXT, path TEXT, sha256 TEXT, PRIMARY KEY(test_id,path));
        CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, test_id TEXT, mode TEXT, sections TEXT, started TEXT, ended TEXT, status TEXT, index_position INTEGER DEFAULT 0, elapsed_seconds INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS attempt_section_timers (attempt_id TEXT, section TEXT, remaining_seconds INTEGER, updated TEXT, PRIMARY KEY(attempt_id,section));
        CREATE TABLE IF NOT EXISTS attempt_question_timers (attempt_id TEXT, question_id TEXT, remaining_seconds INTEGER, updated TEXT, PRIMARY KEY(attempt_id,question_id));
        CREATE TABLE IF NOT EXISTS answers (attempt_id TEXT, question_id TEXT, answer TEXT, updated TEXT, PRIMARY KEY(attempt_id,question_id));
        CREATE TABLE IF NOT EXISTS speaking_recordings (attempt_id TEXT, question_id TEXT, path TEXT, duration REAL, created TEXT, PRIMARY KEY(attempt_id,question_id));
        CREATE TABLE IF NOT EXISTS writing_responses (attempt_id TEXT, question_id TEXT, response TEXT, updated TEXT, PRIMARY KEY(attempt_id,question_id));
        CREATE TABLE IF NOT EXISTS daily_activity (date TEXT PRIMARY KEY, last_updated TEXT);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        """)
        test_columns = {row[1] for row in self.db.execute("PRAGMA table_info(tests)")}
        if "audio_notice" not in test_columns:
            self.db.execute("ALTER TABLE tests ADD COLUMN audio_notice TEXT DEFAULT ''")
        attempt_columns = {row[1] for row in self.db.execute("PRAGMA table_info(attempts)")}
        if "countdown_enabled" not in attempt_columns:
            self.db.execute("ALTER TABLE attempts ADD COLUMN countdown_enabled INTEGER DEFAULT 1")
        self.db.commit()
        self.import_content()

    def import_content(self):
        root = bundle_root()
        manifest = root / "data/manifests/sources.json"
        if manifest.exists():
            for row in json.loads(manifest.read_text(encoding="utf-8")):
                self.db.execute("INSERT OR REPLACE INTO sources VALUES (?,?,?,?)", (row["source_id"], row["source_url"], row["download_status"], json.dumps(row)))
        for path in sorted((root / "data/tests").glob("*.json")):
            test = json.loads(path.read_text(encoding="utf-8"))
            # Packaged content is authoritative. Clear an older build's rows so
            # corrected question IDs and audio mappings cannot coexist with
            # stale imported records in the user's persistent database.
            self.db.execute("DELETE FROM sections WHERE test_id=?", (test["id"],))
            self.db.execute("DELETE FROM questions WHERE test_id=?", (test["id"],))
            self.db.execute("DELETE FROM audio_assets WHERE test_id=?", (test["id"],))
            self.db.execute("INSERT OR REPLACE INTO tests(id,name,provider,category,status,source_pdf,audio_notice) VALUES (?,?,?,?,?,?,?)",
                            (test["id"], test["name"], test["provider"], test["category"],
                             test["status"], test["source_pdf"], test.get("audio_notice", "")))
            for section in test["sections"]:
                self.db.execute("INSERT OR REPLACE INTO sections VALUES (?,?,?)", (test["id"], section, sum(q["section"] == section for q in test["questions"])))
            for q in test["questions"]:
                self.db.execute("INSERT OR REPLACE INTO questions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", (test["id"], q["id"], q["section"], q["module"], q["number"], q["type"], q["stimulus"], q["prompt"], json.dumps(q["choices"]), q["answer"], q["transcript"], q["audio"], q["duration"]))
            for asset in test["audio_assets"]:
                self.db.execute("INSERT OR IGNORE INTO audio_assets VALUES (?,?,?)", (test["id"], asset, ""))
        explanation_path = root / "data/explanations.json"
        if explanation_path.exists():
            explanations = json.loads(explanation_path.read_text(encoding="utf-8"))
            self.db.execute("DELETE FROM question_explanations WHERE test_id IN (SELECT id FROM tests WHERE category!='IMPORTED_ARCHIVE')")
            self.db.executemany("INSERT OR REPLACE INTO question_explanations VALUES (?,?,?,?)", (
                (item["test_id"], item["question_id"], item["zh"], item["en"])
                for item in explanations.get("items", [])
            ))
        self.db.commit()

    def tests(self):
        return self.db.execute("SELECT * FROM tests ORDER BY CASE WHEN category='OFFICIAL_ETS' THEN 0 ELSE 1 END,name").fetchall()

    def questions(self, test_id, sections):
        order = {"Reading": 0, "Listening": 1, "Writing": 2, "Speaking": 3}
        rows = [dict(r) for r in self.db.execute("SELECT * FROM questions WHERE test_id=?", (test_id,)) if r["section"] in sections]
        for row in rows:
            row["choices"] = json.loads(row["choices"])
        return sorted(rows, key=lambda q: (order[q["section"]], q["module"], q["number"]))

    def audio_ok(self, test_id, section):
        rows = self.db.execute("SELECT audio FROM questions WHERE test_id=? AND section=?", (test_id, section)).fetchall()
        return bool(rows) and all(r[0] and (bundle_root() / r[0]).exists() for r in rows)

    def unfinished(self):
        return self.db.execute("SELECT * FROM attempts WHERE status='IN_PROGRESS' ORDER BY started DESC LIMIT 1").fetchone()

    def test_completion(self, test_id):
        total = self.db.execute("SELECT COUNT(*) FROM questions WHERE test_id=?", (test_id,)).fetchone()[0]
        answered = self.db.execute("""
            SELECT COUNT(DISTINCT q.id)
            FROM questions q
            WHERE q.test_id=? AND EXISTS (
                SELECT 1
                FROM answers ans
                JOIN attempts a ON a.id=ans.attempt_id
                WHERE a.test_id=q.test_id AND a.status!='DISCARDED'
                  AND ans.question_id=q.id AND TRIM(COALESCE(ans.answer,''))!=''
            )
        """, (test_id,)).fetchone()[0]
        percent = round(answered * 100 / total) if total else 0
        return answered, total, percent

    def attempt_completion(self, attempt_id):
        attempt = self.db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
        if not attempt:
            return 0, 0, 0
        sections = json.loads(attempt["sections"])
        questions = self.questions(attempt["test_id"], sections)
        answered = self.db.execute("""
            SELECT COUNT(DISTINCT question_id) FROM answers
            WHERE attempt_id=? AND TRIM(COALESCE(answer,''))!=''
        """, (attempt_id,)).fetchone()[0]
        total = len(questions)
        percent = round(answered * 100 / total) if total else 0
        return answered, total, percent

    def make_attempt(self, attempt_id, test_id, mode, sections, countdown_enabled=True, section_seconds=None):
        self.db.execute("INSERT INTO attempts(id,test_id,mode,sections,started,status,countdown_enabled) VALUES(?,?,?,?,?,?,?)", (attempt_id, test_id, mode, json.dumps(sections), datetime.now().astimezone().isoformat(), "IN_PROGRESS", int(bool(countdown_enabled))))
        for section in sections:
            seconds = int((section_seconds or {}).get(section, 0))
            self.db.execute("INSERT OR REPLACE INTO attempt_section_timers VALUES(?,?,?,?)",
                            (attempt_id, section, seconds, datetime.now().astimezone().isoformat()))
        self.db.commit()

    def section_time(self, attempt_id, section, default=0):
        row = self.db.execute("SELECT remaining_seconds FROM attempt_section_timers WHERE attempt_id=? AND section=?",
                              (attempt_id, section)).fetchone()
        return int(row[0]) if row else int(default)

    def set_section_time(self, attempt_id, section, remaining):
        self.db.execute("INSERT OR REPLACE INTO attempt_section_timers VALUES(?,?,?,?)",
                        (attempt_id, section, max(0, int(remaining)), datetime.now().astimezone().isoformat()))
        self.db.commit()

    def question_time(self, attempt_id, question_id, default=0):
        row = self.db.execute("SELECT remaining_seconds FROM attempt_question_timers WHERE attempt_id=? AND question_id=?",
                              (attempt_id, question_id)).fetchone()
        return int(row[0]) if row else int(default)

    def set_question_time(self, attempt_id, question_id, remaining):
        self.db.execute("INSERT OR REPLACE INTO attempt_question_timers VALUES(?,?,?,?)",
                        (attempt_id, question_id, max(0, int(remaining)), datetime.now().astimezone().isoformat()))
        self.db.commit()

    def save_answer(self, attempt_id, question_id, answer):
        now = datetime.now().astimezone().isoformat()
        self.db.execute("INSERT OR REPLACE INTO answers VALUES(?,?,?,?)", (attempt_id, question_id, answer, now))
        self.db.execute("INSERT OR REPLACE INTO daily_activity VALUES(?,?)", (now[:10], now))
        self.db.commit()

    def answer(self, attempt_id, question_id):
        row = self.db.execute("SELECT answer FROM answers WHERE attempt_id=? AND question_id=?", (attempt_id, question_id)).fetchone()
        return row[0] if row else ""

    def explanation(self, test_id, question_id, language="zh-TW"):
        column = "zh" if language == "zh-TW" else "en"
        row = self.db.execute(f"SELECT {column} FROM question_explanations WHERE test_id=? AND question_id=?",
                              (test_id, question_id)).fetchone()
        return row[0] if row else ""

    def save_writing(self, attempt_id, question_id, text):
        now = datetime.now().astimezone().isoformat()
        self.db.execute("INSERT OR REPLACE INTO writing_responses VALUES(?,?,?,?)", (attempt_id, question_id, text, now))
        self.save_answer(attempt_id, question_id, text)

    def save_recording(self, attempt_id, question_id, path, duration):
        now = datetime.now().astimezone().isoformat()
        self.db.execute("INSERT OR REPLACE INTO speaking_recordings VALUES(?,?,?,?,?)", (attempt_id, question_id, str(path), duration, now))
        self.save_answer(attempt_id, question_id, str(path))

    def progress(self, attempt_id, index, elapsed):
        self.db.execute("UPDATE attempts SET index_position=?,elapsed_seconds=? WHERE id=?", (index, elapsed, attempt_id))
        self.db.commit()

    def finish(self, attempt_id, status="COMPLETE"):
        self.db.execute("UPDATE attempts SET status=?,ended=? WHERE id=?", (status, datetime.now().astimezone().isoformat(), attempt_id))
        self.db.commit()

    def setting(self, key, default=""):
        row = self.db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default

    def set_setting(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, str(value)))
        self.db.commit()
