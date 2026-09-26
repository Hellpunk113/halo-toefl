"""Generate clearly labelled local TTS audio for third-party transcript-only tests."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "resources" / "audio"
TESTS = ROOT / "data" / "tests"
PROCESSED = ROOT / "resources" / "processed"
MANIFEST = ROOT / "data" / "manifests" / "sources.json"


def spoken(text: str) -> str:
    text = re.sub(r"\b(?:Woman|Man|Professor|Podcast Host|Speaker|Trainer|Interviewer):\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def prep_group_transcripts() -> dict[tuple[int, int], str]:
    text = (PROCESSED / "prepdrills-2026.txt").read_text(encoding="utf-8")
    section = text.split("SECTION 2 OF 4", 1)[1].split("SECTION 3 OF 4", 1)[0]
    parts = re.split(r"Listening · Module\s*(\d+)", section)
    result: dict[tuple[int, int], str] = {}
    for index in range(1, len(parts), 2):
        module = int(parts[index])
        body = parts[index + 1]
        matches = re.findall(
            r"(?ims)^Listen to .+?questions\s+(\d+)[–-](\d+)\.\s*(.*?)(?=^\s*\d{1,2}\.)",
            body,
        )
        for start, end, transcript in matches:
            cleaned = spoken(transcript)
            for number in range(int(start), int(end) + 1):
                result[(module, number)] = cleaned
    return result


def make_jobs() -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    groups = prep_group_transcripts()
    for sid in ("prepdrills-2026", "reach120-2026", "exambooster-demo"):
        data = json.loads((TESTS / f"{sid}.json").read_text(encoding="utf-8"))
        for question in data["questions"]:
            if question["section"] not in ("Listening", "Speaking"):
                continue
            if sid == "reach120-2026" and question["section"] == "Listening":
                continue  # Reach120 provides its original public Listening audio.
            text = question["prompt"]
            if sid == "prepdrills-2026" and question["section"] == "Listening":
                text = groups.get((question["module"], question["number"]), text)
            elif sid == "exambooster-demo" and question["section"] == "Listening":
                text = question["transcript"]
            text = spoken(text)
            if not text:
                raise ValueError(f"No TTS transcript for {sid} {question['id']}")
            path = AUDIO / sid / f"synthetic-{question['id']}.wav"
            jobs.append({"source_id": sid, "question_id": question["id"],
                         "text": text, "path": str(path.resolve())})
    return jobs


def synthesize(jobs: list[dict[str, str]]) -> None:
    pending = [job for job in jobs if not Path(job["path"]).exists()]
    if not pending:
        return
    for job in pending:
        Path(job["path"]).parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="halo-tts-") as temp:
        temp_dir = Path(temp)
        jobs_path = temp_dir / "jobs.json"
        script_path = temp_dir / "synthesize.ps1"
        jobs_path.write_text(json.dumps(pending, ensure_ascii=False), encoding="utf-8-sig")
        script_path.write_text(
            "param([string]$JobsPath)\n"
            "Add-Type -AssemblyName System.Speech\n"
            "$jobs = Get-Content -LiteralPath $JobsPath -Raw -Encoding UTF8 | ConvertFrom-Json\n"
            "$voice = New-Object System.Speech.Synthesis.SpeechSynthesizer\n"
            "$voice.Rate = 0\n"
            "foreach ($job in $jobs) {\n"
            "  $voice.SetOutputToWaveFile($job.path)\n"
            "  $voice.Speak([string]$job.text)\n"
            "  $voice.SetOutputToNull()\n"
            "}\n"
            "$voice.Dispose()\n",
            encoding="utf-8-sig",
        )
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(script_path), "-JobsPath", str(jobs_path)], check=True, timeout=600)


def update_manifest(jobs: list[dict[str, str]]) -> None:
    records = json.loads(MANIFEST.read_text(encoding="utf-8"))
    target_ids = {job["source_id"] for job in jobs}
    records = [record for record in records
               if not (record.get("source_type") == "SYNTHETIC_AUDIO"
                       and record.get("source_id") in target_ids)]
    names = {"prepdrills-2026": ("PrepDrills 2026 Test", "PrepDrills"),
             "reach120-2026": ("Reach120 2026 Complete Test", "Reach120"),
             "exambooster-demo": ("Exambooster 2026 Demo", "Exambooster")}
    now = datetime.now(timezone.utc).isoformat()
    for job in jobs:
        path = Path(job["path"])
        data = path.read_bytes()
        test_name, provider = names[job["source_id"]]
        records.append(dict(source_id=job["source_id"], test_name=test_name, provider=provider,
                            category="SYNTHETIC_AUDIO", source_type="SYNTHETIC_AUDIO",
                            source_url=f"local-tts://{job['source_id']}/{job['question_id']}",
                            local_filename=str(path.relative_to(ROOT)).replace("\\", "/"),
                            download_timestamp=now, file_size=len(data),
                            SHA256=hashlib.sha256(data).hexdigest(), download_status="GENERATED",
                            error="SYNTHETIC AUDIO — NOT ORIGINAL TEST AUDIO"))
    MANIFEST.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    jobs = make_jobs()
    synthesize(jobs)
    update_manifest(jobs)
    print(f"Generated/verified {len(jobs)} clearly labelled synthetic audio assets.")


if __name__ == "__main__":
    main()
