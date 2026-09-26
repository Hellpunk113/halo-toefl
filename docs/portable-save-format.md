# HALO TOEFL portable save format

Extension: `.halo-save`  
Container: ZIP  
Current schema version: `1`

The format uses UTF-8 JSON and relative POSIX paths so it can be read on Windows, macOS, or Linux. A save contains:

- `manifest.json`: format identifier, schema version, creation time, counts, and SHA-256 of `progress.json`.
- `progress.json`: test and question snapshots, bilingual explanations, every attempt, section and question timers, selected answers, writing responses, and portable speaking-recording metadata.
- `recordings/...`: available speaking recordings, stored with relative paths and individual SHA-256 values.

The stable format identifier is `halo-toefl-portable-save`. Importers must reject an unsupported version, a mismatched `progress.json` hash, unsafe paths, and recording hash mismatches.

Attempt UUIDs are stable identities. Importing the same archive more than once skips an attempt UUID already present and never overwrites its answers. If a referenced test is unavailable, the archive's question and explanation snapshots can be inserted as an `IMPORTED_ARCHIVE` test so historical review remains readable.

Absolute paths from the source computer are never stored for speaking recordings. Importers extract recordings under their own application data folder and update the corresponding saved response to the new local path.
