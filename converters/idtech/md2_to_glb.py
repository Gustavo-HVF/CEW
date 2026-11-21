"""MD2 (modelos do Quake II) -> glTF 2.0 binario (.glb).

Estrutura (little-endian), como em qcommon/qfiles.h do codigo publicado pela id Software
(https://github.com/id-Software/Quake-2): dmdl_t com ident 'IDP2', versao 8 e 17 inteiros;
dstvert_t (s, t: short), dtriangle_t (index_xyz[3], index_st[3]: short), daliasframe_t
(scale[3], translate[3]: float, name[16], dtrivertx_t verts[]: byte v[3] + lightnormalindex).

Conversao:
- vertices = v * scale + translate, de Z para cima (Quake) para Y para cima (glTF), mao direita;
- unidades: 1 unidade do Quake ~ 1 polegada -> metros (opcao "escala", padrao 0.0254);
- cada quadro vira um morph target (deslocamento em relacao ao quadro 0); cada sequencia de
  quadros com o mesmo prefixo de nome (stand01, stand02... -> "stand") vira uma animacao glTF de
  pesos, a 10 quadros por segundo (o Quake II avanca as animacoes a 10 Hz); o FPS original fica
  em extras;
- normais calculadas da geometria do quadro 0 (a tabela de normais pre-calculadas do MD2 nao e
  usada); ordem dos vertices invertida por padrao (o glquake desenha com glCullFace(GL_FRONT),
  ou seja, a face visivel e a horaria) - opcao "inverter_faces".
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import math
import re
import struct

from converters.comum.binario import LeitorBinario, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.eixos import METROS_POR_POLEGADA, converter_ponto
from converters.comum.gltf import ConstrutorGltf

INFO = {
    "arquivo": "converters/idtech/md2_to_glb.py",
    "descricao": "Converte modelos MD2 (Quake II) em GLB com morph targets e animacoes por sequencia.",
    "formatos_entrada": ["idtech.quake2.md2"],
    "destino": "glb",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"escala\": 0.0254, \"fps\": 10, \"inverter_faces\": true, \"max_quadros\": 512}.",
}

LIMITES = {"vertices": 4096, "triangulos": 8192, "quadros": 1024, "st": 8192, "skins": 32}


def analisar(dados: bytes) -> dict:
    r = LeitorBinario(dados, "little")
    exigir(r.bytes_em(0, 4) == b"IDP2", "nao e MD2 (ident 'IDP2' ausente)")
    campos = [r.s32_em(4 * i) for i in range(1, 17)]
    (versao, larg_skin, alt_skin, tam_quadro, n_skins, n_xyz, n_st, n_tris, _n_gl, n_quadros,
     o_skins, o_st, o_tris, o_quadros, _o_gl, o_fim) = campos
    exigir(versao == 8, f"versao MD2 {versao} (esperado 8)")
    exigir(0 < n_xyz <= LIMITES["vertices"] and 0 < n_tris <= LIMITES["triangulos"], "contagens MD2 implausiveis")
    exigir(0 < n_quadros <= LIMITES["quadros"] and 0 <= n_st <= LIMITES["st"] and 0 <= n_skins <= LIMITES["skins"], "contagens MD2 implausiveis")
    exigir(tam_quadro == 40 + 4 * n_xyz, f"tamanho de quadro {tam_quadro} nao bate com {n_xyz} vertices")
    exigir(o_fim <= len(dados), "ofs_end passa do fim do arquivo")
    r.conferir(o_skins, 64 * n_skins, "skins")
    r.conferir(o_st, 4 * n_st, "coordenadas de textura")
    r.conferir(o_tris, 12 * n_tris, "triangulos")
    r.conferir(o_quadros, tam_quadro * n_quadros, "quadros")
    skins = [r.texto_fixo_em(o_skins + 64 * i, 64, "latin-1") for i in range(n_skins)]
    st = [(r.s16_em(o_st + 4 * i), r.s16_em(o_st + 4 * i + 2)) for i in range(n_st)]
    tris = []
    for i in range(n_tris):
        b = o_tris + 12 * i
        xyz = tuple(r.u16_em(b + 2 * k) for k in range(3))
        uv = tuple(r.u16_em(b + 6 + 2 * k) for k in range(3))
        exigir(all(v < n_xyz for v in xyz), f"triangulo {i} aponta para vertice inexistente")
        exigir(n_st == 0 or all(v < n_st for v in uv), f"triangulo {i} aponta para st inexistente")
        tris.append((xyz, uv))
    quadros = []
    for f in range(n_quadros):
        b = o_quadros + tam_quadro * f
        esc = struct.unpack_from("<3f", dados, b)
        trans = struct.unpack_from("<3f", dados, b + 12)
        nome = r.texto_fixo_em(b + 24, 16, "latin-1")
        vs = []
        for v in range(n_xyz):
            o = b + 40 + 4 * v
            vs.append(tuple(dados[o + k] * esc[k] + trans[k] for k in range(3)))
        quadros.append((nome, vs))
    return {"skin": (larg_skin, alt_skin), "skins": skins, "st": st, "tris": tris, "quadros": quadros}


def _sequencia(nome: str) -> str:
    m = re.match(r"^(.*?)(\d+)$", nome)
    return (m.group(1) if m and m.group(1) else nome) or "quadros"


def _normais(pos: list[tuple[float, float, float]], indices: list[int]) -> list[tuple[float, float, float]]:
    acc = [[0.0, 0.0, 0.0] for _ in pos]
    for t in range(0, len(indices), 3):
        a, b, c = (pos[indices[t + k]] for k in range(3))
        u = [b[i] - a[i] for i in range(3)]
        v = [c[i] - a[i] for i in range(3)]
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        for k in range(3):
            for i in range(3):
                acc[indices[t + k]][i] += n[i]
    saida = []
    for n in acc:
        m = math.sqrt(sum(x * x for x in n))
        saida.append((n[0] / m, n[1] / m, n[2] / m) if m > 1e-12 else (0.0, 1.0, 0.0))
    return saida


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    md = analisar(dados)
    escala = float(opcoes.get("escala", METROS_POR_POLEGADA))
    fps = float(opcoes.get("fps", 10))
    inverter = bool(opcoes.get("inverter_faces", True))
    max_q = int(opcoes.get("max_quadros", 512))
    quadros = md["quadros"][:max_q]
    if len(md["quadros"]) > max_q:
        esc.avisar(f"{len(md['quadros']) - max_q} quadros alem de max_quadros foram ignorados")
    larg, alt = md["skin"]
    # vertices unicos (indice xyz, indice st)
    mapa: dict[tuple[int, int], int] = {}
    chaves: list[tuple[int, int]] = []
    indices: list[int] = []
    for xyz, uv in md["tris"]:
        ordem = (0, 2, 1) if inverter else (0, 1, 2)
        for k in ordem:
            ch = (xyz[k], uv[k] if md["st"] else 0)
            if ch not in mapa:
                mapa[ch] = len(chaves)
                chaves.append(ch)
            indices.append(mapa[ch])

    def posicoes(vs):
        return [converter_ponto(vs[x], "z_up_rh", escala) for x, _ in chaves]

    base = posicoes(quadros[0][1])
    g = ConstrutorGltf()
    attrs = {
        "POSITION": g.accessor_float(base, "VEC3", min_max=True),
        "NORMAL": g.accessor_float(_normais(base, indices), "VEC3"),
    }
    if md["st"] and larg > 0 and alt > 0:
        attrs["TEXCOORD_0"] = g.accessor_float([(md["st"][s][0] / larg, md["st"][s][1] / alt) for _, s in chaves], "VEC2")
    alvos, nomes = [], []
    for nome, vs in quadros[1:]:
        p = posicoes(vs)
        delta = [(a[0] - b[0], a[1] - b[1], a[2] - b[2]) for a, b in zip(p, base)]
        alvos.append({"POSITION": g.accessor_float(delta, "VEC3", min_max=True)})
        nomes.append(nome)
    mat = g.material("skin", extras={"skins_md2": md["skins"], "tamanho_skin_px": [larg, alt]})
    malha = g.malha("md2", attrs, g.accessor_indices(indices), mat, alvos or None, nomes or None)
    no = g.no("md2", malha, extras={"origem": "MD2", "escala_metros": escala})
    # animacoes por sequencia
    seqs: dict[str, list[int]] = {}
    for i, (nome, _) in enumerate(quadros):
        seqs.setdefault(_sequencia(nome), []).append(i)
    n_alvos = len(alvos)
    if n_alvos:
        for seq, ids in seqs.items():
            tempos, pesos = [], []
            for k, q in enumerate(ids):
                tempos.append(k / fps)
                w = [0.0] * n_alvos
                if q > 0:
                    w[q - 1] = 1.0
                pesos.append(w)
            if len(tempos) == 1:  # uma chave so: repete para a animacao ter duracao
                tempos.append(1 / fps)
                pesos.append(pesos[0])
            g.animacao_pesos(seq, no, tempos, pesos, "LINEAR", extras={"fps_original": fps})
    glb = g.glb()
    meta = {"escala_metros": escala, "eixo_para_cima": "Y", "vertices": len(chaves), "ossos": 0, "fps_original": fps,
            "extras": {"triangulos": len(md["tris"]), "quadros": len(quadros), "animacoes": sorted(seqs), "skins": md["skins"]}}
    esc.gravar("modelo.glb", glb, "modelo", "glb", meta)
    return {"vertices_originais": len(md["quadros"][0][1]), "vertices_gltf": len(chaves), "triangulos": len(md["tris"]), "quadros": len(quadros), "animacoes": len(seqs)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
