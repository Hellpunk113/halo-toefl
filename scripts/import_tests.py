"""Conservative PDF and audio importer for HALO TOEFL's local practice library."""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import zipfile
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader
import pdfplumber

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "resources/raw"
AUDIO = ROOT / "resources/audio"
PROCESSED = ROOT / "resources/processed"
TRANSCRIPTS = ROOT / "resources/transcripts"
TESTS = ROOT / "data/tests"
REPORTS = ROOT / "reports/import-validation"
for p in (AUDIO, PROCESSED, TRANSCRIPTS, TESTS, REPORTS, ROOT / "resources/images"):
    p.mkdir(parents=True, exist_ok=True)


def clean(text):
    text = re.sub(r"(?m)^TOEFL iBT[®™]?[^\n]*\d+\s*$", "", text)
    text = re.sub(r"\r", "", text)
    text = re.sub(r"(?m)^\s+$", "", text)
    return text.strip()


def clean_source_text(sid, text):
    if sid != "prepdrills-2026":
        return text
    # PrepDrills pages contain a diagonal site watermark whose individual
    # letters are exposed as standalone PDF text. Remove only those isolated
    # fragments; ordinary question, choice, and passage lines remain intact.
    fragments = {"s", "l", "i", "r", "D", "p", "e", "m", "o", "t",
                 "P o", "c", "s.", "rill", "efl.", "p r", "s l l", "r m"}
    lines = [line for line in text.splitlines() if line.strip() not in fragments]
    text = "\n".join(lines)
    # A few watermark fragments share a line immediately before a numbered
    # question. Keep the question and discard the short fragment prefix.
    text = re.sub(r"(?m)^\s*(?:[slirDepmotcP.]\s+){1,5}(?=\d{1,2}\.)", "", text)
    return text


FOOTER_RE = re.compile(
    r"(?im)^\s*(?:Вариант\s+\d+\s*·.*|TOEFL\s+2026\s*·\s*ExamBooster.*|"
    r"Reach120\s*·.*|\d+\s*===\s*PAGE\s*===|===\s*PAGE\s*===|\d+\s*/\s*\d+)\s*$"
)


