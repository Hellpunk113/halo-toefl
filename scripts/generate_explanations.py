from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "by", "do", "does", "for", "from",
    "had", "has", "have", "he", "her", "his", "how", "i", "in", "is", "it", "its", "mainly",
    "most", "of", "on", "or", "she", "that", "the", "their", "they", "this", "to", "was", "were",
    "what", "when", "where", "which", "why", "will", "with", "woman", "man", "according", "passage",
    "conversation", "announcement", "talk", "speaker", "professor", "student", "following", "about",
}
WORD_EXPANSIONS = {
    "bank": {"account", "savings", "billing", "statement"},
    "cognition": {"awareness", "consciousness", "recognize", "animals"},
    "schedule": {"closed", "tomorrow", "time", "date", "rescheduled"},
    "worker": {"work", "office", "job"},
    "extended": {"prolonged", "longer", "lasting"},
    "volunteer": {"volunteers", "assist", "community"},
    "lecture": {"speaker", "auditorium", "present", "talk"},
}


def words(text: str) -> set[str]:
    return {w for w in re.findall(r"[A-Za-z][A-Za-z'-]{2,}", text.lower()) if w not in STOPWORDS}


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def excerpt(question: dict, correct_text: str) -> tuple[str, int]:
    if question["type"] == "Listen and Choose a Response" or (question["type"] == "Listening" and not clean(question.get("transcript", ""))):
        return clean(question.get("prompt", "")), 99
    source = clean(question.get("stimulus") or question.get("transcript") or question.get("prompt", ""))
    if not source:
        return "", 0
    if question["section"] == "Reading":
        markers = list(re.finditer(r"\bRead (?:a|an) (?:notice|email|announcement|advertisement|article|passage|poster|review|webpage)\.", source, re.I))
        if markers:
            source = source[markers[-1].start():]
    candidates = [s.strip() for s in re.split(r"(?<=[.!?])\s+|(?=(?:Woman|Man|Professor|Student|Host):)", source) if len(s.strip()) >= 8]
    if not candidates:
        candidates = [source]
    answer_words = words(correct_text)
    expanded = set(answer_words)
    for word in answer_words:
        expanded.update(WORD_EXPANSIONS.get(word, set()))
    prompt_words = words(question.get("prompt", ""))
    ranked = []
    for index, sentence in enumerate(candidates):
        sentence_words = words(sentence)
        exact = len(expanded & sentence_words)
        stem = sum(1 for a in expanded for s in sentence_words if len(a) >= 5 and len(s) >= 5 and a[:5] == s[:5])
        score = 4 * (exact + stem) + len(prompt_words & sentence_words)
        ranked.append((score, -index, sentence))
    best = max(ranked)
    result = best[2]
    return (result if len(result) <= 360 else result[:357].rstrip() + "…"), best[0]


def completed_word(question: dict) -> tuple[str, str, str]:
    pattern = re.compile(r"(?P<prefix>[A-Za-z]+)(?P<between>[ \t\r\n]*)(?P<gap>_+(?:[ \t]*_+)*|-+(?:[ \t\r\n]*-+)*(?![ \t\r\n]*[A-Za-z]))(?P<label>\d{1,2})?")
    matches = list(pattern.finditer(question.get("stimulus", "")))
    number_match = re.search(r"blank\s+(\d+)", question.get("prompt", ""), re.I)
    number = int(number_match.group(1)) if number_match else 1
    target = next((m for m in matches if m.group("label") and int(m.group("label")) == number), None)
    if target is None and 0 < number <= len(matches):
        target = matches[number - 1]
    prefix = target.group("prefix") if target else ""
    answer = question.get("answer", "")
    whole = answer if prefix and answer.lower().startswith(prefix.lower()) else prefix + answer
    return prefix, answer, whole


