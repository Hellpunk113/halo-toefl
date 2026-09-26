# HALO TOEFL 1.0.0

**公益免費的本地新托福模考軟體，誓死消滅淘寶上動輒賣八九十塊錢的黑心商家，後續題庫會持續更新。**

HALO TOEFL is a Windows and macOS TOEFL mock-exam application for the 2026 format, distributed only for internal beta testing within Halo Education Research. It downloads public source material using `scripts/fetch_resources.py`, imports it using `scripts/import_tests.py`, and uses SQLite for attempts, answers, recordings, writing recovery, and daily activity.

The exam screen uses TOEFL-style split layouts: Reading places the passage on the left and the question on the right, while Listening and Speaking place a contextual speaker illustration on the left and the task on the right. Complete-the-Words answers are entered directly in the active blank and are limited to the printed blank length. Question text and answer cards are sized for high-DPI displays, and the test library is vertically scrollable. The exam header includes an Exit Test control that saves the current answer and timer state before returning to the library. Each library card shows cumulative completion as a percentage and answered-question count; an unfinished test can be resumed from its card.

Before a test begins, the user can enable or disable countdowns. The section limits are Reading 30 minutes, Listening 29 minutes, Writing 23 minutes, and Speaking 8 minutes. Objective items also have practice pacing timers: Complete the Words 30 seconds, Read in Daily Life and Build a Sentence 60 seconds, Read an Academic Passage 75 seconds, Listen and Choose a Response 20 seconds, and the other Listening choice types 35–40 seconds. A Listening item timer waits until its audio has finished. These item allocations are a HALO TOEFL practice feature; they are not presented as official ETS per-item limits.

## Run from source

Use Python 3.12+:

```powershell
python scripts/fetch_resources.py
python scripts/import_tests.py
python scripts/generate_neural_audio.py
python scripts/import_tests.py
python main.py
```

## Build on Windows

```powershell
python -m PyInstaller --noconfirm --clean HALO-TOEFL-Windows.spec
```

## Build on macOS

```bash
python3 -m pip install -r requirements.txt
python3 -m PyInstaller --noconfirm --clean HaloTOEFL-macOS.spec
mkdir -p dmg
cp -R "dist/HALO TOEFL.app" dmg/
ln -s /Applications dmg/Applications
hdiutil create -volname "HALO TOEFL" -srcfolder dmg -ov -format UDZO "dist/HALO-TOEFL-macOS.dmg"
```

The macOS package is unsigned. The GitHub Actions workflow builds both desktop packages on their native operating systems and attaches them to a release when a `v*` tag is pushed.

The application stores personal data under `%LOCALAPPDATA%\HALO TOEFL` on Windows and `~/Library/Application Support/HALO TOEFL` on macOS. Set `HALO_VOCAB_DATA` before launch to choose another local data folder.

## Releases

Download the Windows EXE or macOS DMG from the repository's Releases page. A `.halo-save` archive exported on one platform can be imported on the other without replacing previous attempts.

## Source status

The current import contains ten complete mocks: seven official ETS tests plus the Exambooster, PrepDrills, and Reach120 third-party sets. Third-party transcript-only items use role-aware male/female neural voices and are visibly labelled `AI-GENERATED NEURAL AUDIO — NOT ORIGINAL TEST AUDIO`. TST Prep remains partial because its complete question set requires the provider's external email/account flow; its public sample audio is preserved but is not presented as a mock. See `reports/import-validation/` for source-specific results.

Generated speech input is sanitized before synthesis so PDF page markers, page numbers, provider footers, section labels, and promotional copy are never spoken.

The packaged build includes twelve original offline campus illustrations. Every supported Listening and Speaking visual category has a three-image pool, chosen deterministically from the test, task type, and question ID so the illustrations rotate across items while remaining stable when a learner returns to the same item.

All 940 questions include offline Taiwan Traditional Chinese and English practice explanations. They are locked while an attempt is in progress and become available only from the review screen after the whole attempt is completed. Choice explanations identify the complete correct option and cite relevant passage or transcript context; word completion and sentence building show the reconstructed answer; Writing and Speaking provide task-specific review criteria. The displayed explanation follows the selected interface language.

## Portable saves and attempt history

Settings can export and import a cross-platform `.halo-save` archive. It contains every independent attempt, per-question selections, Writing responses, timers, available Speaking recordings, question snapshots, and bilingual explanation snapshots. The ZIP-based UTF-8 format uses relative paths and integrity hashes so a future macOS build can read the same archive. Importing the same archive again skips existing attempt UUIDs and never overwrites answers. See `docs/portable-save-format.md` for the versioned format.

Each test keeps every attempt separately as Attempt 1, Attempt 2, and so on. Its library card opens a history screen with completion, status, date, section, Resume for unfinished work, and Review for completed work.

Settings also contains an irreversible local-data reset. It requires the exact text `ACCESS`, followed by a second warning confirmation, before attempts, answers, timers, writing, Speaking recordings, and imported archive snapshots are deleted.

HALO TOEFL is not affiliated with or endorsed by ETS.
