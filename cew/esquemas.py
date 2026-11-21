"""Validacao JSON Schema (draft 2020-12) de todo arquivo trocado entre etapas.

Todo JSON do CEW e validado antes de gravar e depois de ler (item 5.1). Os esquemas ficam em
schemas/ e se referenciam por $id (https://cew.local/schemas/...).
"""

from __future__ import annotations

import json
import os
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import raiz_repositorio

PREFIXO_ID = "https://cew.local/schemas/"


class ErroEsquema(ValueError):
    def __init__(self, esquema: str, erros: list[str], origem: str = ""):
        self.esquema = esquema
        self.erros = erros
        onde = f" ({origem})" if origem else ""
        resumo = "; ".join(erros[:5]) + (" ..." if len(erros) > 5 else "")
        super().__init__(f"JSON invalido para {esquema}{onde}: {resumo}")


def pasta_esquemas() -> Path:
    return raiz_repositorio() / "schemas"


@lru_cache(maxsize=1)
def _registro() -> tuple[Registry, dict[str, dict]]:
    pasta = pasta_esquemas()
    recursos = []
    por_nome: dict[str, dict] = {}
    for arq in sorted(pasta.rglob("*.schema.json")):
        doc = json.loads(arq.read_text(encoding="utf-8"))
        rel = arq.relative_to(pasta).as_posix()
        esperado = PREFIXO_ID + rel
        if doc.get("$id") != esperado:
            raise RuntimeError(f"{arq}: $id deve ser {esperado}")
        Draft202012Validator.check_schema(doc)
        recursos.append((esperado, Resource.from_contents(doc)))
        por_nome[rel.removesuffix(".schema.json")] = doc
    return Registry().with_resources(recursos), por_nome


def limpar_cache() -> None:
    _registro.cache_clear()


def nomes_esquemas() -> list[str]:
    return sorted(_registro()[1])


def esquema(nome: str) -> dict:
    """`nome` sem extensao, relativo a schemas/: 'inventario', 'gemini/resposta_formato'."""
    _, por_nome = _registro()
    if nome not in por_nome:
        raise KeyError(f"esquema desconhecido: {nome}")
    return por_nome[nome]


def erros(dados: Any, nome: str) -> list[str]:
    registro, _ = _registro()
    v = Draft202012Validator(esquema(nome), registry=registro, format_checker=FormatChecker())
    saida = []
    for e in sorted(v.iter_errors(dados), key=lambda e: list(e.absolute_path)):
        caminho = "/".join(str(p) for p in e.absolute_path) or "(raiz)"
        saida.append(f"{caminho}: {e.message}")
    return saida


def validar(dados: Any, nome: str, origem: str = "") -> None:
    lista = erros(dados, nome)
    if lista:
        raise ErroEsquema(nome, lista, origem)


def cabecalho(dados: dict) -> dict:
    """Garante schema_version e gerado_por no topo (item 5.1), sem sobrescrever valores."""
    saida = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR}
    saida.update(dados)
    return saida


def dump(dados: Any) -> str:
    """JSON deterministico: chaves na ordem dada, UTF-8 sem escapes, fim de linha unico."""
    return json.dumps(dados, ensure_ascii=False, indent=2) + "\n"


def gravar_json(caminho: Path, dados: Any, nome_esquema: str | None) -> Path:
    """Valida e grava de forma atomica (arquivo temporario + replace)."""
    if nome_esquema:
        validar(dados, nome_esquema, str(caminho))
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=caminho.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(dump(dados))
        os.replace(tmp, caminho)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return caminho


def ler_json(caminho: Path, nome_esquema: str | None) -> Any:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    if nome_esquema:
        validar(dados, nome_esquema, str(caminho))
    return dados
