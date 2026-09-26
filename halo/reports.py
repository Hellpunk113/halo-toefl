from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .db import user_root


def estimated_band(correct, total):
    if not total:
        return None
    return round((1 + 5 * correct / total) * 2) / 2


def attempt_stats(store, attempt_id):
    attempt = store.db.execute("SELECT * FROM attempts WHERE id=?", (attempt_id,)).fetchone()
    if not attempt:
        return None
    questions = store.questions(attempt["test_id"], json.loads(attempt["sections"]))
    answers = {r["question_id"]: r["answer"] for r in store.db.execute("SELECT * FROM answers WHERE attempt_id=?", (attempt_id,))}
    stats = {}
    for section in ("Reading", "Listening", "Writing", "Speaking"):
        sq = [q for q in questions if q["section"] == section]
        objective = [q for q in sq if q["correct"]]
        correct = sum(answers.get(q["id"], "").strip().casefold() == q["correct"].strip().casefold() for q in objective)
        stats[section] = dict(questions=len(sq), answered=sum(bool(answers.get(q["id"])) for q in sq),
                              correct=correct, graded=len(objective), accuracy=round(correct / len(objective) * 100, 1) if objective else None,
                              estimated_score=estimated_band(correct, len(objective)) if section in ("Reading", "Listening") else None)
    return dict(attempt=dict(attempt), test=store.db.execute("SELECT name FROM tests WHERE id=?", (attempt["test_id"],)).fetchone()[0], stats=stats, answers=answers, questions=questions)


def daily_data(store, day=None):
    day = day or date.today().isoformat()
    attempts = [dict(r) for r in store.db.execute("SELECT * FROM attempts WHERE substr(started,1,10)=? ORDER BY started", (day,))]
    ids = [a["id"] for a in attempts]
    sections = Counter()
    total_correct = total_graded = total_answered = total_questions = 0
    speaking_seconds = 0
    writing_words = 0
    recordings = []
    details = []
    for attempt in attempts:
        result = attempt_stats(store, attempt["id"])
        details.append(dict(id=attempt["id"], test=result["test"], mode=attempt["mode"], status=attempt["status"],
                            duration_seconds=attempt["elapsed_seconds"], sections=result["stats"]))
        for name, stat in result["stats"].items():
            if stat["questions"]:
                sections[name] += 1
            total_correct += stat["correct"]
            total_graded += stat["graded"]
            total_answered += stat["answered"]
            total_questions += stat["questions"]
        for row in store.db.execute("SELECT * FROM speaking_recordings WHERE attempt_id=?", (attempt["id"],)):
            recordings.append(dict(row))
            speaking_seconds += row["duration"]
        for row in store.db.execute("SELECT response FROM writing_responses WHERE attempt_id=?", (attempt["id"],)):
            writing_words += len(row[0].split())
    return dict(date=day, total_study_seconds=sum(a["elapsed_seconds"] for a in attempts), sessions=len(attempts),
                full_mocks_completed=sum(a["mode"] == "FULL" and a["status"] == "COMPLETE" for a in attempts),
                sections_practiced=dict(sections), questions_answered=total_answered, questions_available=total_questions,
                questions_correct=total_correct, incorrect_questions=max(0, total_graded-total_correct),
                objective_accuracy=round(total_correct/total_graded*100,1) if total_graded else None,
                speaking_prompts_completed=len(recordings), speaking_recorded_seconds=round(speaking_seconds,1),
                recordings=recordings, writing_tasks_completed=sum(1 for a in attempts for r in store.db.execute("SELECT response FROM writing_responses WHERE attempt_id=?", (a["id"],)) if r[0].strip()),
                writing_words=writing_words, attempts=details)


def pdf_bytes(report):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, leftMargin=45, rightMargin=45, topMargin=45, bottomMargin=45)
    styles = getSampleStyleSheet()
    story = [Paragraph("HALO TOEFL — Daily Report", styles["Title"]),
             Paragraph(report["date"], styles["Heading2"]), Spacer(1, 12)]
    rows = [("Study time", f"{report['total_study_seconds']//60} minutes"), ("Sessions", str(report["sessions"])),
            ("Full mocks completed", str(report["full_mocks_completed"])),
            ("Questions answered", str(report["questions_answered"])), ("Correct", str(report["questions_correct"])),
            ("Objective accuracy", f"{report['objective_accuracy']}%" if report["objective_accuracy"] is not None else "N/A"),
            ("Speaking prompts", str(report["speaking_prompts_completed"])),
            ("Recorded speaking", f"{report['speaking_recorded_seconds']} seconds"),
            ("Writing tasks", str(report["writing_tasks_completed"])), ("Writing words", str(report["writing_words"]))]
    table = Table([["Metric", "Value"], *rows], colWidths=[240, 240])
    table.setStyle(TableStyle([("BACKGROUND", (0,0),(-1,0),colors.HexColor("#143b70")),
                               ("TEXTCOLOR",(0,0),(-1,0),colors.white),("GRID",(0,0),(-1,-1),0.3,colors.lightgrey),
                               ("PADDING",(0,0),(-1,-1),7)]))
    story.append(table)
    story.append(Spacer(1, 18))
    story.append(Paragraph("Attempts", styles["Heading2"]))
    for attempt in report["attempts"]:
        story.append(Paragraph(f"{attempt['test']} — {attempt['mode']} — {attempt['status']} — {attempt['duration_seconds']//60} min", styles["Normal"]))
        for name, stat in attempt["sections"].items():
            if stat["questions"]:
                score = f"; estimated {stat['estimated_score']}/6" if stat["estimated_score"] is not None else ""
                story.append(Paragraph(f"{name}: {stat['answered']}/{stat['questions']} answered, {stat['correct']}/{stat['graded']} correct{score}", styles["Normal"]))
        story.append(Spacer(1, 8))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Estimated scores are practice estimates and are not official ETS conversions.", styles["Italic"]))
    doc.build(story)
    return buffer.getvalue()


def csv_bytes(report):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["date", "sessions", "study_seconds", "full_mocks", "answered", "correct", "objective_accuracy", "speaking_prompts", "speaking_seconds", "writing_tasks", "writing_words"])
    writer.writerow([report["date"], report["sessions"], report["total_study_seconds"], report["full_mocks_completed"], report["questions_answered"], report["questions_correct"], report["objective_accuracy"], report["speaking_prompts_completed"], report["speaking_recorded_seconds"], report["writing_tasks_completed"], report["writing_words"]])
    return buffer.getvalue().encode("utf-8-sig")


def export_daily(store, day, format, target):
    report = daily_data(store, day)
    target = Path(target)
    if format == "PDF":
        target.write_bytes(pdf_bytes(report))
    elif format == "CSV":
        target.write_bytes(csv_bytes(report))
    elif format == "JSON":
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    elif format == "ZIP":
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("daily-report.pdf", pdf_bytes(report))
            z.writestr("daily-report.csv", csv_bytes(report))
            z.writestr("daily-report.json", json.dumps(report, ensure_ascii=False, indent=2))
            for recording in report["recordings"]:
                path = Path(recording["path"])
                if path.exists():
                    z.write(path, "speaking-recordings/" + path.name)
            for attempt in report["attempts"]:
                for row in store.db.execute("SELECT question_id,response FROM writing_responses WHERE attempt_id=?", (attempt["id"],)):
                    z.writestr(f"writing-responses/{attempt['id']}-{row['question_id']}.txt", row["response"])
    return target
