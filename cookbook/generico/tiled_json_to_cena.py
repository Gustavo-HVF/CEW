"""Mapa do Tiled em JSON (.tmj/.json) -> cena bruta 2D: objetos posicionados + camadas de tiles.

Campos conforme docs/reference/json-map-format.rst do repositorio oficial do Tiled
(https://github.com/mapeditor/tiled, lido em 2026-11-21): mapa com type "map", width/height (tiles),
tilewidth/tileheight (px), layers (tilelayer com data, objectgroup com objects, group com layers);
objeto com id (unico no mapa), name, type (classe; "class" no 1.9), x/y/width/height em pixels,
rotation em graus no sentido horario, gid quando o objeto e um tile, point, properties [{name,type,value}].
Origem no topo esquerdo, y para baixo. Objeto-tile (gid) e ancorado na base esquerda no mapa ortogonal
com alinhamento "unspecified" (hipotese registrada em docs/DECISOES.md).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import base64
import json
import struct

from converters.comum.binario import ErroFormato, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.compressao import gzip_descompactar, zlib_descompactar

INFO = {
    "arquivo": "cookbook/generico/tiled_json_to_cena.py",
    "descricao": "Converte mapas do Tiled (JSON) em cena bruta 2D com objetos e tiles.",
    "formatos_entrada": ["tiled.mapa.json"],
    "destino": "cena (json)",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"pixels_por_metro\": 32}.",
}

GID_MASCARA = 0x1FFFFFFF  # bits altos guardam espelhamento (flip) no Tiled


def _props(lista) -> dict:
    return {p["name"]: p.get("value") for p in (lista or []) if isinstance(p, dict) and "name" in p}


def _dados_tiles(camada: dict, esc: Escritor) -> list[int] | None:
    d = camada.get("data")
    if isinstance(d, list):
        return [int(x) for x in d]
    if isinstance(d, str) and camada.get("encoding") == "base64":
        bruto = base64.b64decode(d)
        comp = camada.get("compression") or ""
        if comp == "zlib":
            bruto = zlib_descompactar(bruto)
        elif comp == "gzip":
            bruto = gzip_descompactar(bruto)
        elif comp:
            esc.avisar(f"camada {camada.get('name')}: compressao {comp} nao suportada")
            return None
        return list(struct.unpack(f"<{len(bruto) // 4}I", bruto[: len(bruto) // 4 * 4]))
    if camada.get("chunks"):
        esc.avisar(f"camada {camada.get('name')}: mapa infinito (chunks) ainda nao suportado")
    return None


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    try:
        m = json.loads(dados.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise ErroFormato(f"JSON invalido: {e}") from e
    exigir(isinstance(m, dict) and m.get("type", "map") == "map" and isinstance(m.get("layers"), list), "nao e mapa do Tiled (type 'map' com layers)")
    tw, th = int(m.get("tilewidth", 0)), int(m.get("tileheight", 0))
    w, h = int(m.get("width", 0)), int(m.get("height", 0))
    exigir(tw > 0 and th > 0 and w >= 0 and h >= 0, "dimensoes do mapa invalidas")
    if m.get("orientation", "orthogonal") != "orthogonal":
        esc.avisar(f"orientacao {m.get('orientation')}: posicoes mantidas em pixels do Tiled, sem projecao")
    ppm = float(opcoes.get("pixels_por_metro", 32))
    entidades, camadas, tiles = [], [], []

    def visitar(lista, dx=0.0, dy=0.0, prefixo=""):
        for camada in lista:
            nome = prefixo + str(camada.get("name", f"camada{camada.get('id', '')}"))
            ox, oy = dx + float(camada.get("offsetx", 0)), dy + float(camada.get("offsety", 0))
            cid = str(camada.get("id", len(camadas)))
            camadas.append({"id": cid, "nome": nome, "ordem": len(camadas), "visivel": bool(camada.get("visible", True))})
            tipo = camada.get("type")
            if tipo == "group":
                visitar(camada.get("layers", []), ox, oy, nome + "/")
            elif tipo == "tilelayer":
                d = _dados_tiles(camada, esc)
                if d is not None:
                    lw, lh = int(camada.get("width", w)), int(camada.get("height", h))
                    exigir(len(d) == lw * lh, f"camada {nome}: {len(d)} tiles para {lw}x{lh}")
                    tiles.append({"camada": nome, "largura": lw, "altura": lh, "tamanho_tile_px": [tw, th], "dados": [g & GID_MASCARA for g in d], "tileset_asset_id": None})
            elif tipo == "objectgroup":
                for o in camada.get("objects", []):
                    classe = o.get("type") or o.get("class") or ""
                    ent = {"id": f"bruta_{len(entidades)}", "id_original": str(o["id"]) if "id" in o else None, "nome": o.get("name") or None,
                           "tipo_original": classe or o.get("name") or "objeto", "categoria": None, "camada": nome,
                           "posicao": [float(o.get("x", 0)) + ox, float(o.get("y", 0)) + oy], "guinada_graus": float(o.get("rotation", 0))}
                    if o.get("width") or o.get("height"):
                        ent["tamanho"] = [float(o.get("width", 0)), float(o.get("height", 0))]
                    ent["ancora"] = "base_esquerda" if o.get("gid") else ("centro" if o.get("point") else "topo_esquerdo")
                    props = _props(o.get("properties"))
                    if o.get("gid"):
                        props["gid"] = int(o["gid"]) & GID_MASCARA
                    if o.get("template"):
                        props["template"] = o["template"]
                    if props:
                        ent["propriedades"] = props
                    entidades.append(ent)

    visitar(m["layers"])
    cena = {"schema_version": "1.0", "gerado_por": "cew", "id_cena": str(opcoes.get("id_cena") or _props(m.get("properties")).get("nome") or "mapa"),
            "origem": opcoes.get("origem", ""), "estado": "bruta", "dimensao": "2d",
            "sistema_coordenadas": {"eixo_para_cima": "-Y", "mao": "direita", "metros_por_unidade": 1.0 / ppm, "origem_2d": "topo_esquerdo", "pixels_por_unidade": 1.0, "rotacao": "horaria"},
            "limites": {"largura_px": w * tw, "altura_px": h * th}, "camadas": camadas, "tiles": tiles, "entidades": entidades,
            "estatisticas": {"tiledversion": m.get("tiledversion"), "tilesets": [t.get("source") or t.get("name") for t in m.get("tilesets", [])]}}
    try:
        from cew.esquemas import validar

        validar(cena, "dados/cena")
    except ImportError:  # pragma: no cover
        pass
    esc.gravar("cena_bruta.json", (json.dumps(cena, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), "mapa", "cena_bruta", {"extras": {"entidades": len(entidades)}})
    return {"objetos": len(entidades), "camadas_tiles": len(tiles)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