def clean_content_piece(text):
    """Clean PDF page furniture without removing ordinary question prose."""
    text = FOOTER_RE.sub("", text)
    text = re.sub(r"(?is)Want this scored.*?Start free\s*→\s*toefl\.prepdrills\.com.*$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _looks_like_title(line):
    line = line.strip()
    if not (10 <= len(line) <= 100) or re.search(r"[.!?:;]$", line):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'’-]*", line)
    if len(words) < 3:
        return False
    significant = [word for word in words if word.lower() not in {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with"}]
    return bool(significant) and sum(word[0].isupper() for word in significant) >= max(2, len(significant) - 1)


def split_choice_tail(text):
    """Separate option D from the next passage/directions on the same PDF page."""
    text = text.strip()
    markers = [
        r"(?im)^\s*Read (?:an?|the)\b",
        r"(?im)^\s*READ AN ACADEMIC PASSAGE\s*$",
        r"(?im)^\s*Listen to (?:an?|the)\b.*(?:—|Прослушайте)",
        r"(?im)^\s*TOCMK",
        r"(?im)^\s*(?:Reading|Listening|Writing|Speaking)\s*$",
    ]
    positions = [m.start() for pattern in markers if (m := re.search(pattern, text))]
    lines = text.splitlines(keepends=True)
    offset = 0
    for index, raw in enumerate(lines[1:], 1):
        offset += len(lines[index - 1])
        if _looks_like_title(raw) and any(line.strip() for line in lines[index + 1:index + 3]):
            positions.append(offset)
            break
    if positions:
        cut = min(positions)
        choice, tail = text[:cut], text[cut:]
    else:
        choice, tail = text, ""
    # Footer text belongs to neither the option nor the next passage.
    footer = FOOTER_RE.search(choice)
    if footer:
        choice = choice[:footer.start()]
    if "\n" in choice:
        choice = re.sub(r"\n\s*\d{1,2}\s*$", "", choice)
    return clean_content_piece(choice), clean_content_piece(tail)


def section_at(text, prior):
    head = text[:500]
    m = re.search(r"\b(Reading|Listening|Writing|Speaking) Section\b", head, re.I)
    if not m:
        m = re.search(r"(?im)^(?:SECTION\s+\d+(?:\s+OF\s+\d+)?\s*)?(?:Section\s+\d+\s*[—–-]\s*)?(Reading|Listening|Writing|Speaking)(?:\s*[·,—–-]\s*Module\s*\d+)?\s*$", head)
    return m.group(1).title() if m else prior


def module_at(text, prior):
    m = re.search(r"\b(?:Reading|Listening)(?: Section)?(?:,|\s*·)?\s*Module\s*(\d+)", text[:300], re.I)
    return int(m.group(1)) if m else prior


def parse_listening_page(text, module, page, keys, next_number):
    """Parse numbered and visually ordered listening questions.

    Newer ETS PDFs omit printed numbers for questions attached to a shared
    conversation/talk. Their four-choice blocks still preserve exact order.
    """
    output = []
    a_positions = [m.start() for m in re.finditer(r"(?m)^\s*(?:\(A\)|A\.)\s+", text)]
    cursor = 0
    for a_pos in a_positions:
        pre = text[cursor:a_pos].strip()
        lines = [line.strip() for line in pre.splitlines() if line.strip()]
        if not lines:
            continue
        prompt_lines = [lines[-1]]
        index = len(lines) - 2
        while index >= 0:
            previous = lines[index]
            if re.search(r"[.!?:]$", previous) or re.match(r"^(?:Man|Woman|Professor|Host|Student|Speaker):", previous):
                break
            if re.match(r"^(?:Listening Section|Listen to|Choose the best|TOEFL iBT)", previous, re.I):
                break
            prompt_lines.insert(0, previous)
            index -= 1
        raw_prompt = " ".join(prompt_lines)
        # Some third-party layouts put a recording title and URL before
        # "Question 19" on the same extracted line. Prefer that explicit
        # marker wherever it occurs so numbering and audio mapping stay exact.
        explicit = re.search(r"\bQuestion\s+(\d{1,2})\s+(.*)$", raw_prompt, re.S | re.I)
        if not explicit:
            explicit = re.match(r"(\d{1,2})(?:\.|\s)\s*(.*)", raw_prompt, re.S | re.I)
        if explicit:
            number, prompt = int(explicit.group(1)), explicit.group(2).strip()
        else:
            number, prompt = next_number, raw_prompt
        # Choices in these source PDFs occupy one visual line each.
        tail = text[a_pos:]
        choice_rows = list(re.finditer(r"(?m)^\s*(?:\(([A-D])\)|([A-D])\.)\s*(.+)$", tail))
        choices = {}
        d_end = None
        for row in choice_rows:
            letter = row.group(1) or row.group(2)
            choices[letter] = row.group(3).strip()
            if letter == "D":
                d_end = a_pos + row.end()
                break
        if len(choices) != 4 or d_end is None:
            continue
        context = "\n".join(lines[:index + 1]).strip()
        qtype = classify("Listening", context, prompt)
        output.append(dict(id=f"l{module}-{number:02d}", section="Listening", module=module,
                           number=number, page=page, type=qtype, stimulus="", prompt=prompt,
                           choices=choices, answer=keys.get(("Listening", module), {}).get(number, ""),
                           transcript=context, audio="", duration=0))
        next_number = max(next_number, number + 1)
        cursor = d_end
    return output, next_number


def parse_special_speaking(sid, text, page):
    if sid != "reach120-2026":
        return []
    output = []
    repeat = re.search(r"Listen and Repeat.*?(?=Take an Interview)", text, re.S | re.I)
    if repeat:
        for number, prompt in re.findall(r"(?m)^\s*(\d+)\.\s+\d+ words\s*\n(.+?)\s*\n\d+ words\s*$", repeat.group(0)):
            number = int(number)
            output.append(dict(id=f"s1-{number:02d}", section="Speaking", module=1, number=number,
                               page=page, type="Listen and Repeat", stimulus="", prompt=prompt.strip(),
                               choices={}, answer="", transcript="", audio="", duration=15))
    interview = text.split("Take an Interview", 1)[-1] if "Take an Interview" in text else ""
    matches = list(re.finditer(r"(?m)^\s*(\d+)\.\s+[^\n]+\n", interview))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(interview)
        number = int(match.group(1))
        prompt = interview[match.end():end].strip()
        output.append(dict(id=f"s2-{number:02d}", section="Speaking", module=2, number=number,
                           page=page, type="Take an Interview", stimulus="", prompt=prompt,
                           choices={}, answer="", transcript="", audio="", duration=45))
    return output


def answer_keys(pages, sid=""):
    keys = defaultdict(dict)
    for text in pages:
        head = text[:200]
        m = re.search(r"(Reading|Listening) Section, Module\s*(\d+)\s*Answer Key", head, re.I)
        if m:
            section, module = m.group(1).title(), int(m.group(2))
            body = text.split("Answer Key", 1)[-1]
            for num, ans in re.findall(r"(?m)^\s*(\d{1,2})\s+([A-Da-z]+)\s*$", body):
                keys[(section, module)][int(num)] = ans.strip()
        elif re.search(r"Writing Section\s*Answer Key", head, re.I):
            body = text.split("Answer Key", 1)[-1]
            for num, ans in re.findall(r"(?m)^\s*(\d{1,2})\s+(.+)$", body):
                keys[("Writing", 1)][int(num)] = ans.strip()
    if sid == "prepdrills-2026":
        keys[("Reading", 1)].update(dict(enumerate(
            ["stone","built","polyp","skeleton","joins","hundreds","grow","shelter","waters","rise"], 1)))
        keys[("Reading", 1)].update(dict(enumerate(list("BCBCBCBDBC"), 11)))
        keys[("Reading", 2)].update(dict(enumerate(
            ["melts","called","lighter","rises","surface","pressure","bursts","eruption","lava","gradually"], 1)))
        keys[("Reading", 2)].update(dict(enumerate(list("CCBAC CABC C".replace(" ", "")), 11)))
        keys[("Listening", 1)].update(dict(enumerate(list("BCABCABCABBCBCCACD"), 1)))
        keys[("Listening", 2)].update(dict(enumerate(list("BACBABBABC BCCACA".replace(" ", "")), 1)))
        writing = [
            "The hotel that we stayed at was wonderful.",
            "Do you know if he will be starting at a new company?",
            "Can you tell me whether the castle will be open?",
            "What time does it begin?", "Do you know how good the coffee is?",
            "How difficult is the trail this time of year?", "Do you know when the due date is?",
            "What skills will you learn?", "She wanted to know where she could submit the assignment.",
            "I used the guide that was recommended by the librarian."]
        keys[("Writing", 1)].update(dict(enumerate(writing, 1)))
    elif sid == "reach120-2026":
        objective = list("BACDDBAADDDDDCACABADBDBDBBCB")
        keys[("Reading", 1)].update(dict(enumerate(objective[:18], 1)))
        keys[("Listening", 1)].update(dict(enumerate(objective[18:], 19)))
        writing = ["I had a delicious sandwich today.", "He works at the local hospital downtown.",
                   "She bought some fresh flowers yesterday.", "They take the yellow bus daily.",
                   "I really enjoyed the keynote presentation yesterday.",
                   "She quickly scored three beautiful goals today.",
                   "They carefully prepared a traditional Italian meal.",
                   "I spent the entire afternoon reading novels in the garden.",
                   "She explained the difficult concept to all the students.",
                   "She always prepares healthy organic meals for the whole family."]
        keys[("Writing", 1)].update(dict(enumerate(writing, 1)))
    return keys


def classify(section, context, prompt):
    s = (context + " " + prompt).lower()
    if section == "Reading":
        if "fill in the missing letters" in s or "complete the words" in s:
            return "Complete the Words"
        if "academic passage" in s or len(context) > 1000:
            return "Read an Academic Passage"
        return "Read in Daily Life"
    if section == "Listening":
        if "choose the best response" in s:
            return "Listen and Choose a Response"
        if "conversation" in s:
            return "Listen to a Conversation"
        if "announcement" in s:
            return "Listen to an Announcement"
        if "talk" in s or "lecture" in s:
            return "Listen to an Academic Talk"
        return "Listening"
    if section == "Writing":
        return "Build a Sentence"
    return section


def parse_questions(text, section, module, page, keys):
    # A PDF page may contain several questions; preserve page context for every one.
    # Some ETS PDFs render a number as ``17 .``. Accept whitespace before the
    # period so that the next question cannot be swallowed by the preceding
    # question's final choice.
    matches = list(re.finditer(r"(?im)^\s*(?:Question\s+(\d{1,2})|(\d{1,2})\s*\.)\s*", text))
    output = []
    active_context = clean_content_piece(text[:matches[0].start()]) if matches else ""
    for i, match in enumerate(matches):
        number = int(match.group(1) or match.group(2))
        if number > 60:
            continue
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunk = text[match.end():end].strip()
        next_context = ""
        choice_matches = list(re.finditer(r"(?m)^\s*(?:\(([A-D])\)|([A-D])\.)\s*", chunk))
        if choice_matches:
            prompt = chunk[:choice_matches[0].start()].strip()
            choices = {}
            for ci, cm in enumerate(choice_matches):
                ce = choice_matches[ci + 1].start() if ci + 1 < len(choice_matches) else len(chunk)
                value = chunk[cm.end():ce].strip()
                if ci == len(choice_matches) - 1:
                    value, next_context = split_choice_tail(value)
                choices[cm.group(1) or cm.group(2)] = clean_content_piece(value)
        else:
            prompt, choices = chunk, {}
        if not prompt and not choices:
            continue
        # Strip introductory directions, but keep stimulus text. Review can show transcript.
        context = active_context
        context = re.sub(r"(?s)^.*?(?=Read a |Listen to a |Choose the best response\.|[A-Z][a-z]+\s+[A-Z][a-z]+\n)", "", context) if len(context) > 2000 else context
        if section == "Listening":
            transcript = context
            context = ""
        else:
            transcript = ""
        qtype = classify(section, context or transcript, prompt)
        if choices and qtype == "Complete the Words":
            qtype = "Read an Academic Passage" if len(context) > 1000 else "Read in Daily Life"
        output.append(dict(id=f"{section[0].lower()}{module}-{number:02d}", section=section,
                           module=module, number=number, page=page, type=qtype,
                           stimulus=context, prompt=prompt, choices=choices,
                           answer=keys.get((section, module), {}).get(number, ""),
                           transcript=transcript, audio="", duration=0))
        if next_context:
            active_context = next_context
    return output


def parse_cloze(text, module, page, keys):
    m = re.search(r"Fill in the missing letters in the paragraph\.\s*\(Questions 1\s*[–-]\s*10\)\s*(.*?)\s*(?:Read an? |TOEFL iBT)", text, re.S | re.I)
    if m:
        passage = m.group(1).strip()
    elif "COMPLETE THE WORDS" in text and "READ IN DAILY LIFE" in text:
        # The PrepDrills Module 1 PDF has decorative diagonal watermark text
        # interleaved with the printed "Questions 1–10" range. Recover the
        # paragraph from the stable instruction and following task heading.
        start = text.upper().rfind("COMPLETE THE WORDS")
        body = text[start:]
        instruction = re.search(r"Fill in the missing letters in the paragraph\.[^\n]*\n", body, re.I)
        if not instruction:
            return []
        passage = body[instruction.end():].split("READ IN DAILY LIFE", 1)[0].strip()
    else:
        return []
    return [dict(id=f"r{module}-{i:02d}", section="Reading", module=module, number=i,
                 page=page, type="Complete the Words", stimulus=passage,
                 prompt=f"Complete missing letters, blank {i} of 10.", choices={},
                 answer=keys.get(("Reading", module), {}).get(i, ""), transcript="", audio="", duration=0)
            for i in range(1, 11)]


def _task_chunks(text, appendix=False):
    dot = r"\s*·" if appendix else ""
    matches = list(re.finditer(rf"(?m)^Задание\s+(\d+){dot}\s+([A-Z]+-[A-Z]+-[0-9-]+).*?$", text))
    result = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        result[int(match.group(1))] = (match.group(2), text[match.end():end].strip())
    return result


def _bare_choice_question(chunk):
    rows = list(re.finditer(r"(?m)^\s*([A-D])\s+", chunk))
    if len(rows) < 4:
        return chunk.strip(), {}
    rows = rows[:4]
    prompt = chunk[:rows[0].start()].strip()
    choices = {}
    for index, row in enumerate(rows):
        end = rows[index + 1].start() if index + 1 < len(rows) else len(chunk)
        value = re.sub(r"\s*▶\s*Слушать.*", "", chunk[row.end():end].strip(), flags=re.S)
        if index == len(rows) - 1:
            value, _ = split_choice_tail(value)
        choices[row.group(1)] = clean_content_piece(value)
    return prompt, choices


def parse_exambooster(pages):
    """Convert the Russian-labelled demo while preserving its English test content."""
    question_text = "\n".join(pages[5:28])
    key_text = "\n".join(pages[28:35])
    transcript_text = "\n".join(pages[35:39])
    tasks = _task_chunks(question_text)
    key_tasks = _task_chunks(key_text, appendix=True)
    transcript_tasks = _task_chunks(transcript_text, appendix=True)

    def task_keys(number, words=False):
        body = key_tasks.get(number, ("", ""))[1]
        first = body.split("\n1.", 1)[0]
        pattern = r"(\d+)\s+([A-Za-z]+)" if words else r"(\d+)\s+([A-D])\b"
        return {int(n): answer for n, answer in re.findall(pattern, first)}

    def transcript(number):
        body = transcript_tasks.get(number, ("", ""))[1]
        body = re.split(r"(?m)^Вариант 1 ·", body, 1)[0]
        return re.sub(r"\s+", " ", body).strip()

    output = []
    reading_number = 0
    for task in range(1, 4):
        body = tasks[task][1]
        body = re.sub(r"^.*?\n", "", body, count=1)
        body = re.split(r"(?m)^Вариант 1 ·", body, 1)[0].strip()
        keys = task_keys(task, words=True)
        for sub in range(1, 11):
            reading_number += 1
            output.append(dict(id=f"r1-{reading_number:02d}", section="Reading", module=1,
                               number=reading_number, page=6 + task // 3, type="Complete the Words",
                               stimulus=body, prompt=f"Complete missing letters, blank {sub} of 10.",
                               choices={}, answer=keys.get(sub, ""), transcript="", audio="", duration=0))
    for task in range(4, 10):
        body = tasks[task][1]
        matches = list(re.finditer(r"(?m)^\s*(\d+)\.\s+", body))
        stimulus = body[:matches[0].start()].strip() if matches else body
        stimulus = re.sub(r"^.*?\n", "", stimulus, count=1)
        keys = task_keys(task)
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
            prompt, choices = _bare_choice_question(body[match.end():end])
            if len(choices) != 4:
                continue
            reading_number += 1
            output.append(dict(id=f"r1-{reading_number:02d}", section="Reading", module=1,
                               number=reading_number, page=7 + task // 2,
                               type="Read in Daily Life" if task <= 7 else "Read an Academic Passage",
                               stimulus=stimulus, prompt=prompt, choices=choices,
                               answer=keys.get(int(match.group(1)), ""), transcript="", audio="", duration=0))

    listening_number = 0
    for task in range(10, 41):
        body = tasks[task][1]
        keys = task_keys(task)
        if task <= 29:
            prompt, choices = _bare_choice_question(body)
            parsed = [(1, "Choose the best response.", choices)]
            qtype = "Listen and Choose a Response"
        else:
            matches = list(re.finditer(r"(?m)^\s*(\d+)\.\s+", body))
            parsed = []
            for index, match in enumerate(matches):
                end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
                prompt, choices = _bare_choice_question(body[match.end():end])
                if len(choices) == 4:
                    parsed.append((int(match.group(1)), prompt, choices))
            qtype = ("Listen to a Conversation" if task <= 34 else
                     "Listen to an Announcement" if task <= 37 else "Listen to an Academic Talk")
        for sub, prompt, choices in parsed:
            if len(choices) != 4:
                continue
            listening_number += 1
            output.append(dict(id=f"l1-{listening_number:02d}", section="Listening", module=1,
                               number=listening_number, page=13 + (task - 10) // 4, type=qtype,
                               stimulus="", prompt=prompt, choices=choices,
                               answer=keys.get(sub, ""), transcript=transcript(task),
                               audio="", duration=0))

    for task in range(41, 51):
        body = re.split(r"(?m)^Вариант 1 ·", tasks[task][1], 1)[0].strip()
        body = re.sub(r"^.*?\n", "", body, count=1)
        answer = key_tasks.get(task, ("", ""))[1].splitlines()[0].strip()
        output.append(dict(id=f"w1-{task - 40:02d}", section="Writing", module=1,
                           number=task - 40, page=24 + (task - 41) // 4, type="Build a Sentence",
                           stimulus="", prompt=body, choices={}, answer=answer,
                           transcript="", audio="", duration=0))
    for task, qtype, duration in [(51, "Write an Email", 420),
                                  (52, "Write for an Academic Discussion", 600)]:
        body = re.split(r"(?m)^Вариант 1 ·", tasks[task][1], 1)[0].strip()
        body = re.sub(r"^.*?\n", "", body, count=1)
        output.append(dict(id=f"w1-{task - 40:02d}", section="Writing", module=1,
                           number=task - 40, page=26 + task - 51, type=qtype,
                           stimulus="", prompt=body, choices={}, answer="",
                           transcript="", audio="", duration=duration))

    speaking = transcript_tasks.get(53, ("", ""))[1]
    repeats = re.findall(r"(?ms)^Speaker:\s*(.*?)(?=^Speaker:|^Задание 54|\Z)", speaking)
    for number, prompt in enumerate(repeats, 1):
        output.append(dict(id=f"s1-{number:02d}", section="Speaking", module=1,
                           number=number, page=28, type="Listen and Repeat", stimulus="",
                           prompt=re.sub(r"\s+", " ", prompt).strip(), choices={}, answer="",
                           transcript="", audio="", duration=15))
    interview = transcript_tasks.get(54, ("", ""))[1]
    prompts = re.findall(r"(?ms)^Interviewer:\s*(.*?)(?=^Interviewer:|^Вариант 1 ·|\Z)", interview)
    for number, prompt in enumerate(prompts, 1):
        output.append(dict(id=f"s2-{number:02d}", section="Speaking", module=2,
                           number=number, page=28, type="Take an Interview", stimulus="",
                           prompt=re.sub(r"\s+", " ", prompt).strip(), choices={}, answer="",
                           transcript="", audio="", duration=45))
    return output


def extract_audio(sid, records):
    assets = []
    for record in records:
        if record["source_type"] not in ("AUDIO_ZIP", "AUDIO") or record["download_status"] != "DOWNLOADED":
            continue
        path = RAW / record["local_filename"]
        if path.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(path) as z:
                    for member in z.infolist():
                        if member.is_dir() or Path(member.filename).suffix.lower() not in (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".mp4"):
                            continue
                        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(member.filename).stem) + Path(member.filename).suffix.lower()
                        target = AUDIO / sid / safe
                        target.parent.mkdir(parents=True, exist_ok=True)
                        if not target.exists():
                            with z.open(member) as inp, target.open("wb") as out:
                                shutil.copyfileobj(inp, out)
                        if target.suffix.lower() == ".mp4":
                            playable = target.with_suffix(".mp3")
                            if not playable.exists():
                                try:
                                    import imageio_ffmpeg
                                    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-i", str(target), "-vn", "-codec:a", "libmp3lame", "-q:a", "4", str(playable)], check=True, timeout=90)
                                except Exception as exc:
                                    print(f"CONVERSION ERROR {target.name}: {exc}", flush=True)
                            target = playable if playable.exists() else target
                        assets.append(str(target.relative_to(ROOT)).replace("\\", "/"))
            except Exception as exc:
                print(f"AUDIO ERROR {sid}: {exc}", flush=True)
        elif path.suffix.lower() in (".mp3", ".wav", ".m4a", ".aac"):
            target = AUDIO / sid / path.name
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
            assets.append(str(target.relative_to(ROOT)).replace("\\", "/"))
    synthetic_dir = AUDIO / sid
    if synthetic_dir.exists():
        for path in sorted(synthetic_dir.glob("synthetic-*.*")):
            if path.suffix.lower() not in (".wav", ".mp3"):
                continue
            assets.append(str(path.relative_to(ROOT)).replace("\\", "/"))
    return list(dict.fromkeys(assets))


def map_audio(questions, assets):
    unmatched = []
    for q in questions:
        if q["section"] not in ("Listening", "Speaking"):
            continue
        module = q["module"]
        number = q["number"]
        synthetic = [x for x in assets if Path(x).stem.lower() == f"synthetic-{q['id']}".lower()]
        preferred = [x for x in synthetic if Path(x).suffix.lower() == ".mp3"] or synthetic
        if preferred:
            q["audio"] = preferred[0]
            continue
        if q["section"] == "Listening" and any("reach120-2026" in x for x in assets):
            slug = ("apology-for-a-mix-up" if number == 19 else
                    "a-double-booked-study-room" if number in (20, 21) else
                    "bookstore-buyback-week-begins" if number in (22, 23) else
                    "adding-sound-to-early-films" if 24 <= number <= 28 else "")
            special = [x for x in assets if slug and slug in x]
            if len(special) == 1:
                q["audio"] = special[0]
                continue
        section_assets = [x for x in assets if ("Speaking" if q["section"] == "Speaking" else "Listening") in x.split("/")[-1] or q["section"].lower() in x.lower()]
        choices = []
        for asset in section_assets:
            name = Path(asset).stem.lower()
            if q["section"] == "Listening":
                if not re.search(rf"(?:listening|listen)[_-]?{module}(?:_|\b)", name):
                    continue
                singles = re.findall(r"question[_-]?(\d+)", name)
                ranges = re.findall(r"questions?[_-]?(\d+)[_-](\d+)", name)
                if number in [int(x) for x in singles] or any(int(a) <= number <= int(b) for a, b in ranges):
                    choices.append(asset)
            else:
                label = "listen_repeat" if module == 1 else "interview"
                if label in name and re.search(rf"(?:question[_-]?)?{number}(?:\D|$)", name):
                    choices.append(asset)
        if len(choices) == 1:
            q["audio"] = choices[0]
        else:
            unmatched.append(q["id"])
    return unmatched


def import_one(sid, records):
    pdfs = [r for r in records if r["source_type"] == "PDF" and r["download_status"] == "DOWNLOADED"]
    assets = extract_audio(sid, records)
    questions = []
    pages = []
    errors = []
    if pdfs:
        try:
            pdf_path = RAW / pdfs[0]["local_filename"]
            # pdfplumber preserves word spacing on newer ETS PDFs whose embedded
            # font maps cause pypdf to split nearly every word into fragments.
            if sid in {"ets-student-1", "ets-student-2", "ets-teacher-1", "ets-teacher-2"}:
                reader = PdfReader(pdf_path)
                pages = [clean(page.extract_text() or "") for page in reader.pages]
            else:
                with pdfplumber.open(pdf_path) as document:
                    pages = [clean_source_text(sid, clean(page.extract_text(x_tolerance=2, y_tolerance=3) or ""))
                             for page in document.pages]
            (PROCESSED / f"{sid}.txt").write_text("\n\n=== PAGE ===\n\n".join(pages), encoding="utf-8")
            keys = answer_keys(pages, sid)
            if sid == "exambooster-demo":
                questions = parse_exambooster(pages)
            section, module = "", 1
            listening_next = {1: 1, 2: 1}
            in_answer_key = False
            for page_no, text in enumerate(pages, 1):
                if sid == "exambooster-demo":
                    break
                if sid in {"prepdrills-2026", "reach120-2026", "exambooster-demo"} and re.search(r"(?:AFTER YOU FINISH|^ANSWERS\s*$|Answer key and explanations)", text[:700], re.I | re.M):
                    in_answer_key = True
                if in_answer_key:
                    continue
                new_section = section_at(text, section)
                if new_section != section:
                    section, module = new_section, 1
                else:
                    section = new_section
                module = module_at(text, module)
                if not section or "Answer Key" in text[:200]:
                    continue
                if section == "Reading":
                    questions.extend(parse_cloze(text, module, page_no, keys))
                if section in ("Reading", "Writing"):
                    questions.extend(parse_questions(text, section, module if section != "Writing" else 1, page_no, keys))
                elif section == "Listening":
                    parsed, listening_next[module] = parse_listening_page(text, module, page_no, keys, listening_next[module])
                    questions.extend(parsed)
                elif section == "Speaking":
                    qtype = "Listen and Repeat" if "Listen and Repeat" in text[:300] else "Take an Interview"
                    label = "Trainer" if qtype == "Listen and Repeat" else "Interviewer"
                    prompts = re.findall(rf"(?ms)^{label}:\s*(.*?)(?=^{label}:|TOEFL iBT|\Z)", text)
                    for n, prompt in enumerate(prompts, 1):
                        qmod = 1 if qtype == "Listen and Repeat" else 2
                        questions.append(dict(id=f"s{qmod}-{n:02d}", section="Speaking", module=qmod,
                                              number=n, page=page_no, type=qtype, stimulus="", prompt=prompt.strip(),
                                              choices={}, answer="", transcript="", audio="", duration=15 if qmod == 1 else 45))
                    questions.extend(parse_special_speaking(sid, text, page_no))
                if section == "Writing":
                    for marker, number, qtype, duration in [("Write an Email", 11, "Write an Email", 420),
                                                            ("Write for an Academic Discussion", 12, "Write for an Academic Discussion", 600)]:
                        heading = re.search(rf"(?im)^\s*{re.escape(marker)}\s*$", text[:350])
                        if heading:
                            prompt_text = text[heading.end():].strip()
                            questions.append(dict(id=f"w1-{number:02d}", section="Writing", module=1,
                                                  number=number, page=page_no, type=qtype, stimulus="",
                                                  prompt=prompt_text, choices={},
                                                  answer="", transcript="", audio="", duration=duration))
            if sid == "reach120-2026":
                # The section headings fall at page boundaries in this PDF:
                # "Write an Email" is at the bottom of one page while its
                # prompt begins on the next. Parse the continuous document so
                # both open-response tasks retain their full prompts.
                document_text = "\n".join(pages)
                discussion_heading = document_text.rfind("Write for an Academic Discussion")
                email_heading = document_text.rfind("Write an Email", 0, discussion_heading)
                answer_heading = document_text.find("AFTER YOU FINISH", discussion_heading)
                if answer_heading < 0:
                    answer_heading = document_text.find("\nANSWERS\n", discussion_heading)
                if answer_heading < 0:
                    answer_heading = len(document_text)
                email = (document_text[email_heading + len("Write an Email"):discussion_heading].strip()
                         if email_heading >= 0 and discussion_heading > email_heading else "")
                discussion = (document_text[discussion_heading + len("Write for an Academic Discussion"):answer_heading].strip()
                              if discussion_heading >= 0 else "")
                for number, qtype, match, duration in [
                    (11, "Write an Email", email, 420),
                    (12, "Write for an Academic Discussion", discussion, 600),
                ]:
                    if match:
                        questions.append(dict(id=f"w1-{number:02d}", section="Writing", module=1,
                                              number=number, page=15, type=qtype, stimulus="",
                                              prompt=match, choices={}, answer="",
                                              transcript="", audio="", duration=duration))
        except Exception as exc:
            errors.append(f"PDF parse: {type(exc).__name__}: {exc}")
    # Remove duplicates caused by repeated page headings or duplicated PDF material.
    seen = set()
    unique = []
    for q in questions:
        if q["id"] not in seen:
            seen.add(q["id"])
            unique.append(q)
    questions = unique
    unmatched = map_audio(questions, assets)
    listening = [q for q in questions if q["section"] == "Listening"]
    speaking = [q for q in questions if q["section"] == "Speaking"]
    counts = {s: sum(q["section"] == s for q in questions) for s in ("Reading", "Listening", "Speaking", "Writing")}
    expected_full_mock = {"Reading": 40, "Listening": 34, "Speaking": 11, "Writing": 12}
    complete = counts == expected_full_mock and all(q["audio"] for q in listening + speaking)
    if all(counts.values()) and counts != expected_full_mock:
        errors.append(
            "NOT_FULL_LENGTH: section counts do not match the 2026 full-mock shape "
            f"{expected_full_mock}; imported as section practice only."
        )
    blocked_external = sid == "tstprep-2026" and not any(counts.values())
    if blocked_external:
        errors.append("BLOCKED_EXTERNAL_ACCESS: the complete test requires the provider's email/account flow; public sample audio and a writing rubric are not a complete question set.")
    synthetic_count = sum("/synthetic-" in x for x in assets)
    test = dict(id=sid, name=records[0]["test_name"], provider=records[0]["provider"],
                category=records[0]["category"], status="COMPLETE" if complete else "PARTIAL",
                sections=[s for s, n in counts.items() if n], questions=questions, audio_assets=assets,
                source_pdf="" if blocked_external else (pdfs[0]["local_filename"] if pdfs else ""),
                audio_notice="AI-GENERATED NEURAL AUDIO — NOT ORIGINAL TEST AUDIO" if synthetic_count else "")
    (TESTS / f"{sid}.json").write_text(json.dumps(test, ensure_ascii=False, indent=2), encoding="utf-8")
    report = dict(test_id=sid, status=test["status"], pages=len(pages), questions=counts,
                  external_access_status="BLOCKED_EXTERNAL_ACCESS" if blocked_external else "",
                  answer_keys=sum(bool(q["answer"]) for q in questions), audio_assets=len(assets),
                  synthetic_audio_assets=synthetic_count,
                  unmapped_audio_questions=unmatched, errors=errors,
                  source_failures=[r["source_url"] + " : " + r.get("error", "") for r in records
                                   if r["download_status"] not in ("DOWNLOADED", "GENERATED")])
    (REPORTS / f"{sid}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(sid, test["status"], counts, "audio", len(assets), "unmapped", len(unmatched), flush=True)
    return test


def main():
    manifest = json.loads((ROOT / "data/manifests/sources.json").read_text(encoding="utf-8"))
    grouped = defaultdict(list)
    for record in manifest:
        grouped[record["source_id"]].append(record)
    tests = [import_one(sid, records) for sid, records in grouped.items()]
    summary = dict(tests=len(tests), complete=sum(t["status"] == "COMPLETE" for t in tests),
                   partial=sum(t["status"] == "PARTIAL" for t in tests),
                   questions=sum(len(t["questions"]) for t in tests),
                   audio_assets=sum(len(t["audio_assets"]) for t in tests))
    (REPORTS / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("SUMMARY", summary, flush=True)


if __name__ == "__main__":
    main()
