"""Repair reading-task boundaries and OCR layout in the packaged question bank.

The source PDFs place the end of one task and the start of the next task on the
same page.  Earlier extraction therefore copied the Complete-the-Words passage
into questions 11 and 12, and sometimes left the final academic questions with
an empty stimulus.  This script makes those task boundaries explicit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "data" / "tests"
DAILY_MARKER = re.compile(r"Read (?:a|an) [^\n.]{1,80}[.:]", re.IGNORECASE)
CLOZE_PATTERN = re.compile(
    r"(?P<prefix>[A-Za-z]+)(?P<between>[ \t\r\n]*)"
    r"(?P<gap>_+(?:[ \t]*_+)*|-+(?:[ \t\r\n]*-+)*(?![ \t\r\n]*[A-Za-z]))"
    r"(?P<label>\d{1,2})?"
)


STUDENT_ONE_CLOZE = {
    1: (
        "We know from drawings that have been preserved in caves for over 10,000 years "
        "that early humans performed dances as a group activity. We mi___ think th__ "
        "prehistoric peo___ concentrated on__ on ba___ survival. How____, it i_ clear "
        "fr__ the rec___ that dan____ was important to them. They recorded more drawings "
        "of dances than of any other group activity. Dances served various purposes, "
        "including ritualistic communication with the divine, storytelling, and social cohesion."
    ),
    2: (
        "The human brain is a complex organ responsible for controlling all bodily functions, "
        "thought, emotion, and memory. It i_ divided in__ several reg____, each wi__ specific "
        "ro___. The cerebrum, i__ largest pa__, is invo____ in cogn_____ functions su__ as "
        "reasoning, language, and voluntary movement."
    ),
}

PREPDRILLS_CLOZE = {
    1: (
        "Coral reefs are among the most diverse ecosystems in the entire ocean. Although a reef "
        "looks like sto__, it is actually bui__ by millions of tiny animals called polyps. Each "
        "pol__ produces a hard skel____ that slowly joi__ with its neighbors. Over hund____ of "
        "years, these skeletons gr__ into vast reefs that shel___ many species. Warm, shallow "
        "wat___ suit them best, but even a small ri__ in temperature is dangerous. When the water "
        "grows too warm, the coral loses its color and turns a ghostly white, an effect known as bleaching."
    ),
    2: (
        "A volcano is an opening in the earth's surface through which molten rock can escape. Deep "
        "underground, intense heat mel__ rock into a thick liquid cal___ magma. Because magma is "
        "lig____ than the solid rock around it, it slowly ri___ toward the surf___. When the "
        "pres____ becomes too great, the magma bur___ out in a violent erup____. Rivers of glowing "
        "la__ then flow downhill and grad_____ cool into new rock. Although volcanoes can be "
        "extremely destructive, the ash they release also makes the surrounding soil remarkably fertile."
    ),
}

PREPDRILLS_DAILY = {
    1: {
        "11-12": (
            "Read a notice.\n\nRiverside Public Library\n\nBorrow e-books and audiobooks from home.\n\n"
            "Download the free Riverside Library app to browse and borrow thousands of e-books and "
            "audiobooks. Sign in with your library card number, choose a title, and it will download "
            "straight to your device. Titles return themselves automatically when they are due, so "
            "there are never any late fees."
        ),
        "13-15": (
            "Read a social media post.\n\nDaniel Cho\n\nIf you love books, our neighborhood's hidden "
            "gem, Corner Pages Books, is a must-visit! The shelves are packed with everything from new "
            "bestsellers to rare second-hand finds, and the staff always seem to know exactly what you'll "
            "enjoy.\n\nOn Friday evenings they host a free book club that's open to everyone—no need to "
            "sign up, just show up. There's also a small café at the back serving excellent coffee and "
            "homemade cake, so you can settle in for hours.\n\nBest of all, they run a ‘buy one, donate "
            "one’ scheme: for every book you buy, they give a used book to a local school. Support local "
            "and see you there!"
        ),
    },
    2: {
        "11-12": (
            "Read an email.\n\nTo: l.ferreira@dmail.com\nFrom: reservations@lakeviewinn.com\n"
            "Date: 02/10/2025\nSubject: Your Booking Confirmation\n\nDear Mr. Ferreira,\n\n"
            "Thank you for booking a room at the Lakeview Inn. Your stay is confirmed for the night of "
            "14 October, arriving any time after 3:00 PM. Breakfast is included and is served until "
            "10:00 AM.\n\nPlease note that our car park has limited space. If you plan to drive, let us "
            "know in advance so that we can reserve a space for you.\n\nKind regards,\nThe Lakeview Inn Team"
        ),
        "13-15": (
            "Read an email.\n\nTo: a.okafor@dmail.com\nFrom: membership@cityartmuseum.org\n"
            "Subject: Your invitation: Members' Evening at the City Art Museum\n\nDear Ms. Okafor,\n\n"
            "As a valued member, you're invited to our exclusive Members' Evening on Saturday, 21 "
            "October, from 6 to 9 PM. Be among the first to see our new exhibition of modern sculpture "
            "before it opens to the public.\n\nThe evening includes a guided tour, a talk by the curator, "
            "and light refreshments. You may bring one guest free of charge; additional guests are welcome "
            "for a small fee.\n\nPlease reply by 18 October so that we can confirm numbers. We look "
            "forward to seeing you.\n\nWarm regards,\nCity Art Museum Membership Team"
        ),
    },
}

PREPDRILLS_ACADEMIC_TWO = (
    "The Bilingual Brain\n\nFor much of the twentieth century, many educators believed that raising a "
    "child with two languages was harmful. They worried that the child would confuse the two systems and "
    "master neither. Today, research has overturned this view. Studies show that children who grow up "
    "bilingual reach the same language milestones as other children, and in some ways their thinking is "
    "sharper.\n\nOne reason is that a bilingual person's brain is constantly deciding which language to "
    "use and suppressing the other. This mental exercise appears to strengthen what psychologists call "
    "“executive function”—the ability to focus attention, ignore distractions, and switch between tasks. "
    "Some researchers have even found that lifelong bilingualism may delay the onset of certain age-related "
    "memory problems by several years.\n\nBilingualism is not without its challenges. Bilingual speakers "
    "sometimes have a slightly smaller vocabulary in each individual language, and they may take a moment "
    "longer to recall a specific word. For most people, however, the cognitive advantages are thought to "
    "outweigh these minor costs."
)


def compact(text: str) -> str:
    text = re.sub(r"Reading\s*[·,]?\s*Section?,?\s*Module\s*\d+", "", text, flags=re.I)
    text = re.sub(r"Reading\s*[·,]\s*Module\s*\d+", "", text, flags=re.I)
    return re.sub(r"[ \t]+\n", "\n", text).strip()


def repair_split_fragments(text: str) -> str:
    previous = None
    while text != previous:
        previous = text
        text = re.sub(r"\n([A-Za-z]{1,4})\n(?=[a-z])", r"\1", text)
    return text.replace("-\n", "-")


def clean_inline(text: str) -> str:
    text = re.sub(r"\s+", " ", repair_split_fragments(text)).strip()
    return text.replace("parag raph", "paragraph")


def clean_cloze(text: str, answers: list[str]) -> str:
    text = re.sub(r"\n([A-Za-z]{1,4})\n(?=[a-z])", r"\1", text)
    marker = re.search(r"Fill in the missing letters in the paragraph\.\s*\(Questions\s*1\s*[–-]\s*10\)", text, re.I)
    if marker:
        text = text[marker.end():]
    text = re.split(r"\bREAD IN DAILY LIFE\b", text, maxsplit=1, flags=re.I)[0]
    text = re.sub(r"\s+", " ", compact(text)).strip()
    matches = list(CLOZE_PATTERN.finditer(text))
    if len(matches) != len(answers):
        return text
    pieces: list[str] = []
    cursor = 0
    for match, answer in zip(matches, answers):
        pieces.append(text[cursor:match.start("gap")])
        pieces.append("_" * len(answer))
        cursor = match.end()
    pieces.append(text[cursor:])
    return "".join(pieces)


def clean_daily(text: str) -> str:
    matches = list(DAILY_MARKER.finditer(text))
    if matches:
        text = text[matches[-1].start():]
    return compact(text)


def clean_academic(text: str) -> str:
    text = compact(text)
    text = re.sub(r"^READ AN ACADEMIC PASSAGE\s*", "", text, flags=re.I)
    return text.strip()


def repair(path: Path) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "COMPLETE":
        return
    reading = [q for q in data["questions"] if q["section"] == "Reading"]
    for module in (1, 2):
        module_questions = sorted((q for q in reading if q["module"] == module), key=lambda q: q["number"])
        by_number = {q["number"]: q for q in module_questions}

        cloze = [by_number[n] for n in range(1, 11)]
        if data["id"] == "ets-student-1":
            cloze_text = STUDENT_ONE_CLOZE[module]
        elif data["id"] == "prepdrills-2026":
            cloze_text = PREPDRILLS_CLOZE[module]
        else:
            cloze_text = clean_cloze(cloze[0]["stimulus"], [q["answer"] for q in cloze])
        for question in cloze:
            question["type"] = "Complete the Words"
            question["stimulus"] = cloze_text

        daily_groups = ((11, 12), (13, 14, 15))
        for numbers in daily_groups:
            group = [by_number[n] for n in numbers]
            if data["id"] == "prepdrills-2026":
                daily_text = PREPDRILLS_DAILY[module]["11-12" if numbers[0] == 11 else "13-15"]
            else:
                candidates = [clean_daily(q["stimulus"]) for q in group if q["stimulus"].strip()]
                daily_text = max(candidates, key=len) if candidates else ""
            for question in group:
                question["type"] = "Read in Daily Life"
                question["stimulus"] = daily_text

        academic = [by_number[n] for n in range(16, 21)]
        if data["id"] == "prepdrills-2026" and module == 2:
            academic_text = PREPDRILLS_ACADEMIC_TWO
        else:
            candidates = [clean_academic(q["stimulus"]) for q in academic if q["stimulus"].strip()]
            academic_text = max(candidates, key=len) if candidates else ""
        for question in academic:
            question["type"] = "Read an Academic Passage"
            question["stimulus"] = academic_text

    if data["id"] == "prepdrills-2026":
        # Correct visible OCR debris in the affected questions and options.
        fixes = {
            (1, 16): ("What is the passage mainly about?", {"A": "How cities can save electricity", "B": "The dangers of air pollution", "C": "Why cities are warmer than nearby rural areas, and how this can be reduced", "D": "The best materials for constructing buildings"}),
            (1, 17): ('The word “considerably” in the first sentence is closest in meaning to', {"A": "equally", "B": "noticeably", "C": "rarely", "D": "suddenly"}),
            (2, 13): ("What is the main purpose of the email?", {"A": "To sell tickets to the general public", "B": "To invite a member to a preview event", "C": "To announce the opening of a new museum branch", "D": "To ask members for a donation"}),
            (2, 14): ("What can be inferred about Ms. Okafor?", {"A": "She is a member of the museum.", "B": "She works at the museum.", "C": "She is a professional sculptor.", "D": "She has already seen the new exhibition."}),
            (2, 15): ("How many guests can a member bring free of charge?", {"A": "None", "B": "As many as they wish", "C": "One", "D": "Two"}),
            (2, 19): ("According to the passage, all of the following are stated about bilingual speakers EXCEPT:", {"A": "They may have a slightly smaller vocabulary in each language.", "B": "Their executive function may be stronger.", "C": "They reach language milestones later than other children.", "D": "They may take a little longer to recall a specific word."}),
            (2, 20): ("Why does the author mention smaller vocabulary and slower word recall?", {"A": "To prove that bilingualism is harmful", "B": "To explain how human memory works", "C": "To acknowledge minor drawbacks while noting the benefits outweigh them", "D": "To encourage schools to teach in only one language"}),
        }
        for question in reading:
            fixed = fixes.get((question["module"], question["number"]))
            if fixed:
                question["prompt"], question["choices"] = fixed

    for question in reading:
        question["stimulus"] = repair_split_fragments(question["stimulus"])
        question["prompt"] = clean_inline(question["prompt"])
        question["choices"] = {key: clean_inline(value) for key, value in question["choices"].items()}

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    for path in sorted(TESTS.glob("*.json")):
        repair(path)


if __name__ == "__main__":
    main()
