"""Catalogo dos conversores em converters/ e execucao padronizada."""

from __future__ import annotations

import importlib
from functools import lru_cache
from pathlib import Path
from typing import Any

from .caminhos import raiz_repositorio


def modulo_de(caminho_rel: str) -> str:
    """'converters/nintendo/u8_to_dir.py' -> 'converters.nintendo.u8_to_dir' (so dentro de converters/)."""
    p = caminho_rel.replace("\\", "/")
    if not p.startswith("converters/") or not p.endswith(".py") or ".." in p.split("/"):
        raise ValueError(f"conversor fora de converters/: {caminho_rel}")
    return p[:-3].replace("/", ".")


def carregar(caminho_rel: str):
    mod = importlib.import_module(modulo_de(caminho_rel))
    if not hasattr(mod, "INFO") or not hasattr(mod, "converter"):
        raise ValueError(f"{caminho_rel} nao define INFO e converter()")
    return mod


@lru_cache(maxsize=1)
def listar() -> list[dict[str, Any]]:
    raiz = raiz_repositorio()
    saida = []
    for arq in sorted((raiz / "converters").glob("*/*.py")):
        if arq.parent.name == "comum" or arq.name == "__init__.py":
            continue
        rel = arq.relative_to(raiz).as_posix()
        mod = carregar(rel)
        saida.append(dict(mod.INFO))
    return saida


def rodar(caminho_rel: str, entrada: Path, saida: Path, opcoes: dict | None = None, dry_run: bool = False) -> dict:
    from converters.comum.cli import rodar as _rodar

    mod = carregar(caminho_rel)
    return _rodar(mod.INFO, mod.converter, Path(entrada), Path(saida), opcoes or {}, dry_run)


def papel(caminho_rel: str) -> str:
    return carregar(caminho_rel).INFO.get("papel", "conversor")
