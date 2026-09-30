"""Validate packaged test structure before producing a desktop release."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CLOZE_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z]+)(?P<between>[ \t\r\n]*)"
    r"(?P<gap>_+(?:[ \t]*_+)*|-+(?:[ \t\r\n]*-+)*(?![ \t\r\n]*[A-Za-z]))"
    r"(?P<label>\d{1,2})?"
)
EXPECTED_READING_TYPE = {
    **{number: "Complete the Words" for number in range(1, 11)},
    **{number: "Read in Daily Life" for number in range(11, 16)},
    **{number: "Read an Academic Passage" for number in range(16, 21)},
}


def validate() -> list[str]:
    errors: list[str] = []
    for path in sorted((ROOT / "data" / "tests").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        questions = data.get("questions", [])
        ids = [q["id"] for q in questions]
        if len(ids) != len(set(ids)):
            errors.append(f"{path.name}: duplicate question IDs")
        for question in questions:
            choices = question.get("choices") or {}
            answer = str(question.get("answer") or "")
            if choices and answer and answer not in choices:
                errors.append(f"{path.name}/{question['id']}: answer {answer!r} is not a choice")
            audio = str(question.get("audio") or "")
            if audio and not (ROOT / audio).is_file():
                errors.append(f"{path.name}/{question['id']}: missing audio {audio}")

        if data.get("status") != "COMPLETE":
            continue
        reading = [q for q in questions if q["section"] == "Reading"]
        if len(reading) != 40:
            errors.append(f"{path.name}: complete test has {len(reading)} reading questions")
            continue
        for module in (1, 2):
            module_questions = sorted((q for q in reading if q["module"] == module), key=lambda q: q["number"])
            numbers = [q["number"] for q in module_questions]
            if numbers != list(range(1, 21)):
                errors.append(f"{path.name}/module {module}: reading numbers are {numbers}")
                continue
            for question in module_questions:
                expected = EXPECTED_READING_TYPE[question["number"]]
                if question["type"] != expected:
                    errors.append(f"{path.name}/{question['id']}: expected {expected}, got {question['type']}")
                if not str(question.get("stimulus") or "").strip():
                    errors.append(f"{path.name}/{question['id']}: empty reading stimulus")
            cloze = module_questions[:10]
            if len({q["stimulus"] for q in cloze}) != 1:
                errors.append(f"{path.name}/module {module}: cloze stimulus differs within the group")
            matches = list(CLOZE_PATTERN.finditer(cloze[0]["stimulus"]))
            if len(matches) != len(cloze):
                errors.append(f"{path.name}/module {module}: {len(matches)} cloze gaps for {len(cloze)} questions")
            for question, match in zip(cloze, matches):
                answer = str(question.get("answer") or "")
                prefix = match.group("prefix")
                missing = len(answer) - len(prefix) if answer.casefold().startswith(prefix.casefold()) else len(answer)
                gap = sum(match.group("gap").count(char) for char in "_-")
                if missing != gap:
                    errors.append(f"{path.name}/{question['id']}: gap length {gap}, answer length {missing}")
            for start, end in ((10, 12), (12, 15), (15, 20)):
                group = module_questions[start:end]
                if len({q["stimulus"] for q in group}) != 1:
                    errors.append(f"{path.name}/module {module}: questions {start+1}-{end} do not share one passage")
            for question in module_questions[10:]:
                stimulus = question["stimulus"]
                if re.search(r"Fill in the missing letters|_{2,}", stimulus, re.I):
                    errors.append(f"{path.name}/{question['id']}: cloze text leaked into another task")
                if re.fullmatch(r"\s*Reading(?: Section)?\s*[,·]?\s*Module\s*\d+\s*", stimulus, re.I):
                    errors.append(f"{path.name}/{question['id']}: boilerplate-only stimulus")
    return errors


def main() -> None:
    errors = validate()
    if errors:
        raise SystemExit("Question-bank validation failed:\n" + "\n".join(f"- {error}" for error in errors))
    print("Question-bank validation passed.")


if __name__ == "__main__":
    main()
