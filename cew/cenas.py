"""Mapeamento e reposicionamento de elementos de cena (inimigos, vegetacao, estruturas, itens...).

Fluxo:
1. o conversor do mapa (cookbook ou escrito pelo agente) grava `*cena_bruta.json`
   (schemas/dados/cena.schema.json, estado "bruta"): tipo original, posicao e rotacao nas unidades
   e eixos do jogo, e o sistema de coordenadas declarado;
2. `normalizar` converte para o sistema do CEW (3D: metros, Y para cima, mao direita; 2D: pixels com
   origem no topo esquerdo), aplica as regras de `mapeamento_entidades.json` (categoria, asset,
   escala, deslocamento, remocao), categoriza o resto por palavras-chave, liga cada elemento a um
   asset do manifesto e aplica os ajustes de `ajustes_cena.json` (reposicionamento nao destrutivo);
3. a cena normalizada e publicada em web/dados/cenas/ e entra no asset_manifest.json (tipo "mapa"):
   o jogo web carrega o mapa e o posicionamento de todos os elementos juntos.

Ids de entidade (e_<16 hex>) sao estaveis: vem do id original quando existe, senao do tipo +
posicao original (+ ordem entre identicos). Assim os ajustes sobrevivem a uma nova conversao.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from converters.comum.eixos import converter_ponto

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import id_estavel, slug
from .esquemas import gravar_json, ler_json, validar
from .logs import agora_iso

SUFIXO_BRUTA = "cena_bruta.json"

# Palavras-chave (pt/en) -> categoria; a primeira que casar vence. Regras do projeto vem antes.
HEURISTICA: list[tuple[str, tuple[str, ...]]] = [
    ("spawn", ("spawn", "player_start", "playerstart", "start_point", "info_player", "checkpoint", "respawn")),
    ("jogador", ("player", "jogador", "hero", "heroi")),
    ("inimigo", ("monster", "enemy", "inimigo", "mob", "boss", "chefe", "hostile", "zombie", "zumbi", "slime", "goblin", "skeleton", "esqueleto", "soldier")),
    ("npc", ("npc", "villager", "aldeao", "vendedor", "merchant", "shopkeeper")),
    ("vegetacao", ("tree", "arvore", "bush", "arbusto", "grass", "grama", "plant", "planta", "foliage", "folhagem", "flower", "flor", "vine", "cipo", "palm", "cactus", "mushroom", "cogumelo")),
    ("porta", ("door", "porta", "gate", "portao")),
    ("plataforma", ("platform", "plataforma", "elevator", "elevador", "lift", "func_plat", "func_train")),
    ("estrutura", ("pillar", "pilastra", "pilar", "column", "coluna", "wall", "parede", "rock", "pedra", "rocha", "crate", "caixa", "barrel", "barril", "statue", "estatua", "fence", "cerca", "house", "casa", "building", "predio", "func_wall", "bridge", "ponte")),
    ("item", ("item", "weapon", "arma", "ammo", "municao", "coin", "moeda", "pickup", "health", "vida", "key", "chave", "powerup", "chest", "bau", "gem", "gema")),
    ("gatilho", ("trigger", "gatilho", "volume", "zone", "zona")),
    ("luz", ("light", "luz", "lamp", "lampada", "torch", "tocha")),
    ("som", ("sound", "som", "ambient", "audio", "music", "musica")),
    ("camera", ("camera",)),
    ("veiculo", ("vehicle", "veiculo", "car", "carro", "boat", "barco")),
    ("efeito", ("particle", "particula", "effect", "efeito", "fx_", "emitter")),
    ("decoracao", ("decor", "prop", "misc_", "detail", "detalhe", "sign", "placa")),
]


def categoria_heuristica(texto: str) -> str | None:
    t = texto.lower()
    for categoria, palavras in HEURISTICA:
        if any(p in t for p in palavras):
            return categoria
    return None


def _origem(sc: dict) -> str:
    up = sc["eixo_para_cima"]
    mao = "rh" if sc["mao"] == "direita" else "lh"
    return f"{'z' if up == 'Z' else 'y'}_up_{mao}"


def converter_quaternion(q: list[float], origem: str) -> list[float]:
    """Quaternion [x,y,z,w] no sistema de origem -> Y para cima, mao direita.

    A parte vetorial transforma como pseudovetor: v' = det(M) * M v (w nao muda).
    """
    x, y, z, w = q
    v = converter_ponto((x, y, z), origem)
    det = -1.0 if origem.endswith("_lh") else 1.0
    r = [det * v[0], det * v[1], det * v[2], w]
    n = math.sqrt(sum(c * c for c in r)) or 1.0
    return [round(c / n, 7) for c in r]


def quat_guinada(graus: float) -> list[float]:
    a = math.radians(graus) / 2
    return [0.0, round(math.sin(a), 7), 0.0, round(math.cos(a), 7)]


def _arred(v: list[float], casas: int = 5) -> list[float]:
    return [round(float(c), casas) + 0.0 for c in v]


def _id_entidade(id_cena: str, ent: dict, ordinal: int) -> str:
    if ent.get("id_original") not in (None, ""):
        return id_estavel("e", id_cena, "id", str(ent["id_original"]))
    pos = ",".join(f"{c:.3f}" for c in ent["posicao"])
    return id_estavel("e", id_cena, ent["tipo_original"], pos, str(ordinal))


# ----------------------------------------------------------------------------- assets
class IndiceAssets:
    def __init__(self, assets: list[dict]):
        self.assets = sorted((a for a in assets if a["tipo"] in ("modelo", "textura", "animacao")), key=lambda a: a["caminho_web"])
        self.por_id = {a["id"]: a for a in assets}

    def por_glob(self, padrao: str, dimensao: str) -> str | None:
        preferido = "modelo" if dimensao == "3d" else "textura"
        achados = [a for a in self.assets if fnmatch.fnmatch(a["origem"]["caminho"].lower(), padrao.lower())]
        achados.sort(key=lambda a: (a["tipo"] != preferido, a["caminho_web"]))
        return achados[0]["id"] if achados else None

    def por_modelo(self, referencia: str, dimensao: str) -> str | None:
        ref = referencia.lower().replace("\\", "/").lstrip("./")
        if not ref or ref.startswith("*"):
            return None
        return self.por_glob(f"*{ref}", dimensao) or self.por_glob(f"*{PurePosixPath(ref).stem}.*", dimensao)

    def por_nome(self, tipo_original: str, dimensao: str) -> str | None:
        tokens = [t for t in re.split(r"[_\-\s./]+", tipo_original.lower()) if len(t) >= 3]
        if not tokens:
            return None
        alvo = tokens[-1]
        preferido = "modelo" if dimensao == "3d" else "textura"
        achados = [a for a in self.assets if PurePosixPath(a["origem"]["caminho"].split("!/")[-1]).stem.lower() == alvo]
        achados.sort(key=lambda a: (a["tipo"] != preferido, a["caminho_web"]))
        return achados[0]["id"] if achados else None


# ------------------------------------------------------------------------------ regras
def _casa_regra(regra: dict, ent: dict, id_cena: str) -> bool:
    q = regra["quando"]
    pares = [("tipo_original", ent.get("tipo_original") or ""), ("nome", ent.get("nome") or ""), ("camada", ent.get("camada") or ""), ("cena", id_cena)]
    for chave, valor in pares:
        if chave in q and not fnmatch.fnmatch(valor.lower(), q[chave].lower()):
            return False
    for k, padrao in (q.get("propriedades") or {}).items():
        if not fnmatch.fnmatch(str((ent.get("propriedades") or {}).get(k, "")).lower(), padrao.lower()):
            return False
    return True


def ler_regras(projeto_pasta: Path) -> dict:
    arq = Path(projeto_pasta) / "mapeamento_entidades.json"
    if arq.is_file():
        return ler_json(arq, "mapeamento_entidades")
    return {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "usar_heuristica": True, "categoria_padrao": "outro", "regras": []}


def ler_ajustes(projeto_pasta: Path) -> dict:
    arq = Path(projeto_pasta) / "ajustes_cena.json"
    if arq.is_file():
        return ler_json(arq, "ajustes_cena")
    return {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "ajustes": []}


# --------------------------------------------------------------------------- normalizar
def normalizar(bruta: dict, assets: list[dict], regras: dict, ajustes: dict, id_cena: str | None = None, geometria_asset_id: str | None = None) -> dict:
    validar(bruta, "dados/cena", "cena bruta")
    if bruta["estado"] != "bruta":
        raise ValueError("esperada cena com estado 'bruta'")
    id_cena = id_cena or bruta["id_cena"]
    sc = bruta["sistema_coordenadas"]
    dim = bruta["dimensao"]
    mpu = float(sc["metros_por_unidade"])
    sentido = -1.0 if sc.get("rotacao") == "horaria" else 1.0
    idx = IndiceAssets(assets)
    avisos = list(bruta.get("avisos", []))
    altura_px = (bruta.get("limites") or {}).get("altura_px")
    if dim == "2d" and sc.get("origem_2d") == "base_esquerda" and not altura_px:
        raise ValueError("cena 2D com origem na base precisa de limites.altura_px")
    vistos: Counter = Counter()
    saida: list[dict] = []
    removidas = 0
    for ent in bruta["entidades"]:
        chave = (ent["tipo_original"], tuple(round(c, 3) for c in ent["posicao"]))
        ordinal = vistos[chave]
        vistos[chave] += 1
        regra = next((r for r in regras.get("regras", []) if _casa_regra(r, ent, id_cena)), None)
        if regra and regra.get("remover"):
            removidas += 1
            continue
        e: dict[str, Any] = {"id": _id_entidade(id_cena, ent, ordinal), "id_original": ent.get("id_original"), "nome": ent.get("nome"),
                             "tipo_original": ent["tipo_original"], "camada": ent.get("camada"), "pai": ent.get("pai")}
        # categoria: regra > conversor > heuristica > padrao
        if regra and regra.get("categoria"):
            e["categoria"], e["categoria_por"] = regra["categoria"], "regra"
        elif ent.get("categoria"):
            e["categoria"], e["categoria_por"] = ent["categoria"], "conversor"
        else:
            h = categoria_heuristica(" ".join(filter(None, [ent["tipo_original"], ent.get("nome") or "", ent.get("camada") or ""]))) if regras.get("usar_heuristica", True) else None
            e["categoria"], e["categoria_por"] = (h, "heuristica") if h else (regras.get("categoria_padrao", "outro"), "padrao")
        # posicao e rotacao
        escala_regra = float((regra or {}).get("escala", 1.0))
        if dim == "3d":
            p = list(ent["posicao"]) + [0.0] * (3 - len(ent["posicao"]))
            pos = list(converter_ponto((p[0], p[1], p[2]), _origem(sc), mpu))
            desl = (regra or {}).get("deslocamento_m") or [0, 0, 0]
            pos = [pos[i] + desl[i] for i in range(3)]
            e["posicao"] = e["posicao_m"] = _arred(pos)
            if ent.get("rotacao"):
                e["rotacao"] = converter_quaternion(ent["rotacao"], _origem(sc))
                e["guinada_graus"] = round(math.degrees(2 * math.atan2(e["rotacao"][1], e["rotacao"][3])), 4)
            else:
                ang = ent.get("angulos_graus") or [0.0, float(ent.get("guinada_graus", 0.0)), 0.0]
                if abs(ang[0]) > 1e-9 or abs(ang[2]) > 1e-9:
                    avisos.append(f"{e['id']}: arfagem/rolagem nao convertidas (o conversor deve informar 'rotacao' em quaternion)")
                g = sentido * ang[1] * (1 if sc["mao"] == "direita" else -1) + float((regra or {}).get("guinada_extra_graus", 0))
                e["guinada_graus"] = round(g, 4)
                e["rotacao"] = quat_guinada(g)
        else:
            x, y = float(ent["posicao"][0]), float(ent["posicao"][1])
            if sc.get("origem_2d") == "base_esquerda":
                y = float(altura_px) - y
            desl = (regra or {}).get("deslocamento_m") or [0, 0, 0]
            ppu = float(sc.get("pixels_por_unidade", 1.0))
            x, y = x * ppu + desl[0] / mpu, y * ppu - desl[1] / mpu
            e["posicao"] = _arred([x, y], 3)
            e["posicao_m"] = _arred([x * mpu, -y * mpu, 0.0])
            # saida 2D: graus no sentido horario (como Phaser/PixiJS); origem anti-horaria inverte o sinal
            g = (1.0 if sc.get("rotacao", "horaria") == "horaria" else -1.0) * float(ent.get("guinada_graus", 0.0)) + float((regra or {}).get("guinada_extra_graus", 0))
            e["guinada_graus"] = round(g, 4)
        esc = ent.get("escala") or ([1.0, 1.0, 1.0] if dim == "3d" else [1.0, 1.0])
        if dim == "3d" and len(esc) == 3:
            esc = [esc[0], esc[2], esc[1]] if sc["eixo_para_cima"] == "Z" else list(esc)
        e["escala"] = _arred([c * escala_regra for c in esc])
        for k in ("tamanho", "ancora", "posicao_estimada", "modelo_original"):
            if ent.get(k) is not None:
                e[k] = ent[k]
        # asset: regra > conversor > propriedade de modelo > nome
        asset, por = None, None
        if regra and regra.get("asset"):
            asset = regra["asset"].get("asset_id") or idx.por_glob(regra["asset"].get("origem_glob", ""), dim)
            por = "regra" if asset else None
            if regra["asset"].get("asset_id") and asset not in idx.por_id:
                avisos.append(f"regra aponta para asset inexistente {asset}")
                asset, por = None, None
        if not asset and ent.get("asset_id") in idx.por_id:
            asset, por = ent["asset_id"], "conversor"
        if not asset and ent.get("modelo_original"):
            asset = idx.por_modelo(ent["modelo_original"], dim)
            por = "propriedade_modelo" if asset else None
        if not asset and e["categoria"] not in ("spawn", "gatilho", "luz", "som", "camera", "regiao"):
            asset = idx.por_nome(ent["tipo_original"], dim)
            por = "nome" if asset else None
        e["asset_id"], e["asset_por"] = asset, por
        props = dict(ent.get("propriedades") or {})
        props.update((regra or {}).get("propriedades") or {})
        if props:
            e["propriedades"] = props
        saida.append(e)
    aplicadas, adicionadas = _aplicar_ajustes(saida, ajustes, id_cena, dim, mpu, avisos)
    cena: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "id_cena": id_cena, "nome": bruta.get("nome") or id_cena,
        "origem": bruta.get("origem", ""), "estado": "normalizada", "dimensao": dim,
        "sistema_coordenadas": ({"eixo_para_cima": "Y", "mao": "direita", "metros_por_unidade": 1.0} if dim == "3d"
                                else {"eixo_para_cima": "-Y", "mao": "direita", "metros_por_unidade": mpu, "origem_2d": "topo_esquerdo", "rotacao": "horaria"}),
        "geometria_asset_id": geometria_asset_id,
    }
    for k in ("camadas", "tiles"):
        if bruta.get(k):
            cena[k] = bruta[k]
    lim = dict(bruta.get("limites") or {})
    if dim == "3d" and saida:
        lim["min_m"] = [min(e["posicao"][i] for e in saida) for i in range(3)]
        lim["max_m"] = [max(e["posicao"][i] for e in saida) for i in range(3)]
    if lim:
        cena["limites"] = lim
    cena["entidades"] = saida
    cena["estatisticas"] = {"bruta": len(bruta["entidades"]), "entidades": len(saida), "removidas_por_regra": removidas, "ajustes_aplicados": aplicadas,
                            "adicionadas": adicionadas, "sem_asset": sum(1 for e in saida if not e["asset_id"]),
                            "por_categoria": dict(sorted(Counter(e["categoria"] for e in saida).items()))}
    if avisos:
        cena["avisos"] = sorted(set(avisos))[:200]
    validar(cena, "dados/cena", "cena normalizada")
    return cena


def _alvos(ents: list[dict], aj: dict) -> list[dict]:
    if aj.get("entidade"):
        return [e for e in ents if e["id"] == aj["entidade"]]
    f = aj.get("filtro") or {}
    return [e for e in ents if all(fnmatch.fnmatch(str(e.get(k) or "").lower(), v.lower()) for k, v in f.items())]


def _atualizar_m(e: dict, dim: str, mpu: float) -> None:
    if dim == "3d":
        e["posicao_m"] = e["posicao"]
    else:
        e["posicao_m"] = _arred([e["posicao"][0] * mpu, -e["posicao"][1] * mpu, 0.0])


def _aplicar_ajustes(ents: list[dict], ajustes: dict, id_cena: str, dim: str, mpu: float, avisos: list[str]) -> tuple[int, int]:
    n = 3 if dim == "3d" else 2
    aplicadas, adicionadas = 0, 0
    for k, aj in enumerate(ajustes.get("ajustes", [])):
        if not fnmatch.fnmatch(id_cena, aj["cena"]):
            continue
        op = aj["op"]
        if op == "adicionar":
            nova = dict(aj["nova"])
            if not str(nova.get("id", "")).startswith("e_"):
                nova["id"] = id_estavel("e", id_cena, "ajuste", str(k))
            nova.setdefault("asset_id", None)
            nova["ajustado"] = True
            if dim == "3d":
                nova.setdefault("rotacao", quat_guinada(float(nova.get("guinada_graus", 0))))
            _atualizar_m(nova, dim, mpu)
            ents.append(nova)
            aplicadas += 1
            adicionadas += 1
            continue
        alvos = _alvos(ents, aj)
        if not alvos:
            avisos.append(f"ajuste {k} ({op}) nao encontrou entidades em {id_cena}")
            continue
        if op == "remover":
            ids = {e["id"] for e in alvos}
            ents[:] = [e for e in ents if e["id"] not in ids]
        for e in alvos if op != "remover" else []:
            if op == "mover":
                e["posicao"] = _arred(list(aj["para"])[:n] + [0.0] * (n - len(aj["para"])))
            elif op == "deslocar":
                d = list(aj["delta"]) + [0.0] * (n - len(aj["delta"]))
                e["posicao"] = _arred([e["posicao"][i] + d[i] for i in range(n)])
            elif op == "girar":
                e["guinada_graus"] = round(float(e.get("guinada_graus", 0)) + float(aj["graus"]), 4)
                if dim == "3d":
                    e["rotacao"] = quat_guinada(e["guinada_graus"])
            elif op == "escalar":
                e["escala"] = _arred([c * float(aj["fator"]) for c in e.get("escala", [1.0] * n)])
            elif op == "grade":
                passo = float(aj["passo"])
                e["posicao"] = _arred([round(c / passo) * passo for c in e["posicao"]])
            elif op == "definir":
                v = aj.get("valores") or {}
                for campo in ("categoria", "asset_id", "nome", "camada"):
                    if campo in v:
                        e[campo] = v[campo]
                if "categoria" in v:
                    e["categoria_por"] = "ajuste"
                if "asset_id" in v:
                    e["asset_por"] = "ajuste"
                if v.get("propriedades"):
                    e["propriedades"] = {**(e.get("propriedades") or {}), **v["propriedades"]}
            _atualizar_m(e, dim, mpu)
            e["ajustado"] = True
        aplicadas += 1
    return aplicadas, adicionadas


# ------------------------------------------------------------------------------ publicar
def publicar(projeto, plano: dict, inv: dict, assets: list[dict]) -> list[dict]:
    """Normaliza todas as cenas brutas do plano e devolve as entradas do manifesto (tipo 'mapa')."""
    por_item = {i["id"]: i for i in inv["itens"]}
    regras = ler_regras(projeto.pasta)
    ajustes = ler_ajustes(projeto.pasta)
    web = projeto.caminho("web")
    entradas: list[dict] = []
    usados: set[str] = set()
    for p in sorted(plano["itens"], key=lambda x: x.get("caminho", "")):
        if p["estado"] != "concluido" or not p.get("saidas"):
            continue
        item = por_item.get(p["item_inventario"])
        if not item:
            continue
        prefixo = f"build/convertido/{p['id']}/"
        for caminho_saida in p["saidas"]:
            if not caminho_saida.endswith(SUFIXO_BRUTA) or not (projeto.pasta / caminho_saida).is_file():
                continue
            rel = caminho_saida[len(prefixo):]
            bruta = json.loads((projeto.pasta / caminho_saida).read_text(encoding="utf-8"))
            aid = id_estavel("a", item["caminho"], rel)
            nome_arquivo = PurePosixPath(item["caminho"].split("!/")[-1]).stem
            base = slug(bruta["id_cena"] if bruta.get("id_cena") not in (None, "", "mapa") else nome_arquivo)
            id_cena = base if base not in usados else f"{base}-{aid[2:8]}"
            usados.add(id_cena)
            geo = _geometria(bruta, p, assets, item)
            cena = normalizar(bruta, assets, regras, ajustes, id_cena, geo)
            texto = json.dumps(cena, ensure_ascii=False, indent=2) + "\n"
            caminho_web = f"dados/cenas/{id_cena}-{aid[2:10]}.json"
            alvo = web / caminho_web
            if not alvo.is_file() or alvo.read_text(encoding="utf-8") != texto:
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_text(texto, encoding="utf-8")
            dados = texto.encode("utf-8")
            entradas.append({"id": aid, "caminho_web": caminho_web, "tipo": "mapa", "mime": "application/json",
                             "hash_sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados),
                             "origem": {"item_inventario": item["id"], "caminho": item["caminho"], "formato": p["formato_origem"], "conversor": p["conversor"]},
                             "metadados": {"extras": {"cena": id_cena, "dimensao": cena["dimensao"], **cena["estatisticas"]}}})
    return entradas


def _geometria(bruta: dict, p: dict, assets: list[dict], item: dict) -> str | None:
    """Geometria do mapa: glob declarado pelo conversor ou o modelo publicado pelo mesmo item do plano."""
    mesmo = [a for a in assets if a["origem"]["item_inventario"] == item["id"] and a["tipo"] == "modelo"]
    padrao = bruta.get("geometria_origem")
    if padrao:
        achados = [a for a in assets if a["tipo"] == "modelo" and (fnmatch.fnmatch(a["origem"]["caminho"].lower(), padrao.lower()) or fnmatch.fnmatch(a["caminho_web"].lower(), padrao.lower()))]
        if achados:
            return sorted(achados, key=lambda a: a["caminho_web"])[0]["id"]
    return mesmo[0]["id"] if mesmo else None


def registrar_ajuste(projeto_pasta: Path, ajuste: dict) -> dict:
    doc = ler_ajustes(projeto_pasta)
    ajuste = {**ajuste, "em": agora_iso()}
    doc["ajustes"].append(ajuste)
    gravar_json(Path(projeto_pasta) / "ajustes_cena.json", doc, "ajustes_cena")
    return ajuste


def registrar_regra(projeto_pasta: Path, regra: dict) -> dict:
    doc = ler_regras(projeto_pasta)
    doc["regras"].append(regra)
    gravar_json(Path(projeto_pasta) / "mapeamento_entidades.json", doc, "mapeamento_entidades")
    return regra


def cenas_publicadas(projeto) -> list[tuple[dict, dict]]:
    """[(entrada do manifesto, cena normalizada)] das cenas do projeto."""
    if not projeto.existe("manifesto"):
        return []
    saida = []
    for a in projeto.ler("manifesto")["assets"]:
        if a["tipo"] == "mapa" and a["caminho_web"].startswith("dados/cenas/"):
            arq = projeto.caminho("web") / a["caminho_web"]
            if arq.is_file():
                saida.append((a, json.loads(arq.read_text(encoding="utf-8"))))
    return saida
