#!/usr/bin/env python3
"""Build one Chan book with Honkit.

Usage:
  python3 tools/book-kit/build_honkit.py book1-chan-foundation

The script intentionally stays small: it validates the book folder and then
delegates rendering to `npx honkit build`, so the book remains compatible with
the same per-book shape used by harness-books.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: build_honkit.py <book-dir>", file=sys.stderr)
        return 2

    repo = Path(__file__).resolve().parents[2]
    book = (repo / sys.argv[1]).resolve()

    if not book.exists() or not book.is_dir():
        print(f"Book directory not found: {book}", file=sys.stderr)
        return 2

    for required in ["book.json", "SUMMARY.md", "index.md"]:
        if not (book / required).exists():
            print(f"Missing {required} in {book}", file=sys.stderr)
            return 2

    return subprocess.call(["npx", "honkit", "build", str(book)], cwd=str(repo))


if __name__ == "__main__":
    raise SystemExit(main())
