"""Etapa 3: inventario e identificacao de formatos.

Percorre o alvo, abre conteiners e compressoes recursivamente (com limites contra bombas e
laços), e grava inventario.json: caminho, tamanho, SHA-256, assinatura, ordem de bytes,
entropia, compressao, formato (camada que decidiu + confianca) e estado.
Idempotente: uma extracao ja feita para o mesmo SHA-256 e reaproveitada.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from converters.comum.binario import ErroFormato
from converters.comum.compressao import DESCOMPACTADORES, detectar

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import id_estavel, juntar_conteiner, nfc, relativo_posix
from .conversores import papel, rodar
from .logs import Log, agora_iso
from .projeto import Projeto
from .registro import TAM_CAUDA, Identificacao, Registro, aplicar_contexto, aplicar_gemini, ler_amostras

LIMIAR_IDENTIFICADO = 0.3
BLOCO = 1024 * 1024
LIMITE_ENTROPIA = 32 * 1024 * 1024


@dataclass
class Limites:
    profundidade_maxima: int = 8
    bytes_extraidos_maximo: int = 8 * 1024**3
    arquivos_maximo: int = 200_000

    def para_json(self) -> dict:
        return {"profundidade_maxima": self.profundidade_maxima, "bytes_extraidos_maximo": self.bytes_extraidos_maximo, "arquivos_maximo": self.arquivos_maximo}


def hash_e_entropia(caminho: Path) -> tuple[str, float]:
    h = hashlib.sha256()
    contagem = [0] * 256
    lidos = 0
    with open(caminho, "rb") as f:
        while True:
            b = f.read(BLOCO)
            if not b:
                break
            h.update(b)
            if lidos < LIMITE_ENTROPIA:
                parte = b[: LIMITE_ENTROPIA - lidos]
                for v, n in Counter(parte).items():
                    contagem[v] += n
                lidos += len(parte)
    if lidos == 0:
        return h.hexdigest(), 0.0
    ent = -sum((n / lidos) * math.log2(n / lidos) for n in contagem if n)
    return h.hexdigest(), round(ent, 4)


def ordem_heuristica(cabeca: bytes) -> str:
    """Compara quantos u32 'pequenos' aparecem lendo em big e em little endian."""
    n = min(16, len(cabeca) // 4)
    if n < 2:
        return "desconhecida"
    be = sum(1 for i in range(n) if 0 < struct.unpack_from(">I", cabeca, 4 * i)[0] < 0x01000000)
    le = sum(1 for i in range(n) if 0 < struct.unpack_from("<I", cabeca, 4 * i)[0] < 0x01000000)
    if be >= le + 3:
        return "big"
    if le >= be + 3:
        return "little"
    return "desconhecida"


def _texto_assinatura(b: bytes) -> str:
    return "".join(chr(c) if 32 <= c < 127 else "." for c in b)


class Inventariador:
    def __init__(self, projeto: Projeto, registro: Registro, limites: Limites | None = None, log: Log | None = None):
        self.p = projeto
        self.reg = registro
        self.lim = limites or Limites()
        self.log = log or Log("inventario")
        self.itens: list[dict] = []
        self.bytes_extraidos = 0
        self.contexto = projeto.ler("contexto")["regras"] if projeto.existe("contexto") else []
        self.respostas_gemini = self._carregar_respostas()

    def _carregar_respostas(self) -> dict[str, dict]:
        pasta = self.p.caminho("tarefas_gemini")
        saida = {}
        for arq in sorted(pasta.glob("*.resposta.json")):
            try:
                doc = json.loads(arq.read_text(encoding="utf-8"))
                saida[arq.name.split(".")[0]] = doc
            except ValueError:
                continue
        return saida

    # ----------------------------------------------------------------------------------
    def executar(self, alvo: Path, dry_run: bool = False) -> dict:
        alvo = Path(alvo).resolve()
        if not alvo.exists():
            raise FileNotFoundError(f"alvo nao encontrado: {alvo}")
        fila: list[tuple[str, Path, str, str | None, int]] = []
        if alvo.is_file():
            base = alvo.parent
            fila.append((nfc(alvo.name), alvo, "alvo", None, 0))
        else:
            base = alvo
            for raiz, dirs, arqs in os.walk(alvo, followlinks=False):
                dirs.sort()
                for a in sorted(arqs):
                    c = Path(raiz, a)
                    if c.is_symlink() or not c.is_file():
                        continue
                    fila.append((relativo_posix(c, alvo), c, "alvo", None, 0))
        self.base_alvo = base
        while fila:
            if len(self.itens) >= self.lim.arquivos_maximo:
                self.log.aviso(f"limite de {self.lim.arquivos_maximo} arquivos atingido; inventario parcial", etapa="inventario")
                break
            logico, disco, origem, pai, prof = fila.pop(0)
            item, filhos = self._processar(logico, disco, origem, pai, prof, dry_run)
            self.itens.append(item)
            fila[0:0] = filhos  # filhos logo depois do pai (ordem estavel, em profundidade)
        doc = self._documento(alvo)
        if not dry_run:
            self.p.gravar("inventario", doc)
        return doc

    def _documento(self, alvo: Path) -> dict:
        resumo = Counter(i["estado"] for i in self.itens)
        por_formato = Counter(i["formato"]["id"] or "desconhecido" for i in self.itens)
        alvo_info: dict[str, Any] = {"caminho": str(alvo), "tipo": "pasta" if alvo.is_dir() else "arquivo"}
        if alvo.is_file() and self.itens:
            alvo_info["sha256"] = self.itens[0]["sha256"]
        return {
            "schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "gerado_em": agora_iso(), "projeto": self.p.nome,
            "alvo": alvo_info, "limites": self.lim.para_json(),
            "resumo": {"total": len(self.itens), "identificados": resumo.get("identificado", 0), "desconhecidos": resumo.get("desconhecido", 0),
                       "compactados": resumo.get("compactado", 0), "bytes_total": sum(i["tamanho_bytes"] for i in self.itens if i["profundidade"] == 0),
                       "por_formato": dict(sorted(por_formato.items()))},
            "itens": self.itens,
        }

    def _identificar(self, logico: str, cabeca: bytes, cauda: bytes, tam: int, sha: str) -> Identificacao:
        ident = self.reg.identificar(cabeca, cauda, tam, logico.rsplit("/", 1)[-1])
        if self.contexto:
            ident = aplicar_contexto(ident, logico, self.contexto, self.reg)
        if ident.confianca < LIMIAR_IDENTIFICADO:
            sem = Identificacao(None, "nenhuma", 0.0, candidatos=[ident.id] if ident.id else [])
            com_gemini = aplicar_gemini(sem, self.respostas_gemini.get(sha), self.reg)
            if com_gemini.id:
                return com_gemini
        return ident

    def _processar(self, logico: str, disco: Path, origem: str, pai: str | None, prof: int, dry_run: bool):
        iid = id_estavel("i", logico)
        cabeca, cauda, tam = ler_amostras(disco)
        sha, ent = hash_e_entropia(disco)
        ident = self._identificar(logico, cabeca, cauda, tam, sha)
        fmt = self.reg.get(ident.id) if ident.confianca >= LIMIAR_IDENTIFICADO else None
        if fmt and fmt["id"] == "nintendo.sarc" and cabeca[6:8] in (b"\xfe\xff", b"\xff\xfe"):
            ordem = "big" if cabeca[6:8] == b"\xfe\xff" else "little"
        elif fmt and fmt["ordem_de_bytes"] != "desconhecida":
            ordem = fmt["ordem_de_bytes"]
        else:
            ordem = ordem_heuristica(cabeca)
        disco_rel = relativo_posix(disco, self.base_alvo) if origem == "alvo" else relativo_posix(disco, self.p.pasta)
        item: dict[str, Any] = {
            "id": iid, "caminho": logico, "caminho_no_disco": disco_rel, "origem": origem, "pai": pai, "profundidade": prof,
            "tamanho_bytes": tam, "sha256": sha, "assinatura_hex": cabeca[:16].hex(), "assinatura_texto": _texto_assinatura(cabeca[:16]),
            "ordem_de_bytes": ordem, "entropia_bits_por_byte": ent, "compressao": None,
            "formato": ident.para_json() if ident.confianca >= LIMIAR_IDENTIFICADO else {**Identificacao(None, "nenhuma", 0.0).para_json(), **({"candidatos": [ident.id]} if ident.id else {})},
            "estado": "identificado" if fmt else "desconhecido", "observacoes": [],
        }
        filhos: list[tuple[str, Path, str, str | None, int]] = []
        det = detectar(cabeca, tam)
        if det is not None and (fmt is None or fmt["tipo"] == "compressao"):
            item["estado"] = "compactado"
            item["compressao"] = {"algoritmo": det.algoritmo, "confianca": det.confianca, "tamanho_descompactado": det.tamanho_descompactado, "descompactado_em": None}
        elif fmt is None and ent > 7.9 and tam > 1024:
            item["observacoes"].append("entropia muito alta: provavelmente compactado com algoritmo desconhecido ou cifrado (o CEW nao decifra)")
        if fmt and fmt.get("cifrado_comum"):
            item["observacoes"].append("formato costuma vir cifrado; se estiver, o CEW registra e nao decifra")
        # expandir conteiner/compressao
        if prof < self.lim.profundidade_maxima:
            try:
                filhos = self._expandir(item, fmt, disco, logico, iid, prof, dry_run)
            except ErroFormato as e:
                item["observacoes"].append(f"nao foi possivel abrir: {e}")
                self.log.aviso(f"falha ao abrir {logico}: {e}", etapa="inventario", item=iid)
        elif fmt and fmt["tipo"] in ("conteiner", "compressao"):
            item["observacoes"].append("profundidade maxima atingida; conteiner nao aberto")
        if not item["observacoes"]:
            del item["observacoes"]
        return item, filhos

    def _expandir(self, item: dict, fmt: dict | None, disco: Path, logico: str, iid: str, prof: int, dry_run: bool):
        destino = self.p.caminho("extraido") / iid
        escolha = self.reg.conversor(fmt["id"]) if fmt else {"ref": None}
        conversor = escolha["ref"]
        usar_conversor = bool(conversor) and papel(conversor, self.p.pasta) in ("extrator", "descompactador")
        algoritmo = (item.get("compressao") or {}).get("algoritmo")
        if not usar_conversor and not (algoritmo in DESCOMPACTADORES and (item["compressao"]["confianca"] >= 0.5)):
            return []
        marcador = destino / ".cew_extracao.json"
        saidas: list[dict]
        if marcador.is_file():
            antigo = json.loads(marcador.read_text(encoding="utf-8"))
            if antigo.get("sha256") == item["sha256"]:
                saidas = antigo["saidas"]
            else:
                shutil.rmtree(destino, ignore_errors=True)
                saidas = []
        else:
            saidas = []
        if not saidas:
            if dry_run:
                self.log.info(f"[dry-run] abriria {logico}", etapa="inventario", item=iid)
                return []
            if usar_conversor:
                opcoes = {}
                if fmt and fmt["id"] == "valve.source.vpk" and disco.name.endswith("_dir.vpk"):
                    opcoes = {"pasta_vpk": str(disco.parent), "nome_base": disco.name[: -len("_dir.vpk")]}
                r = rodar(conversor, disco, destino, opcoes, projeto_pasta=self.p.pasta)
                if not r["ok"]:
                    raise ErroFormato(r["erro"] or "extracao falhou")
                for a in r["avisos"]:
                    item.setdefault("observacoes", []).append(a)
                saidas = [{"caminho": s["caminho"], "tamanho_bytes": s["tamanho_bytes"]} for s in r["saidas"]]
            else:
                limite = max(0, self.lim.bytes_extraidos_maximo - self.bytes_extraidos)
                dados = DESCOMPACTADORES[algoritmo](disco.read_bytes(), min(limite, 2 * 1024**3))
                nome = Path(logico).stem or "descompactado"
                destino.mkdir(parents=True, exist_ok=True)
                (destino / nome).write_bytes(dados)
                saidas = [{"caminho": nome, "tamanho_bytes": len(dados)}]
            marcador.parent.mkdir(parents=True, exist_ok=True)
            marcador.write_text(json.dumps({"sha256": item["sha256"], "saidas": saidas}, ensure_ascii=False), encoding="utf-8")
        total = sum(s["tamanho_bytes"] for s in saidas)
        self.bytes_extraidos += total
        if self.bytes_extraidos > self.lim.bytes_extraidos_maximo:
            raise ErroFormato(f"limite de {self.lim.bytes_extraidos_maximo} bytes extraidos atingido (possivel bomba de descompressao)")
        filhos = []
        for s in saidas:
            filhos.append((juntar_conteiner(logico, s["caminho"]), destino / s["caminho"], "extraido", iid, prof + 1))
        if item.get("compressao") and filhos:
            item["compressao"]["descompactado_em"] = id_estavel("i", filhos[0][0])
        else:
            item["extraido"] = True
        return filhos


def inventariar(projeto: Projeto, alvo: Path, dry_run: bool = False, registro: Registro | None = None, limites: Limites | None = None) -> dict:
    from .registro import registro_do_projeto

    return Inventariador(projeto, registro or registro_do_projeto(projeto.pasta), limites).executar(alvo, dry_run)


__all__ = ["inventariar", "Inventariador", "Limites", "LIMIAR_IDENTIFICADO", "TAM_CAUDA"]
