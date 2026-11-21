"""Quake BSP (versao 29) -> cena bruta: entidades posicionadas do mapa (monstros, itens, luzes, spawn...).

Estrutura conferida no codigo publicado pela id Software (https://github.com/id-Software/Quake):
- WinQuake/bspfile.h: BSPVERSION 29, HEADER_LUMPS 15, lump_t {int fileofs, filelen}, LUMP_ENTITIES = 0;
- WinQuake/pr_edict.c (ED_ParseEdict): o lump de entidades e texto com blocos { "chave" "valor" ... };
  a chave "angle" N vira "angles" "0 N 0" (arfagem, guinada, rolagem), guinada em torno de Z.
Quake: Z para cima, mao direita, 1 unidade ~ 1 polegada (0,0254 m), guinada anti-horaria vista de cima.
"angle" -1/-2 em portas e plataformas e direcao (cima/baixo), nao rotacao.
A geometria do mapa (faces do BSP) nao e convertida por esta receita.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import json

from converters.comum.binario import ErroFormato, LeitorBinario, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "cookbook/idtech/bsp_entidades_to_cena.py",
    "descricao": "Extrai as entidades posicionadas de um BSP do Quake (v29) para uma cena bruta do CEW.",
    "formatos_entrada": ["idtech.quake.bsp"],
    "destino": "cena (json)",
    "versao": "1.0",
    "papel": "conversor",
}

LIMITE_TEXTO = 16 * 1024 * 1024


def tokens(texto: str):
    """Tokenizador no espirito do COM_Parse: strings entre aspas, chaves e comentarios //."""
    i, n = 0, len(texto)
    while i < n:
        c = texto[i]
        if c.isspace():
            i += 1
        elif texto.startswith("//", i):
            j = texto.find("\n", i)
            i = n if j < 0 else j + 1
        elif c in "{}":
            yield c
            i += 1
        elif c == '"':
            j = texto.find('"', i + 1)
            if j < 0:
                raise ErroFormato("string sem aspas de fechamento no lump de entidades")
            yield texto[i + 1 : j]
            i = j + 1
        else:
            j = i
            while j < n and not texto[j].isspace() and texto[j] not in '{}"':
                j += 1
            yield texto[i:j]
            i = j


def entidades(texto: str) -> list[dict[str, str]]:
    saida, atual, chave = [], None, None
    for t in tokens(texto):
        if t == "{":
            exigir(atual is None, "chave '{' dentro de outra entidade")
            atual, chave = {}, None
        elif t == "}":
            exigir(atual is not None and chave is None, "entidade mal fechada")
            saida.append(atual)
            atual = None
        else:
            exigir(atual is not None, f"token fora de entidade: {t[:30]!r}")
            if chave is None:
                chave = t
            else:
                atual[chave] = t
                chave = None
    exigir(atual is None, "fim do lump com entidade aberta")
    return saida


def _vec(s: str | None, n: int = 3) -> list[float] | None:
    if not s:
        return None
    try:
        v = [float(x) for x in s.split()]
    except ValueError:
        return None
    return v if len(v) == n else None


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "little")
    exigir(r.s32_em(0, "versao") == 29, "nao e BSP do Quake (versao 29)")
    ofs, tam = r.s32_em(4, "lump 0"), r.s32_em(8, "lump 0")
    exigir(0 <= tam <= LIMITE_TEXTO, "lump de entidades com tamanho implausivel")
    bruto = r.bytes_em(ofs, tam, "lump de entidades").split(b"\x00", 1)[0]
    ents = entidades(bruto.decode("latin-1"))
    nome_mapa = opcoes.get("id_cena") or "mapa"
    mundo = {}
    lista = []
    for i, e in enumerate(ents):
        classe = e.get("classname", "")
        if classe == "worldspawn":
            mundo = e
            continue
        origem = _vec(e.get("origin"))
        props = {k: v for k, v in e.items() if k not in ("classname", "origin", "angle", "angles", "targetname")}
        ang = _vec(e.get("angles"))
        if ang is None and e.get("angle") is not None:
            try:
                a = float(e["angle"])
            except ValueError:
                a = 0.0
            if a in (-1.0, -2.0):
                props["direcao"] = "cima" if a == -1.0 else "baixo"
                a = 0.0
            ang = [0.0, a, 0.0]
        ent = {"id": f"bruta_{len(lista)}", "id_original": None, "nome": e.get("targetname"), "tipo_original": classe or "sem_classname",
               "categoria": None, "posicao": origem or [0.0, 0.0, 0.0], "angulos_graus": ang or [0.0, 0.0, 0.0]}
        if origem is None:
            ent["posicao_estimada"] = True  # entidade de brush ("model" "*n"): sem origem propria
        modelo = e.get("model")
        if modelo and not modelo.startswith("*"):
            ent["modelo_original"] = modelo
        if props:
            ent["propriedades"] = props
        lista.append(ent)
    cena = {"schema_version": "1.0", "gerado_por": "cew", "id_cena": nome_mapa, "nome": mundo.get("message") or nome_mapa,
            "origem": opcoes.get("origem", ""), "estado": "bruta", "dimensao": "3d",
            "sistema_coordenadas": {"eixo_para_cima": "Z", "mao": "direita", "metros_por_unidade": float(opcoes.get("metros_por_unidade", 0.0254)), "rotacao": "anti_horaria"},
            "entidades": lista, "estatisticas": {"worldspawn": mundo, "entidades_no_lump": len(ents)}}
    try:
        from cew.esquemas import validar

        validar(cena, "dados/cena")
    except ImportError:  # pragma: no cover
        pass
    esc.gravar("cena_bruta.json", (json.dumps(cena, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), "mapa", "cena_bruta",
               {"extras": {"entidades": len(lista)}})
    return {"entidades": len(lista)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
