# HALO TOEFL 1.0.0 acceptance test

Date: 2026-09-26

| Check | Result | Evidence |
|---|---|---|
| Source manifest | PASS | `data/manifests/sources.json` contains public downloads and 110 generated neural-audio records with hashes, voice metadata, and explicit AI-audio labels. |
| Import pipeline | PASS | `reports/import-validation/summary.json`: 11 source records, 10 complete mocks, 1 partial source, 940 questions, 423 audio assets. |
| Official ETS tests | PASS | Seven ETS tests contain Reading, Listening, Writing, and Speaking; required Listening and Speaking audio paths are mapped to original ETS files. |
| Third-party conversion | PASS | Exambooster: 119 questions; PrepDrills: 97; Reach120: 46. Transcript-only audio uses role-aware male/female neural voices and is labelled `AI-GENERATED NEURAL AUDIO — NOT ORIGINAL TEST AUDIO` in the library. |
| Neural audio quality | PASS | All 110 MP3 files decoded successfully; six US English neural voices were used and total generated audio is 40.59 minutes. A transcript audit found no PDF page markers, page numbers, provider footers, or promotional copy in speech input. |
| Reading split layout | PASS | A live Tk UI test measured the Reading passage and answer panes at 562 px and 555 px; the passage is scrollable on the left and the question remains on the right. |
| Inline word completion | PASS | ETS suffix answers and full-word third-party keys were tested. Input occurs inside the active passage blank, rejects alphabetic input beyond the blank length, and saves the answer in the format required by its source key. |
| Optional countdown | PASS | The pre-test screen offers countdown on/off. Section timers use 30/29/23/8 minutes for Reading/Listening/Writing/Speaking and persist remaining time in SQLite across navigation and resume. |
| Per-question practice countdown | PASS | All objective Reading, Listening, and Build-a-Sentence types receive a type-specific 20–75 second item timer when countdown is enabled. Listening item time pauses while its audio is playing, auto-advances at zero, and persists in `attempt_question_timers`. |
| Scrollable test library | PASS | A live 200% DPI UI test moved the library canvas from `(0.0, 0.5936)` to `(0.4064, 1.0)`, confirming all installed tests can be reached by wheel or scrollbar. |
| Exit and resume | PASS | The exam header exposes `退出測驗`. A live attempt selected answer A and exited; the answer and timer state were saved, the attempt remained `IN_PROGRESS`, and `繼續作答` appeared on that test's library card. |
| Per-test completion | PASS | Each library card shows cumulative non-empty distinct answers across non-discarded attempts as a percentage and fraction. A one-answer fixture correctly rendered `完成度 1% · 1/97 題已完成`. |
| Bilingual answer explanations | PASS | `data/explanations.json` and packaged SQLite contain non-empty Taiwan Traditional Chinese and English explanations for all 940 questions. Live review renders the Chinese or English version according to the interface language. |
| Explanation access control | PASS | Calling review for an `IN_PROGRESS` attempt displayed `解析尚未開放`; after the attempt became `COMPLETE`, the same review displayed the answer key and per-question explanation. |
| Portable save round trip | PASS | Two independent attempts, answers, a question timer, and a Speaking recording were exported to `.halo-save` and imported into a fresh data directory. Attempt IDs, answer choices, bilingual explanations, and the remapped recording were preserved. |
| Non-destructive duplicate import | PASS | Reimporting the same archive imported 0 attempts and skipped the 2 existing UUIDs; no saved answer was overwritten or duplicated. |
| Multiple attempt history | PASS | A live test created two attempts under one test. The library rendered `作答紀錄 (2)`, and its history rendered separate `第 1 次` and `第 2 次` cards with their own status and completion. |
| Protected local reset | PASS | Incorrect `access` and a declined second confirmation both preserved two attempts. Exact `ACCESS` followed by the final confirmation removed all attempts and recordings while retaining the eleven installed test sources. |
| Internal beta distribution label | PASS | The home subtitle now reads `2026 格式 · 僅在Halo教研企業內測分發`. |
| Larger answer controls | PASS | Choice rows use 15-point text, a 22-point empty/filled selection marker, a full-row click target, keyboard selection, and a highlighted selected state. |
| Listening and Speaking visuals | PASS | Twelve original offline illustrations are packaged. Seven supported visual task categories each expose a deterministic three-image pool; a live Listening render showed one image in the left pane and choices in the right pane. See `reports/exam-visual-qa.png`. |
| Compact header subtitle | PASS | The descriptive text next to `HALO TOEFL` uses a 10-point font, leaving more room for the library and exam controls. |
| Choice-boundary cleanup | PASS | All 940 imported questions were audited; no choice contains a following passage, provider footer, page marker, promotional block, missing choice, or empty choice. |
| TST Prep access handling | PASS | The validation report records `BLOCKED_EXTERNAL_ACCESS`; 22 public sample audio files are preserved, but no mock is fabricated without the gated question set. |
| Automatic scoring | PASS | A temporary ETS Reading attempt submitted three known correct answers; all three were scored correctly and an estimated 1–6 practice score was produced. |
| SQLite persistence | PASS | Source and packaged launches created an on-disk database; the packaged database contained 11 tests, 10 complete, 1 partial, including all 119 Exambooster questions. |
| Content migration | PASS | A stale Reach120 question was inserted into an older persistent database; packaged launch removed it and restored the authoritative 46-question set while leaving user attempt tables intact. |
| Daily exports | PASS | PDF, CSV, JSON, and ZIP reports were generated and checked as non-empty files. |
| Microphone recording | PASS | A selected Windows input device produced a 16 kHz WAV with 16,000 frames and non-zero peak level. |
| Recording export | PASS | The recorded WAV was converted to MP3 and archived to ZIP; both outputs were checked as non-empty. |
| Audio playback | PASS | Pygame initialized the Windows output path, decoded the recorded WAV, played it, and stopped cleanly. |
| Packaged application | PASS | `dist/HALO-TOEFL.exe` launched for 18 seconds; its responding main window title was `HALO TOEFL`. |
| Bilingual interface | PASS | Non-question UI defaults to 台灣正體 and can switch to English; imported exam content is kept in its source language. |
| Home navigation | PASS | The home screen calls the header with `show_home_button=False`; interior screens retain the Home button. |
| High DPI text rendering | PASS | Windows Per Monitor DPI Awareness detected the test display at 192 DPI (200% scaling), Tk rendering used 192 DPI rather than the former virtualized 96 DPI, and Taiwan Traditional Chinese uses Microsoft JhengHei UI. `reports/font-render-qa.png` confirms crisp native-size rendering. |

Packaged executable SHA-256: `ae710159595523f5da56cfe68fc56cfc65e7dfda032844c9e1be712d5cf05e3f`

The three third-party mocks use neural audio only where the source supplies a transcript but no publicly downloadable original audio. The seven official ETS tests never substitute generated audio for supplied ETS audio.
