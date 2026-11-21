"""Esqueleto comum dos conversores: --help, --dry-run, saida em JSON validado.

Cada conversor define INFO e `converter(entrada, escritor, opcoes) -> dict | None` e chama
`executar(INFO, converter)` no __main__. O resultado segue schemas/conversor_resultado.schema.json.

Em --dry-run o conversor le e decodifica a entrada normalmente (para falhar cedo em arquivo
corrompido), mas nada e gravado: o resultado lista o que seria gravado.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path
from typing import Any, Callable

from .binario import ErroFormato

LIMITE_ENTRADA_PADRAO = 1024 * 1024 * 1024  # 1 GiB


def _destino_seguro(base: Path, relativo: str) -> Path:
    rel = relativo.replace("\\", "/")
    partes = [p for p in rel.split("/") if p not in ("", ".")]
    if not partes or any(p == ".." for p in partes) or rel.startswith("/") or (len(rel) > 1 and rel[1] == ":"):
        raise ErroFormato(f"caminho de saida inseguro: {relativo!r}")
    destino = Path(base, *partes)
    try:
        destino.resolve().relative_to(Path(base).resolve())
    except ValueError as e:
        raise ErroFormato(f"caminho de saida inseguro: {relativo!r}") from e
    return destino


class Escritor:
    def __init__(self, pasta: Path, dry_run: bool):
        self.pasta = Path(pasta)
        self.dry_run = dry_run
        self.saidas: list[dict[str, Any]] = []
        self.avisos: list[str] = []
        self._nomes: set[str] = set()

    def gravar(self, relativo: str, dados: bytes, tipo: str, formato: str, metadados: dict | None = None) -> dict:
        destino = _destino_seguro(self.pasta, relativo)
        chave = relativo.replace("\\", "/").lower()
        if chave in self._nomes:
            raise ErroFormato(f"saida duplicada: {relativo}")
        self._nomes.add(chave)
        if not self.dry_run:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
        item: dict[str, Any] = {
            "caminho": relativo.replace("\\", "/"),
            "tipo": tipo,
            "formato": formato,
            "sha256": hashlib.sha256(dados).hexdigest(),
            "tamanho_bytes": len(dados),
        }
        if metadados:
            item["metadados"] = metadados
        self.saidas.append(item)
        return item

    def avisar(self, texto: str) -> None:
        self.avisos.append(texto)


def ler_entrada(caminho: Path, limite: int = LIMITE_ENTRADA_PADRAO) -> bytes:
    caminho = Path(caminho)
    tam = caminho.stat().st_size
    if tam > limite:
        raise ErroFormato(f"entrada com {tam} bytes passa do limite de {limite}")
    return caminho.read_bytes()


def rodar(info: dict, funcao: Callable[[bytes, Escritor, dict], dict | None], entrada: Path, saida: Path, opcoes: dict | None = None, dry_run: bool = False) -> dict:
    """Executa um conversor como funcao (usado pelo orquestrador, pelo MCP e pelos testes)."""
    opcoes = opcoes or {}
    entrada = Path(entrada)
    dados = ler_entrada(entrada)
    esc = Escritor(Path(saida), dry_run)
    resultado: dict[str, Any] = {
        "schema_version": "1.0",
        "gerado_por": "cew-conversor",
        "conversor": info["arquivo"],
        "versao_conversor": info.get("versao", "1.0"),
        "entrada": {"caminho": entrada.name, "sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados)},
        "dry_run": dry_run,
        "ok": True,
        "erro": None,
        "saidas": [],
        "avisos": [],
    }
    try:
        extra = funcao(dados, esc, opcoes) or {}
        if extra:
            resultado["estatisticas"] = extra
    except ErroFormato as e:
        resultado["ok"] = False
        resultado["erro"] = str(e)
    except (struct.error, IndexError, KeyError, ValueError, OverflowError, UnicodeError, ZeroDivisionError) as e:
        # rede de seguranca: arquivo corrompido nunca derruba o orquestrador; o texto marca o bug
        resultado["ok"] = False
        resultado["erro"] = f"falha inesperada (bug do conversor, leitura sem conferencia): {type(e).__name__}: {e}"
    resultado["saidas"] = esc.saidas
    resultado["avisos"] = esc.avisos
    _validar(resultado)
    return resultado


def _validar(resultado: dict) -> None:
    try:
        from cew.esquemas import validar  # import tardio: conversores tambem rodam sozinhos
    except Exception:  # pragma: no cover - sem o pacote cew, pula a validacao
        return
    validar(resultado, "conversor_resultado")


def executar(info: dict, funcao: Callable[[bytes, Escritor, dict], dict | None], argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog=info["arquivo"],
        description=f"{info['descricao']}\nEntrada: {', '.join(info['formatos_entrada'])} -> {info['destino']}",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=info.get("epilogo", ""),
    )
    p.add_argument("entrada", type=Path, help="arquivo de entrada")
    p.add_argument("-o", "--saida", type=Path, default=None, help="pasta de saida (padrao: <entrada>.cew/)")
    p.add_argument("--opcoes", default="{}", help="opcoes em JSON, ex.: '{\"escala\": 0.0254}'")
    p.add_argument("--dry-run", action="store_true", help="le e decodifica, mas nao grava nada")
    p.add_argument("--json-resultado", type=Path, default=None, help="grava o resultado (JSON) neste arquivo tambem")
    a = p.parse_args(argv)
    try:
        opcoes = json.loads(a.opcoes)
        if not isinstance(opcoes, dict):
            raise ValueError("--opcoes deve ser um objeto JSON")
    except ValueError as e:
        p.error(str(e))
    if not a.entrada.is_file():
        p.error(f"entrada nao encontrada: {a.entrada}")
    saida = a.saida or a.entrada.with_name(a.entrada.name + ".cew")
    r = rodar(info, funcao, a.entrada, saida, opcoes, a.dry_run)
    texto = json.dumps(r, ensure_ascii=False, indent=2)
    if a.json_resultado and not a.dry_run:
        a.json_resultado.parent.mkdir(parents=True, exist_ok=True)
        a.json_resultado.write_text(texto + "\n", encoding="utf-8")
    sys.stdout.write(texto + "\n")
    return 0 if r["ok"] else 1