def explanation(question: dict) -> tuple[str, str]:
    qtype = question["type"]
    correct = question.get("answer", "")
    choices = question.get("choices", {})

    if choices and correct in choices:
        correct_text = clean(choices[correct])
        evidence, evidence_score = excerpt(question, correct_text)
        prompt_lower = question.get("prompt", "").lower()
        if qtype == "Listen and Choose a Response" or (qtype == "Listening" and not clean(question.get("transcript", ""))):
            zh = f"正確答案是 {correct}：「{correct_text}」說話者的話是：「{evidence}」這個選項能直接而合理地回應該問題或陳述；其他選項談到不同的時間、地點或行動。"
            en = f"The correct answer is {correct}: “{correct_text}” The speaker says, “{evidence}” This option responds directly and logically to that question or statement; the other choices shift to a different time, place, or action."
        elif " not " in f" {prompt_lower} " or "except" in prompt_lower:
            medium_zh = "逐字稿" if question["section"] == "Listening" else "文章"
            medium_en = "transcript" if question["section"] == "Listening" else "passage"
            zh = f"正確答案是 {correct}：「{correct_text}」這是一道反向題：{medium_zh}沒有把這個選項列為符合題意的內容，因此它是題目要求找出的「未提及／不正確」項目。相關內容可回看：「{evidence}」"
            en = f"The correct answer is {correct}: “{correct_text}” This is a negative question: the {medium_en} does not identify this choice as matching the requested condition, so it is the NOT/EXCEPT answer. Review the surrounding context: “{evidence}”"
        elif "closest in meaning" in prompt_lower:
            target_match = re.search(r"[“\"]([^”\"]+)[”\"]", question.get("prompt", ""))
            target = target_match.group(1) if target_match else "the highlighted expression"
            zh = f"正確答案是 {correct}：「{correct_text}」「{target}」在此處的意思與「{correct_text}」最接近；代回原句後，句意和詞性都保持一致。"
            en = f"The correct answer is {correct}: “{correct_text}” In this context, “{target}” is closest in meaning to “{correct_text}.” Substituting it preserves both the meaning and grammatical role of the original sentence."
        elif evidence:
            medium_zh = "逐字稿" if question["section"] == "Listening" else "文章"
            medium_en = "transcript" if question["section"] == "Listening" else "passage"
            if evidence_score:
                zh = f"正確答案是 {correct}：「{correct_text}」{medium_zh}中的關鍵依據是：「{evidence}」這段內容最能支持正確選項；其他選項與材料的重點、細節或說話目的不符。"
                en = f"The correct answer is {correct}: “{correct_text}” The key evidence in the {medium_en} is: “{evidence}” This best supports the correct choice; the other choices do not match the main point, detail, or speaker purpose in the source."
            else:
                zh = f"正確答案是 {correct}：「{correct_text}」請把此選項與{medium_zh}的相關脈絡對照：「{evidence}」正確選項概括或推論了材料的意思，而不是逐字重複原文。"
                en = f"The correct answer is {correct}: “{correct_text}” Compare the choice with the relevant {medium_en} context: “{evidence}” The correct option summarizes or infers the source meaning rather than repeating its exact words."
        else:
            zh = f"正確答案是 {correct}：「{correct_text}」此選項最符合題幹和材料提供的資訊；其他選項加入了材料未支持的內容，或偏離題目所問的重點。"
            en = f"The correct answer is {correct}: “{correct_text}” This choice best matches the question and the information provided; the other choices add unsupported information or miss the point being asked."
        return zh, en

    if qtype == "Complete the Words":
        prefix, missing, whole = completed_word(question)
        zh = f"此空應填入「{missing}」，完整單字是「{whole}」。空格前已有「{prefix}」；補上缺少的字母後，單字的拼字、詞性和句意都能與上下文銜接。"
        en = f"Enter “{missing}”; the completed word is “{whole}.” The letters “{prefix}” are already given. Adding the missing letters produces a correctly spelled word whose form and meaning fit the sentence."
        return zh, en

    if qtype == "Build a Sentence":
        zh = f"正確句序是：「{correct}」先確定主詞和主要動詞，再把關係子句、受詞或修飾語放到它所修飾的成分旁；最後檢查時態、主動詞一致和句末標點。"
        en = f"The correct sentence is: “{correct}” Identify the subject and main verb first, then place each relative clause, object, or modifier next to the element it describes. Finally, check tense, subject–verb agreement, and punctuation."
        return zh, en

    if qtype == "Write an Email":
        zh = "這是開放式寫作題，沒有唯一標準答案。檢討時請確認：收件人和語氣合宜、題目列出的每一項要求都有回應、理由或細節具體、段落連貫，並檢查文法、拼字和結尾格式。"
        en = "This is an open-response task with no single model answer. Check that the recipient and tone are appropriate, every requested point is addressed, reasons or details are specific, ideas are organized, and grammar, spelling, and the closing are accurate."
        return zh, en

    if qtype == "Write for an Academic Discussion":
        zh = "這是開放式寫作題，沒有唯一標準答案。有效回答應清楚表明立場，以理由和具體例子支持觀點，回應教授或同學的內容，加入自己的分析，並保持組織、文法和用字清楚。"
        en = "This is an open-response task with no single model answer. An effective response states a clear position, supports it with reasons and concrete examples, engages with the professor or classmates, adds original analysis, and maintains clear organization, grammar, and word choice."
        return zh, en

    if qtype == "Listen and Repeat":
        prompt = clean(question.get("prompt", ""))
        zh = f"目標句是：「{prompt}」檢討錄音時，確認內容沒有漏字或改變原意，重音落在關鍵詞，語調和停頓自然，子音與字尾清楚，並在不中斷流暢度的情況下完整複誦。"
        en = f"Target sentence: “{prompt}” When reviewing the recording, check that no words or meaning were lost, key words received appropriate stress, intonation and pauses sounded natural, consonants and endings were clear, and the full sentence was repeated fluently."
        return zh, en

    if qtype == "Take an Interview":
        zh = "這是開放式口說題，沒有唯一標準答案。回答應先直接回應問題，再補充理由、經驗或例子；檢討時注意內容是否具體、組織是否清楚，以及發音、語速、停頓和文法是否影響理解。"
        en = "This is an open-response speaking task with no single model answer. Answer the question directly, then add a reason, experience, or example. During review, check specificity and organization as well as whether pronunciation, pace, pauses, or grammar interfere with understanding."
        return zh, en

    answer = clean(correct) or "open response"
    zh = f"參考答案為：「{answer}」請依題目要求檢查內容是否完整、資訊是否正確，以及語言表達是否清楚。"
    en = f"Reference answer: “{answer}” Check whether the response fully addresses the task, presents accurate information, and communicates clearly."
    return zh, en


def main() -> None:
    items = []
    for path in sorted((ROOT / "data" / "tests").glob("*.json")):
        test = json.loads(path.read_text(encoding="utf-8"))
        for question in test["questions"]:
            zh, en = explanation(question)
            items.append({"test_id": test["id"], "question_id": question["id"], "zh": zh, "en": en})
    output = {"version": 1, "generator": "HALO TOEFL bilingual explanation generator", "items": items}
    target = ROOT / "data" / "explanations.json"
    target.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(items)} bilingual explanations: {target}")


if __name__ == "__main__":
    main()
