"""Download public source files; preserve originals and record every outcome."""
from __future__ import annotations

import concurrent.futures
import hashlib
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "resources" / "raw"
MANIFEST = ROOT / "data" / "manifests" / "sources.json"
RAW.mkdir(parents=True, exist_ok=True)
MANIFEST.parent.mkdir(parents=True, exist_ok=True)
ETS_PAGE = "https://www.ets.org/toefl/teachers-advisors-agents/ibt/teaching/preparing-students.html"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) HALO-TOEFL/1.0"}


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            if d.get("href"):
                self.links.append(d["href"])


def links(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as r:
        html = r.read().decode("utf-8", "replace")
    parser = Links()
    parser.feed(html)
    return [urllib.parse.urljoin(url, x) for x in parser.links]


def embedded_media(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=35) as response:
        html = response.read().decode("utf-8", "replace")
    found = re.findall(r"https?://[^\"'<>\s]+", html, re.I)
    found.extend(urllib.parse.urljoin(url, x) for x in re.findall(r"(?:src|href)=[\"']([^\"']+)", html, re.I))
    return [x.replace("&amp;", "&") for x in found if re.search(r"(?:\.mp3|\.wav|\.m4a|/audio)(?:\?|$)", x, re.I)]


def source_list():
    ets = links(ETS_PAGE)
    # Names in the public ETS page uniquely identify student/teacher test assets.
    for group, stem, count in [("student", "student-practice-test", 2),
                                ("teacher", "teacher-practice-test", 5)]:
        for i in range(1, count + 1):
            sid = f"ets-{group}-{i}"
            test = f"ETS {'Practice' if group == 'student' else 'Teacher Practice'} Test {i}"
            pdf_guess = (f"https://www.ets.org/content/dam/ets-org/pdfs/toefl/"
                         f"toefl-ibt-{'full-length' if group == 'student' else 'teachers-resources'}-practice-test-{i}.pdf")
            pdf = next((x for x in ets if x.endswith(f"{'full-length' if group == 'student' else 'teachers-resources'}-practice-test-{i}.pdf")), pdf_guess)
            if group == "student":
                audio_guess = f"https://www.ets.org/content/dam/ets-org/pdfs/toefl/student-practice-test-{i}-audio-files.zip"
            else:
                audio_guess = f"https://www.ets.org/content/dam/ets-org/pdfs/toefl/teacher-practice-test-{i}-audio-file.zip"
            audio = next((x for x in ets if re.search(rf"{stem}-{i}-audio", x, re.I) and x.lower().endswith(".zip")), audio_guess)
            yield sid, test, "ETS", "OFFICIAL_ETS", "PDF", pdf
            yield sid, test, "ETS", "OFFICIAL_ETS", "AUDIO_ZIP", audio
    yield "exambooster-demo", "Exambooster 2026 Demo Question Bank", "Exambooster", "THIRD_PARTY", "PDF", "https://toefl.exambooster.ru/content/toefl-demo/demo-toefl-tests.pdf"
    yield "reach120-2026", "Reach120 2026 Section Practice", "Reach120", "THIRD_PARTY", "PDF", "https://www.reach120.com/downloads/pdf/toefl-2026-practice-test-answer-key.pdf"
    for url, sid, test, provider in [
        ("https://www.reach120.com/downloads/toefl-practice-test", "reach120-2026", "Reach120 2026 Section Practice", "Reach120"),
        ("https://tstprep.com/articles/toefl/complete-practice-test-for-the-toefl-test/", "tstprep-2026", "TST Prep 2026 Samples", "TST Prep"),
        ("https://prepdrills.com/toefl-practice-test/", "prepdrills-2026", "PrepDrills 2026 Test", "PrepDrills")]:
        try:
            found = links(url)
            candidates = [x for x in found if re.search(r"\.pdf(?:\?|$)|\.mp3(?:\?|$)|\.zip(?:\?|$)", x, re.I)]
            if provider == "Reach120":
                candidates.extend(embedded_media(url))
            for x in dict.fromkeys(candidates):
                if "toefl" in x.lower() or provider == "Reach120":
                    kind = "PDF" if ".pdf" in x.lower() else "AUDIO"
                    yield sid, test, provider, "THIRD_PARTY", kind, x
        except Exception as exc:
            yield sid, test, provider, "THIRD_PARTY", "PAGE_ERROR", f"{url} | {exc}"


def download(item):
    sid, test, provider, category, kind, url = item
    basename = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
    if basename.lower() == "audio":
        basename = Path(urllib.parse.urlparse(url).path).parent.name + ".mp3"
    if not basename:
        basename = "resource.bin"
    local = f"{sid}__{basename}"
    target = RAW / local
    result = dict(source_id=sid, test_name=test, provider=provider, category=category,
                  source_type=kind, source_url=url, local_filename=local,
                  download_timestamp=datetime.now(timezone.utc).isoformat(),
                  file_size=0, SHA256="", download_status="FAILED", error="")
    if kind == "PAGE_ERROR":
        result["error"] = url
        return result
    try:
        if not target.exists():
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=60) as response, target.open("wb") as out:
                while chunk := response.read(1024 * 1024):
                    out.write(chunk)
        data = target.read_bytes()
        if kind == "PDF" and not data.startswith(b"%PDF"):
            raise ValueError("Response is not a PDF")
        if kind == "AUDIO_ZIP" and not data.startswith(b"PK"):
            raise ValueError("Response is not a ZIP")
        result.update(file_size=len(data), SHA256=hashlib.sha256(data).hexdigest(), download_status="DOWNLOADED")
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        if target.exists() and target.stat().st_size == 0:
            target.unlink()
    return result


def main():
    preserved = []
    if MANIFEST.exists():
        preserved = [r for r in json.loads(MANIFEST.read_text(encoding="utf-8"))
                     if r.get("source_type") == "SYNTHETIC_AUDIO"]
    items = list(dict.fromkeys(source_list()))
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(download, items))
    records.extend(preserved)
    MANIFEST.write_text(json.dumps(records, indent=2, ensure_ascii=False), encoding="utf-8")
    for r in records:
        print(r["download_status"], r["source_id"], r["source_type"], r["local_filename"], r["error"], flush=True)
    print("MANIFEST", MANIFEST, flush=True)


if __name__ == "__main__":
    main()
