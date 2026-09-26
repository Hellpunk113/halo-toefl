"""Small release gate for packaged content and cross-platform data paths."""

from __future__ import annotations

import os
import tempfile

from halo.db import Store


def main():
    os.environ["HALO_VOCAB_DATA"] = tempfile.mkdtemp(prefix="halo-release-")
    store = Store()
    values = {
        "tests": store.db.execute("SELECT COUNT(*) FROM tests").fetchone()[0],
        "complete": store.db.execute("SELECT COUNT(*) FROM tests WHERE status='COMPLETE'").fetchone()[0],
        "questions": store.db.execute("SELECT COUNT(*) FROM questions").fetchone()[0],
        "explanations": store.db.execute("SELECT COUNT(*) FROM question_explanations").fetchone()[0],
    }
    store.db.close()
    print(values)
    assert values == {"tests": 11, "complete": 10, "questions": 940, "explanations": 940}


if __name__ == "__main__":
    main()
