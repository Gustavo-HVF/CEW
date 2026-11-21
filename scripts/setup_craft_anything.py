#!/usr/bin/env python3
"""Setup do CEW: clona e compila o Craft Anything, roda o doctor, liga o Ghidra e testa o Gemini.

Equivale a `cew setup`. Opcoes: --ssh | --https, --com-app, --sem-craft, --dry-run.
A implementacao fica em cew/setup_craft.py (ver docs/DECISOES.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cew.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["setup", *sys.argv[1:]]))
