"""Generate role-aware neural practice audio with Microsoft Edge voices.

This is a build-time tool. Generated MP3 files are bundled for offline playback;
HALO TOEFL does not need the service or edge-tts at run time.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "resources" / "audio"
TESTS = ROOT / "data" / "tests"
PROCESSED = ROOT / "resources" / "processed"
MANIFEST = ROOT / "data" / "manifests" / "sources.json"
CACHE = ROOT / ".pyinstaller-cache" / "neural-segments"
EDGE_SITE = ROOT / ".pyinstaller-cache" / "edge-tts"
sys.path.insert(0, str(EDGE_SITE))

import edge_tts  # noqa: E402
import imageio_ffmpeg  # noqa: E402


FEMALE_VOICES = ["en-US-AvaNeural", "en-US-EmmaNeural", "en-US-AriaNeural"]
MALE_VOICES = ["en-US-AndrewNeural", "en-US-BrianNeural", "en-US-ChristopherNeural"]
ROLE_PATTERN = re.compile(
    r"(?ms)(Woman|Man|Female Student|Male Student|Student|Professor|Advisor|Technician|"
    r"Podcast Host|Host|Speaker|Interviewer|Trainer):\s*(.*?)(?=(?:Woman|Man|Female Student|"
    r"Male Student|Student|Professor|Advisor|Technician|Podcast Host|Host|Speaker|"
    r"Interviewer|Trainer):|\Z)"
)


def normalize(text: str) -> str:
    """Remove PDF furniture before any text is sent to the speech service."""
    text = text.replace("\ufeff", " ")
    text = re.sub(r"(?im)^\s*\d+\s*===\s*PAGE\s*===\s*$", "", text)
    text = re.sub(r"(?im)^\s*===\s*PAGE\s*===\s*$", "", text)
    text = re.sub(r"(?im)^\s*Вариант\s+\d+\s*·.*$", "", text)
    text = re.sub(r"(?im)^\s*Reach120\s*·.*$", "", text)
    text = re.sub(r"(?im)^\s*(?:TOEFL\s+2026\s*·\s*ExamBooster.*|\d+\s*/\s*\d+)\s*$", "", text)
    text = re.sub(r"(?is)Practice speaking with .*?Start free\s*→\s*toefl\.prepdrills\.com.*$", "", text)
    text = re.sub(r"(?is)\s+Reach120\s*·\s*complete\s+2026\s+practice\s+test.*$", "", text)
    text = re.sub(r"(?im)^\s*(?:Section\s+\d+\s*,\s*(?:Reading|Listening|Writing|Speaking)|\d{1,2})\s*$", "", text)
    text = re.sub(r"\s+", " ", text).strip(" ·|_=")
    text = re.sub(r"\s+(?:[1-9]|[1-3]\d|4[0-2])$", "", text).strip()
    return text


def prep_group_transcripts() -> dict[tuple[int, int], str]:
    text = (PROCESSED / "prepdrills-2026.txt").read_text(encoding="utf-8")
    section = text.split("SECTION 2 OF 4", 1)[1].split("SECTION 3 OF 4", 1)[0]
    parts = re.split(r"Listening · Module\s*(\d+)", section)
    result: dict[tuple[int, int], str] = {}
    for index in range(1, len(parts), 2):
        module = int(parts[index])
        matches = re.findall(
            r"(?ims)^Listen to .+?questions\s+(\d+)[–-](\d+)\.\s*(.*?)(?=^\s*\d{1,2}\.)",
            parts[index + 1],
        )
        for start, end, transcript in matches:
            transcript = normalize(transcript)
            for number in range(int(start), int(end) + 1):
                result[(module, number)] = transcript
    return result


def voice_for(role: str, ordinal: int, qtype: str) -> tuple[str, str, str]:
    role_lower = role.lower()
    if role_lower in {"woman", "female student"}:
        female = True
    elif role_lower in {"man", "male student", "advisor", "technician"}:
        female = False
    elif role_lower in {"professor", "speaker", "host", "podcast host", "interviewer", "trainer"}:
        female = ordinal % 2 == 0
    else:  # Unspecified students alternate naturally inside a conversation.
        female = ordinal % 2 == 0
    voices = FEMALE_VOICES if female else MALE_VOICES
    voice = voices[ordinal % len(voices)]
    if "Academic" in qtype:
        rate = "-7%"
    elif "Interview" in qtype or "Conversation" in qtype:
        rate = "-3%"
    else:
        rate = "-1%"
    pitch = "+2Hz" if female else "-2Hz"
    return voice, rate, pitch


def segments(text: str, qtype: str, seed: int) -> list[dict[str, str]]:
    matches = list(ROLE_PATTERN.finditer(text))
    if matches:
        result = []
        role_counts: dict[str, int] = {}
        for index, match in enumerate(matches):
            role, spoken = match.group(1), normalize(match.group(2))
            if not spoken:
                continue
            role_counts.setdefault(role, len(role_counts))
            voice, rate, pitch = voice_for(role, seed + role_counts[role], qtype)
            result.append(dict(text=spoken, voice=voice, rate=rate, pitch=pitch))
        if result:
            return result
    voice, rate, pitch = voice_for("Speaker", seed, qtype)
    return [dict(text=normalize(text), voice=voice, rate=rate, pitch=pitch)]


def make_jobs() -> list[dict]:
    groups = prep_group_transcripts()
    jobs = []
    for sid in ("prepdrills-2026", "reach120-2026", "exambooster-demo"):
        test = json.loads((TESTS / f"{sid}.json").read_text(encoding="utf-8"))
        for question in test["questions"]:
            if question["section"] not in ("Listening", "Speaking"):
                continue
            if sid == "reach120-2026" and question["section"] == "Listening":
                continue
            text = question["prompt"]
            if sid == "prepdrills-2026" and question["section"] == "Listening":
                text = groups.get((question["module"], question["number"]), text)
            elif sid == "exambooster-demo" and question["section"] == "Listening":
                text = question["transcript"]
            jobs.append(dict(source_id=sid, question_id=question["id"], qtype=question["type"],
                             output=AUDIO / sid / f"synthetic-{question['id']}.mp3",
                             segments=segments(text, question["type"], question["number"])))
    return jobs


async def create_segment(segment: dict, semaphore: asyncio.Semaphore) -> Path:
    key = hashlib.sha256(json.dumps(segment, sort_keys=True).encode()).hexdigest()
    target = CACHE / f"{key}.mp3"
    if target.exists() and target.stat().st_size > 1000:
        return target
    async with semaphore:
        for attempt in range(4):
            try:
                await edge_tts.Communicate(segment["text"], segment["voice"],
                                           rate=segment["rate"], pitch=segment["pitch"]).save(str(target))
                if target.stat().st_size <= 1000:
                    raise RuntimeError("empty neural audio")
                return target
            except Exception:
                if target.exists():
                    target.unlink()
                if attempt == 3:
                    raise
                await asyncio.sleep(1.5 * (attempt + 1))
    return target


def join_segments(paths: list[Path], target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if len(paths) == 1:
        shutil.copy2(paths[0], target)
        return
    with tempfile.TemporaryDirectory(prefix="halo-neural-") as temp:
        listing = Path(temp) / "segments.txt"
        listing.write_text("\n".join(f"file '{str(path).replace("'", "'\\''")}'" for path in paths),
                           encoding="utf-8")
        subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error",
                        "-f", "concat", "-safe", "0", "-i", str(listing),
                        "-codec:a", "libmp3lame", "-q:a", "3", str(target)],
                       check=True, timeout=180)


async def generate(jobs: list[dict]) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(4)
    unique = {}
    for job in jobs:
        for segment in job["segments"]:
            key = json.dumps(segment, sort_keys=True)
            unique[key] = segment
    generated = await asyncio.gather(*(create_segment(segment, semaphore) for segment in unique.values()))
    cache_paths = dict(zip(unique, generated))
    audio_cache: dict[str, Path] = {}
    for index, job in enumerate(jobs, 1):
        signature = hashlib.sha256(json.dumps(job["segments"], sort_keys=True).encode()).hexdigest()
        if signature in audio_cache:
            shutil.copy2(audio_cache[signature], job["output"])
        else:
            join_segments([cache_paths[json.dumps(segment, sort_keys=True)] for segment in job["segments"]],
                          job["output"])
            audio_cache[signature] = job["output"]
        print(f"[{index:03d}/{len(jobs)}] {job['source_id']} {job['question_id']}", flush=True)


def update_manifest(jobs: list[dict]) -> None:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    targets = {(job["source_id"], job["question_id"]) for job in jobs}
    records = [record for record in records if not (
        record.get("source_type") == "SYNTHETIC_AUDIO" and
        (record.get("source_id"), record.get("source_url", "").rsplit("/", 1)[-1]) in targets)]
    names = {"prepdrills-2026": ("PrepDrills 2026 Test", "PrepDrills"),
             "reach120-2026": ("Reach120 2026 Complete Test", "Reach120"),
             "exambooster-demo": ("Exambooster 2026 Demo", "Exambooster")}
    now = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        path = job["output"]
        data = path.read_bytes()
        test_name, provider = names[job["source_id"]]
        voices = sorted({segment["voice"] for segment in job["segments"]})
        records.append(dict(source_id=job["source_id"], test_name=test_name, provider=provider,
                            category="SYNTHETIC_AUDIO", source_type="SYNTHETIC_AUDIO",
                            source_url=f"local-neural-tts://{job['source_id']}/{job['question_id']}",
                            local_filename=str(path.relative_to(ROOT)).replace("\\", "/"),
                            download_timestamp=now, file_size=len(data),
                            SHA256=hashlib.sha256(data).hexdigest(), download_status="GENERATED",
                            error="AI-GENERATED NEURAL AUDIO — NOT ORIGINAL TEST AUDIO; voices=" + ",".join(voices)))
    MANIFEST.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    jobs = make_jobs()
    asyncio.run(generate(jobs))
    update_manifest(jobs)
    print(f"Generated {len(jobs)} role-aware neural audio assets.")


if __name__ == "__main__":
    main()
