"""Caminhos do repositorio e normalizacao entre Windows, macOS e Linux.

Regras:
- caminhos gravados em JSON usam "/" e Unicode NFC (o macOS entrega nomes em NFD; sem
  normalizar, o mesmo arquivo teria ids diferentes em cada sistema);
- caminhos dentro de conteiners usam "!/" como separador: "dados/fase.szs!/arc/modelo.brres".
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from pathlib import Path, PurePosixPath

SEPARADOR_CONTEINER = "!/"


def raiz_repositorio() -> Path:
    """Raiz do repositorio CEW (a pasta que contem schemas/ e formats/).

    Pode ser trocada com a variavel CEW_RAIZ (usada nos testes).
    """
    env = os.environ.get("CEW_RAIZ")
    if env:
        return Path(env).resolve()
    aqui = Path(__file__).resolve().parent.parent
    return aqui


def pasta_projetos() -> Path:
    env = os.environ.get("CEW_PROJETOS")
    if env:
        return Path(env).resolve()
    return raiz_repositorio() / "projects"


def nfc(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


def relativo_posix(caminho: Path, base: Path) -> str:
    """Caminho relativo com "/" e NFC. Lanca ValueError se `caminho` nao esta dentro de `base`."""
    rel = Path(os.path.relpath(Path(caminho).resolve(), Path(base).resolve()))
    if rel.parts and rel.parts[0] == "..":
        raise ValueError(f"{caminho} esta fora de {base}")
    return nfc(PurePosixPath(*rel.parts).as_posix())


def juntar_conteiner(pai: str, filho: str) -> str:
    return f"{pai}{SEPARADOR_CONTEINER}{nfc(filho)}"


def id_estavel(prefixo: str, *partes: str, tamanho: int = 16) -> str:
    """Id deterministico: o mesmo caminho de origem gera sempre o mesmo id (item 5.4)."""
    h = hashlib.sha256("\x1f".join(nfc(p) for p in partes).encode("utf-8")).hexdigest()
    return f"{prefixo}_{h[:tamanho]}"


_NAO_SEGURO = re.compile(r"[^a-z0-9._-]+")


def slug(nome: str, limite: int = 48) -> str:
    """Nome seguro para a web: minusculas, sem acentos, sem espacos."""
    base = unicodedata.normalize("NFKD", nome)
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = _NAO_SEGURO.sub("-", base).strip("-.")
    return (base or "arquivo")[:limite]


def nome_projeto_valido(nome: str) -> str:
    s = slug(nome, 64)
    if not s:
        raise ValueError("nome de projeto vazio")
    return s


def dentro_de(caminho: Path, base: Path) -> bool:
    try:
        Path(caminho).resolve().relative_to(Path(base).resolve())
        return True
    except ValueError:
        return False


def destino_seguro(base: Path, relativo: str) -> Path:
    """Junta `relativo` a `base` recusando caminhos absolutos e "..", contra "zip slip"."""
    rel = relativo.replace("\\", "/")
    partes = [p for p in rel.split("/") if p not in ("", ".")]
    if any(p == ".." for p in partes) or re.match(r"^[A-Za-z]:", rel) or rel.startswith("/"):
        raise ValueError(f"caminho inseguro dentro do conteiner: {relativo!r}")
    destino = Path(base, *partes) if partes else Path(base)
    if not dentro_de(destino, base):
        raise ValueError(f"caminho inseguro dentro do conteiner: {relativo!r}")
    return destino
