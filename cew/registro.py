"""Registro de formatos (formats/registry.json) e identificacao em camadas (item 4.3).

Ordem: assinatura (magic bytes) -> extensao -> estrutura (tamanhos/offsets) -> contexto (quem
carrega o arquivo, pelo Ghidra/Craft Anything) -> hipotese do Gemini. O resultado registra qual
camada decidiu e a confianca.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from . import estruturas
from .caminhos import raiz_repositorio
from .esquemas import ler_json

TAM_CABECA = 64 * 1024
TAM_CAUDA = 64


@dataclass
class Identificacao:
    id: str | None
    camada: str
    confianca: float
    empresa_ou_motor: str | None = None
    tipo: str | None = None
    candidatos: list[str] = field(default_factory=list)
    evidencia: str = ""

    def para_json(self) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "empresa_ou_motor": self.empresa_ou_motor, "tipo": self.tipo, "camada": self.camada, "confianca": round(self.confianca, 3)}
        if self.candidatos:
            d["candidatos"] = self.candidatos
        if self.evidencia:
            d["evidencia"] = self.evidencia
        return d


class Registro:
    def __init__(self, dados: dict):
        self.dados = dados
        self.formatos: list[dict] = dados["formatos"]
        self.por_id = {f["id"]: f for f in self.formatos}

    @classmethod
    def carregar(cls, caminho: Path | None = None) -> "Registro":
        return cls(ler_json(caminho or raiz_repositorio() / "formats" / "registry.json", "registry"))

    def get(self, formato_id: str | None) -> dict | None:
        return self.por_id.get(formato_id) if formato_id else None

    # ------------------------------------------------------------------------- camadas
    @staticmethod
    def _casa(assinatura: dict, cabeca: bytes, cauda: bytes, tamanho: int) -> bool:
        alvo = bytes.fromhex(assinatura["bytes_hex"])
        off = assinatura["offset"]
        if off >= 0:
            return cabeca[off : off + len(alvo)] == alvo
        # offset negativo: relativo ao fim (cauda tem os ultimos TAM_CAUDA bytes)
        ini = len(cauda) + off
        if ini < 0 or tamanho < -off:
            return False
        return cauda[ini : ini + len(alvo)] == alvo

    def _assinaturas(self, f: dict) -> list[dict]:
        lista = [f["assinatura"]] if f.get("assinatura") else []
        return lista + list(f.get("assinaturas_alternativas", []))

    def _ident(self, f: dict, camada: str, conf: float, candidatos: list[str], evid: str) -> Identificacao:
        return Identificacao(f["id"], camada, conf, f["empresa_ou_motor"], f["tipo"], [c for c in candidatos if c != f["id"]], evid)

    def identificar(self, cabeca: bytes, cauda: bytes, tamanho: int, nome: str) -> Identificacao:
        ext = "".join(PurePosixPath(nome.lower()).suffixes[-2:]) if nome else ""
        ext_simples = PurePosixPath(nome.lower()).suffix if nome else ""

        def tem_ext(f: dict) -> bool:
            return ext_simples in f["extensoes"] or (ext and ext in f["extensoes"])

        # 1) assinatura
        por_assinatura = [f for f in self.formatos if any(self._casa(a, cabeca, cauda, tamanho) for a in self._assinaturas(f))]
        if por_assinatura:
            # assinaturas mais longas sao mais especificas ("J3D2bmd3" vence "RIFF")
            def comprimento(f: dict) -> int:
                return max(len(a["bytes_hex"]) for a in self._assinaturas(f) if self._casa(a, cabeca, cauda, tamanho))

            por_assinatura.sort(key=comprimento, reverse=True)
            ids = [f["id"] for f in por_assinatura]
            resultados = [(f, estruturas.verificar(f.get("verificador_estrutura"), cabeca, cauda, tamanho)) for f in por_assinatura]
            confirmados = [f for f, ok in resultados if ok is True]
            neutros = [f for f, ok in resultados if ok is None]
            if len(confirmados) == 1:
                camada = "estrutura" if len(por_assinatura) > 1 else "assinatura"
                return self._ident(confirmados[0], camada, 0.95, ids, f"assinatura + estrutura ({confirmados[0]['verificador_estrutura']})")
            if len(confirmados) > 1:
                com_ext = [f for f in confirmados if tem_ext(f)]
                if len(com_ext) == 1:
                    return self._ident(com_ext[0], "extensao", 0.85, ids, "assinatura e estrutura empatadas; extensao desempatou")
                return self._ident(confirmados[0], "assinatura", 0.5, ids, "varios formatos com a mesma assinatura e estrutura coerente")
            if neutros:
                maior = comprimento(neutros[0])
                melhores = [f for f in neutros if comprimento(f) == maior]
                if len(melhores) > 1:
                    com_ext = [f for f in melhores if tem_ext(f)]
                    if len(com_ext) == 1:
                        return self._ident(com_ext[0], "extensao", 0.85, ids, "assinatura empatada; extensao desempatou")
                    return self._ident(melhores[0], "assinatura", 0.5, ids, "assinatura compartilhada por varios formatos")
                conf = 0.9 if maior >= 8 else 0.75  # >= 4 bytes de assinatura
                return self._ident(melhores[0], "assinatura", conf, ids, f"assinatura de {maior // 2} bytes")
            # todos os verificadores rejeitaram: segue para extensao, sem confiar na assinatura
        # 2) extensao, 3) estrutura
        por_ext = [f for f in self.formatos if tem_ext(f)]
        ids_ext = [f["id"] for f in por_ext]
        estrutura_ok = []
        so_ext = []
        for f in por_ext:
            if self._assinaturas(f):
                continue  # tem assinatura e ela nao casou: a estrutura sozinha nao confirma
            ok = estruturas.verificar(f.get("verificador_estrutura"), cabeca, cauda, tamanho)
            if ok is True:
                estrutura_ok.append(f)
            elif ok is None:
                so_ext.append(f)
        if len(estrutura_ok) == 1:
            return self._ident(estrutura_ok[0], "estrutura", 0.8, ids_ext, f"extensao + estrutura ({estrutura_ok[0]['verificador_estrutura']})")
        if estrutura_ok:
            return self._ident(estrutura_ok[0], "estrutura", 0.55, ids_ext, "extensao + estrutura, com empate")
        if so_ext:
            return self._ident(so_ext[0], "extensao", 0.4 if len(so_ext) == 1 else 0.25, ids_ext, "so a extensao (formato sem assinatura)")
        if por_ext:
            f = por_ext[0]
            return self._ident(f, "extensao", 0.15, ids_ext, "extensao bate, mas a assinatura esperada nao (compactado, cifrado ou outro formato)")
        return Identificacao(None, "nenhuma", 0.0)


def aplicar_contexto(ident: Identificacao, caminho_logico: str, regras: list[dict], registro: Registro) -> Identificacao:
    """Camada 4: regras de analise/contexto.json (evidencia do Ghidra/Craft Anything)."""
    for r in regras:
        if fnmatch.fnmatch(caminho_logico.lower(), r["padrao"].lower()) or fnmatch.fnmatch(PurePosixPath(caminho_logico).name.lower(), r["padrao"].lower()):
            conf = float(r.get("confianca", 0.85))
            if conf > ident.confianca:
                f = registro.get(r["formato_id"]) or {}
                ev = r["evidencia"]
                onde = ev.get("funcao") or ev.get("endereco") or ev.get("arquivo") or ev["fonte"]
                return Identificacao(r["formato_id"], "contexto", conf, f.get("empresa_ou_motor"), f.get("tipo"), [ident.id] if ident.id else [], f"carregado por {onde}")
    return ident


def aplicar_gemini(ident: Identificacao, resposta: dict | None, registro: Registro, teto: float = 0.6) -> Identificacao:
    """Camada 5: hipotese do Gemini (so quando as outras camadas nao decidiram)."""
    if not resposta or ident.id is not None:
        return ident
    fid = resposta.get("formato_id_proposto")
    if not fid:
        return ident
    f = registro.get(fid) or {}
    return Identificacao(fid, "gemini", min(teto, float(resposta.get("confianca", 0))), f.get("empresa_ou_motor"), f.get("tipo") or resposta.get("tipo"), [], "hipotese do Gemini (revisar)")


@lru_cache(maxsize=1)
def registro_padrao() -> Registro:
    return Registro.carregar()


def ler_amostras(caminho: Path) -> tuple[bytes, bytes, int]:
    tam = caminho.stat().st_size
    with open(caminho, "rb") as f:
        cabeca = f.read(TAM_CABECA)
        if tam > TAM_CAUDA:
            f.seek(tam - TAM_CAUDA)
            cauda = f.read(TAM_CAUDA)
        else:
            cauda = cabeca
    return cabeca, cauda, tam


def identificar_arquivo(caminho: Path, registro: Registro | None = None) -> Identificacao:
    cabeca, cauda, tam = ler_amostras(Path(caminho))
    return (registro or registro_padrao()).identificar(cabeca, cauda, tam, Path(caminho).name)
