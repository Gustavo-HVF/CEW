#!/usr/bin/env python3
"""Orquestrador do CEW (o mesmo que o comando `cew`).

Funciona sem instalar: `python scripts/orchestrator.py run --projeto meu-jogo --alvo <caminho>`.
A logica fica no pacote cew/ (cew/cli.py) para poder ser empacotada como o comando `cew`
via pyproject.toml; este arquivo so a chama. Ver docs/DECISOES.md.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cew.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
