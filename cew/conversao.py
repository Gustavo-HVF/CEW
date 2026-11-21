"""Executa o plano de conversao e gera web/asset_manifest.json (o que o jogo web carrega).

- cada item "pendente" roda o conversor do registro em build/convertido/<id do plano>/;
- saidas intermediarias seguem uma cadeia (WAV de um decodificador -> wav_to_ogg);
- as saidas finais vao para web/assets/<tipo>/<nome>-<id8>.<ext> (ou web/dados/), com id estavel
  derivado do caminho de origem + nome da saida (item 5.4): o mesmo arquivo de origem gera sempre o
  mesmo id e o mesmo caminho web;
- idempotente: item ja concluido com o mesmo SHA-256 de entrada nao roda de novo.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path, PurePosixPath
from typing import Any

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import id_estavel, slug
from .conversores import rodar
from .logs import Log
from .projeto import Projeto

MIME = {"png": "image/png", "jpg": "image/jpeg", "webp": "image/webp", "ktx2": "image/ktx2", "glb": "model/gltf-binary", "ogg": "audio/ogg",
        "wav": "audio/wav", "mp3": "audio/mpeg", "mid": "audio/midi", "json": "application/json", "webm": "video/webm", "mp4": "video/mp4"}
TIPO_ASSET = {"textura": "textura", "modelo": "modelo", "animacao": "animacao", "audio": "audio", "video": "video", "mapa": "mapa", "dados": "dados", "fonte": "fonte"}
PASTA_TIPO = {"textura": "texturas", "modelo": "modelos", "animacao": "animacoes", "audio": "audio", "video": "video", "mapa": "mapas", "fonte": "fontes", "outro": "outros"}
CADEIA = {"wav": "converters/generico/wav_to_ogg.py"}


def _origem_disco(projeto: Projeto, item: dict, inventario: dict) -> Path:
    if item["origem"] == "alvo":
        base = Path(inventario["alvo"]["caminho"])
        return base if base.is_file() else base / item["caminho_no_disco"]
    return projeto.pasta / item["caminho_no_disco"]


def executar(projeto: Projeto, dry_run: bool = False, log: Log | None = None, opcoes_por_formato: dict[str, dict] | None = None) -> dict:
    log = log or Log("conversao")
    inv = projeto.ler("inventario")
    plano = projeto.ler("plano")
    por_item = {i["id"]: i for i in inv["itens"]}
    pasta_conv = projeto.caminho("convertido")
    relatorio = {"convertidos": 0, "pulados": 0, "erros": 0, "dry_run": dry_run}
    for p in sorted(plano["itens"], key=lambda x: (x["prioridade"], x["caminho"] if "caminho" in x else "")):
        if p["estado"] != "pendente" or not p["conversor"]:
            relatorio["pulados"] += 1
            continue
        item = por_item[p["item_inventario"]]
        entrada = _origem_disco(projeto, item, inv)
        destino = pasta_conv / p["id"]
        opcoes = dict((opcoes_por_formato or {}).get(p["formato_origem"] or "", {}))
        opcoes.update(p.get("opcoes") or {})
        if dry_run:
            log.info(f"[dry-run] {p['conversor']} {item['caminho']}", etapa="conversao", item=p["id"])
            relatorio["convertidos"] += 1
            continue
        if destino.exists():
            shutil.rmtree(destino)
        try:
            r = rodar(p["conversor"], entrada, destino, opcoes)
            if not r["ok"]:
                raise RuntimeError(r["erro"])
            saidas = []
            for s in r["saidas"]:
                formato = s["formato"]
                caminho = destino / s["caminho"]
                if formato in CADEIA and p["conversor"] != CADEIA[formato]:
                    r2 = rodar(CADEIA[formato], caminho, destino / "cadeia", {})
                    if not r2["ok"]:
                        raise RuntimeError(f"cadeia {CADEIA[formato]}: {r2['erro']}")
                    for s2 in r2["saidas"]:
                        saidas.append({**s2, "caminho": f"cadeia/{s2['caminho']}"})
                    continue
                saidas.append(s)
            p["saidas"] = [f"build/convertido/{p['id']}/{s['caminho']}" for s in saidas]
            p["_metadados"] = {s["caminho"]: {"tipo": s["tipo"], "formato": s["formato"], "metadados": s.get("metadados", {})} for s in saidas}
            p["estado"], p["erro"] = "concluido", None
            relatorio["convertidos"] += 1
        except Exception as e:  # noqa: BLE001 - registrar no plano e seguir
            p["estado"], p["erro"] = "erro", str(e)[:1000]
            relatorio["erros"] += 1
            log.erro(f"falha em {item['caminho']}: {e}", etapa="conversao", item=p["id"])
    metas = {p["id"]: p.pop("_metadados", None) for p in plano["itens"]}
    if not dry_run:
        projeto.gravar("plano", plano)
        manifesto = publicar(projeto, plano, inv, metas)
        relatorio["assets"] = len(manifesto["assets"])
    return relatorio


def _metadados_de_resultado(projeto: Projeto, pid: str, rel: str, metas: dict) -> dict[str, Any] | None:
    m = (metas.get(pid) or {}).get(rel)
    if m is not None:
        return m
    # item concluido em execucao anterior: os metadados ficaram no manifesto antigo
    return None


def publicar(projeto: Projeto, plano: dict, inv: dict, metas: dict | None = None) -> dict:
    metas = metas or {}
    por_item = {i["id"]: i for i in inv["itens"]}
    web = projeto.caminho("web")
    antigo = {a["id"]: a for a in projeto.ler("manifesto")["assets"]} if projeto.existe("manifesto") else {}
    assets: list[dict] = []
    for p in plano["itens"]:
        if p["estado"] != "concluido" or not p.get("saidas") or not p.get("conversor"):
            continue
        item = por_item.get(p["item_inventario"])
        if not item:
            continue
        prefixo = f"build/convertido/{p['id']}/"
        for caminho_saida in p["saidas"]:
            rel = caminho_saida[len(prefixo):] if caminho_saida.startswith(prefixo) else caminho_saida
            arq = projeto.pasta / caminho_saida
            if not arq.is_file():
                continue
            aid = id_estavel("a", item["caminho"], rel)
            m = _metadados_de_resultado(projeto, p["id"], rel, metas)
            ext = PurePosixPath(rel).suffix.lstrip(".").lower()
            if m is None:
                velho = antigo.get(aid)
                tipo, meta = (velho["tipo"], velho["metadados"]) if velho else ("outro", {})
            else:
                tipo, meta = TIPO_ASSET.get(m["tipo"], "outro"), dict(m["metadados"] or {})
            nome_base = slug(PurePosixPath(item["caminho"].split("!/")[-1]).stem)
            if len(p["saidas"]) > 1:
                nome_base += "-" + slug(PurePosixPath(rel).stem)
            nome = f"{nome_base}-{aid[2:10]}.{ext}"
            caminho_web = f"dados/{nome}" if tipo == "dados" else f"assets/{PASTA_TIPO.get(tipo, 'outros')}/{nome}"
            dados = arq.read_bytes()
            alvo = web / caminho_web
            if not alvo.is_file() or alvo.read_bytes() != dados:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(dados)
            assets.append({
                "id": aid, "caminho_web": caminho_web, "tipo": tipo, "mime": MIME.get(ext, "application/octet-stream"),
                "hash_sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados),
                "origem": {"item_inventario": item["id"], "caminho": item["caminho"], "formato": p["formato_origem"], "conversor": p["conversor"]},
                "metadados": meta,
            })
    assets.sort(key=lambda a: a["caminho_web"])
    # remove arquivos publicados que sairam do manifesto (rodar de novo refaz so o que mudou)
    validos = {a["caminho_web"] for a in assets}
    for pasta in (web / "assets", web / "dados"):
        if pasta.is_dir():
            for f in sorted(pasta.rglob("*")):
                if f.is_file() and f.relative_to(web).as_posix() not in validos:
                    f.unlink()
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "raiz_web": "web", "assets": assets}
    projeto.gravar("manifesto", doc)
    return doc
