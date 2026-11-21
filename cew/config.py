"""Leitura de config/*.json e do .env (sem dependencias externas)."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any

from .caminhos import raiz_repositorio
from .esquemas import ler_json


def config_gemini() -> dict[str, Any]:
    return ler_json(raiz_repositorio() / "config" / "gemini.json", "config_gemini")


def config_versoes() -> dict[str, Any]:
    return ler_json(raiz_repositorio() / "config" / "versoes.json", "config_versoes")


def ler_env(caminho: Path | None = None) -> dict[str, str]:
    """Le um .env simples: NOME=valor, linhas com # sao comentarios, aspas opcionais."""
    caminho = caminho or (raiz_repositorio() / ".env")
    valores: dict[str, str] = {}
    if not caminho.is_file():
        return valores
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, _, valor = linha.partition("=")
        nome = nome.strip()
        if nome.startswith("export "):
            nome = nome[7:].strip()
        valor = valor.strip()
        if len(valor) >= 2 and valor[0] == valor[-1] and valor[0] in "\"'":
            valor = valor[1:-1]
        valores[nome] = valor
    return valores


def carregar_env(caminho: Path | None = None) -> None:
    """Copia o .env para os.environ sem sobrescrever o que ja veio do ambiente."""
    for nome, valor in ler_env(caminho).items():
        if valor and not os.environ.get(nome):
            os.environ[nome] = valor


def salvar_no_env(nome: str, valor: str, caminho: Path | None = None) -> Path:
    """Grava/atualiza NOME=valor no .env com permissao restrita (0600 onde o sistema permite)."""
    caminho = caminho or (raiz_repositorio() / ".env")
    linhas = caminho.read_text(encoding="utf-8").splitlines() if caminho.is_file() else []
    novas, trocou = [], False
    for linha in linhas:
        if linha.split("=", 1)[0].strip() == nome:
            novas.append(f"{nome}={valor}")
            trocou = True
        else:
            novas.append(linha)
    if not trocou:
        novas.append(f"{nome}={valor}")
    caminho.write_text("\n".join(novas) + "\n", encoding="utf-8")
    try:
        os.chmod(caminho, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
    return caminho
