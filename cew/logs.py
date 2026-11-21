"""Logs em JSON Lines (logs/<area>/<data>.jsonl) com nivel, etapa e id do item.

Toda linha passa por `redigir`, que troca qualquer ocorrencia da chave do Gemini (e de chaves
com cara de chave de API do Google) por "[REDIGIDO]" antes de chegar ao disco.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from .caminhos import raiz_repositorio

_PADRAO_CHAVE_GOOGLE = re.compile(r"AIza[0-9A-Za-z_\-]{30,}")
_NIVEIS = {"debug": 10, "info": 20, "aviso": 30, "erro": 40}


def _segredos() -> list[str]:
    valores = []
    for nome in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
        v = os.environ.get(nome, "").strip()
        if len(v) >= 8:
            valores.append(v)
    return valores


def redigir(texto: str) -> str:
    for s in _segredos():
        texto = texto.replace(s, "[REDIGIDO]")
    return _PADRAO_CHAVE_GOOGLE.sub("[REDIGIDO]", texto)


def redigir_obj(obj: Any) -> Any:
    return json.loads(redigir(json.dumps(obj, ensure_ascii=False)))


def agora_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def pasta_logs() -> Path:
    env = os.environ.get("CEW_LOGS")
    return Path(env) if env else raiz_repositorio() / "logs"


class Log:
    def __init__(self, area: str = "cew", nivel_minimo: str | None = None, eco: bool = False):
        self.area = area
        self.minimo = _NIVEIS.get((nivel_minimo or os.environ.get("CEW_LOG_NIVEL", "info")).lower(), 20)
        self.eco = eco

    def arquivo(self) -> Path:
        dia = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        return pasta_logs() / self.area / f"{dia}.jsonl"

    def registrar(self, nivel: str, mensagem: str, etapa: str | None = None, item: str | None = None, **extra: Any) -> None:
        if _NIVEIS.get(nivel, 20) < self.minimo:
            return
        linha = {"ts": agora_iso(), "nivel": nivel, "area": self.area, "etapa": etapa, "item": item, "mensagem": mensagem}
        if extra:
            linha["dados"] = extra
        texto = redigir(json.dumps(linha, ensure_ascii=False, default=str))
        arq = self.arquivo()
        arq.parent.mkdir(parents=True, exist_ok=True)
        with open(arq, "a", encoding="utf-8", newline="\n") as f:
            f.write(texto + "\n")
        if self.eco or nivel in ("aviso", "erro"):
            print(redigir(f"[{nivel}] {mensagem}"), file=sys.stderr)

    def debug(self, m: str, **k: Any) -> None:
        self.registrar("debug", m, **k)

    def info(self, m: str, **k: Any) -> None:
        self.registrar("info", m, **k)

    def aviso(self, m: str, **k: Any) -> None:
        self.registrar("aviso", m, **k)

    def erro(self, m: str, **k: Any) -> None:
        self.registrar("erro", m, **k)
