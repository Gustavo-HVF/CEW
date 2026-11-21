"""Gera as amostras sinteticas de tests/fixtures/ de forma deterministica.

Nenhuma amostra vem de jogo comercial: cada arquivo e montado aqui a partir da descricao publica
do formato. Os testes conferem que rodar este gerador de novo produz exatamente os mesmos bytes.

Uso: python tests/fixtures/gerar_fixtures.py [--conferir]
"""

from __future__ import annotations

import io
import json
import math
import struct
import sys
import zipfile
import zlib
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from converters.comum.audio import Pcm, wav_bytes  # noqa: E402
from converters.comum.compressao import yaz0_compactar  # noqa: E402

PASTA = Path(__file__).resolve().parent / "amostras"


# ----------------------------------------------------------------------- imagem de referencia
def imagem_ref(w: int, h: int, alfa: bool = True) -> list[tuple[int, int, int, int]]:
    """Gradiente com quadrantes; valores escolhidos para sobreviver a quantizacao de 4/5 bits."""
    px = []
    for y in range(h):
        for x in range(w):
            r = (x * 255) // max(1, w - 1)
            g = (y * 255) // max(1, h - 1)
            b = 255 if (x < w // 2) ^ (y < h // 2) else 0
            a = 255 if not alfa else (255 if x < w // 2 else 136)
            px.append((r, g, b, a))
    return px


# --------------------------------------------------------------------------- encoders GX (testes)
def _q(v: int, bits: int) -> int:
    return (v * ((1 << bits) - 1) + 127) // 255


def gx_codificar(px, w: int, h: int, fmt: str) -> bytes:
    blocos = {"I8": (8, 4), "IA8": (4, 4), "RGB565": (4, 4), "RGB5A3": (4, 4), "RGBA32": (4, 4), "I4": (8, 8), "CMPR": (8, 8), "C8": (8, 4)}
    bw, bh = blocos[fmt]
    out = bytearray()

    def p(x, y):
        return px[y * w + x] if x < w and y < h else (0, 0, 0, 0)

    for by in range(0, h, bh):
        for bx in range(0, w, bw):
            if fmt == "RGBA32":
                ar, gb = bytearray(), bytearray()
                for i in range(16):
                    r, g, b, a = p(bx + i % 4, by + i // 4)
                    ar += bytes([a, r])
                    gb += bytes([g, b])
                out += ar + gb
                continue
            if fmt == "CMPR":
                for sub in range(4):
                    sx, sy = bx + (sub % 2) * 4, by + (sub // 2) * 4
                    cores = sorted({p(sx + i % 4, sy + i // 4)[:3] for i in range(16)})
                    c0 = cores[-1]
                    c1 = cores[0]
                    e0 = _q(c0[0], 5) << 11 | _q(c0[1], 6) << 5 | _q(c0[2], 5)
                    e1 = _q(c1[0], 5) << 11 | _q(c1[1], 6) << 5 | _q(c1[2], 5)
                    if e0 < e1:
                        e0, e1 = e1, e0
                    elif e0 == e1:
                        e1 = max(0, e0 - 1)
                    out += struct.pack(">HH", e0, e1)
                    for y in range(4):
                        linha = 0
                        for x in range(4):
                            c = p(sx + x, sy + y)[:3]
                            idx = 0 if sum(c) >= sum(c0 + c1) / 2 else 1
                            linha |= idx << (6 - 2 * x)
                        out.append(linha)
                continue
            for i in range(bw * bh):
                r, g, b, a = p(bx + i % bw, by + i // bw)
                if fmt == "I8":
                    out.append(r)
                elif fmt == "C8":
                    out.append(r & 0x0F)
                elif fmt == "I4":
                    v = _q(r, 4)
                    if i % 2 == 0:
                        out.append(v << 4)
                    else:
                        out[-1] |= v
                elif fmt == "IA8":
                    out += bytes([a, r])
                elif fmt == "RGB565":
                    out += struct.pack(">H", _q(r, 5) << 11 | _q(g, 6) << 5 | _q(b, 5))
                elif fmt == "RGB5A3":
                    if a == 255:
                        v = 0x8000 | _q(r, 5) << 10 | _q(g, 5) << 5 | _q(b, 5)
                    else:
                        v = _q(a, 3) << 12 | _q(r, 4) << 8 | _q(g, 4) << 4 | _q(b, 4)
                    out += struct.pack(">H", v)
    return bytes(out)


def tpl(imagens: list[tuple[str, int, int, bytes, bytes | None, int]]) -> bytes:
    """imagens: (formato, largura, altura, dados, paleta_bytes|None, formato_paleta)."""
    cod = {"I4": 0, "I8": 1, "IA4": 2, "IA8": 3, "RGB565": 4, "RGB5A3": 5, "RGBA32": 6, "C4": 8, "C8": 9, "CMPR": 0xE}
    n = len(imagens)
    cab = struct.pack(">III", 0x0020AF30, n, 0x0C)
    tabela_tam = 8 * n
    pos = 0x0C + tabela_tam
    cabs, pals, corpo = bytearray(), bytearray(), bytearray()
    off_cabs = pos
    off_pals = off_cabs + 0x24 * n
    pal_offsets = []
    p_pos = off_pals
    for f, w, h, d, pal, fpal in imagens:
        pal_offsets.append(p_pos if pal else 0)
        if pal:
            p_pos += 0x0C
    dados_ini = (p_pos + 31) // 32 * 32
    tabela = bytearray()
    d_pos = dados_ini
    for i, (f, w, h, d, pal, fpal) in enumerate(imagens):
        tabela += struct.pack(">II", off_cabs + 0x24 * i, pal_offsets[i])
        cabs += struct.pack(">HHIIIIIIfBBBB", h, w, cod[f], d_pos, 0, 0, 1, 1, 0.0, 0, 0, 0, 0)
        corpo += d
        d_pos += len(d)
        if pal:
            pals += struct.pack(">HBBII", len(pal) // 2, 0, 0, fpal, d_pos)
            corpo += pal
            d_pos += len(pal)
    preenchimento = b"\x00" * (dados_ini - p_pos)
    return cab + tabela + cabs + pals + preenchimento + corpo


# ----------------------------------------------------------------------------- conteineres
def u8(arquivos: dict[str, bytes]) -> bytes:
    """Monta U8 com pastas (ordem: pasta antes do conteudo)."""
    arvore: dict = {}
    for caminho, dados in sorted(arquivos.items()):
        no = arvore
        partes = caminho.split("/")
        for p in partes[:-1]:
            no = no.setdefault(p, {})
        no[partes[-1]] = dados
    nos, nomes = [], bytearray(b"\x00")
    corpos: list[tuple[int, bytes]] = []

    def visitar(d: dict, pai: int):
        for nome in sorted(d):
            off_nome = len(nomes)
            nomes.extend(nome.encode() + b"\x00")
            if isinstance(d[nome], dict):
                idx = len(nos)
                nos.append([1, off_nome, pai, 0])
                visitar(d[nome], idx)
                nos[idx][3] = len(nos)
            else:
                nos.append([0, off_nome, 0, len(d[nome])])
                corpos.append((len(nos) - 1, d[nome]))

    nos.append([1, 0, 0, 0])
    visitar(arvore, 0)
    nos[0][3] = len(nos)
    raiz = 0x20
    tam_nos = len(nos) * 12 + len(nomes)
    off_dados = (raiz + tam_nos + 31) // 32 * 32
    pos = off_dados
    dados = bytearray()
    for idx, corpo in corpos:
        nos[idx][2] = pos
        dados += corpo
        pad = (32 - len(dados) % 32) % 32
        dados += b"\x00" * pad
        pos = off_dados + len(dados)
    bloco = b"".join(struct.pack(">II", t << 24 | n, a) + struct.pack(">I", b) for t, n, a, b in nos) + bytes(nomes)
    cab = struct.pack(">IIII", 0x55AA382D, raiz, tam_nos, off_dados) + b"\x00" * 16
    return cab + bloco + b"\x00" * (off_dados - raiz - tam_nos) + bytes(dados)


def sarc(arquivos: dict[str, bytes], ordem: str = "little") -> bytes:
    p = "<" if ordem == "little" else ">"
    chave = 0x65

    def h(nome: str) -> int:
        v = 0
        for c in nome.encode():
            v = (v * chave + c) & 0xFFFFFFFF
        return v

    itens = sorted(arquivos.items(), key=lambda kv: h(kv[0]))
    nomes = bytearray()
    attrs = []
    for nome, _ in itens:
        attrs.append(0x01000000 | (len(nomes) // 4))
        nomes += nome.encode() + b"\x00"
        nomes += b"\x00" * ((4 - len(nomes) % 4) % 4)
    dados = bytearray()
    faixas = []
    for _, corpo in itens:
        dados += b"\x00" * ((8 - len(dados) % 8) % 8)
        faixas.append((len(dados), len(dados) + len(corpo)))
        dados += corpo
    sfat = b"SFAT" + struct.pack(p + "HHI", 0x0C, len(itens), chave)
    for (nome, _), attr, (ini, fim) in zip(itens, attrs, faixas):
        sfat += struct.pack(p + "IIII", h(nome), attr, ini, fim)
    sfnt = b"SFNT" + struct.pack(p + "HH", 8, 0) + bytes(nomes)
    off_dados = 0x14 + len(sfat) + len(sfnt)
    off_dados = (off_dados + 0xFF) // 0x100 * 0x100
    bom = b"\xff\xfe" if ordem == "little" else b"\xfe\xff"
    total = off_dados + len(dados)
    cab = b"SARC" + struct.pack(p + "H", 0x14) + bom + struct.pack(p + "IIHH", total, off_dados, 0x0100, 0)
    corpo = cab + sfat + sfnt
    return corpo + b"\x00" * (off_dados - len(corpo)) + bytes(dados)


def pak(arquivos: dict[str, bytes]) -> bytes:
    corpo = bytearray()
    entradas = []
    for nome, d in sorted(arquivos.items()):
        entradas.append((nome, 12 + len(corpo), len(d)))
        corpo += d
    diretorio = b"".join(n.encode().ljust(56, b"\x00") + struct.pack("<ii", o, t) for n, o, t in entradas)
    return b"PACK" + struct.pack("<ii", 12 + len(corpo), len(diretorio)) + bytes(corpo) + diretorio


def vpk(arquivos: dict[str, bytes]) -> bytes:
    """VPK v2 com todos os dados no proprio arquivo (indice 0x7FFF)."""
    grupos: dict[str, dict[str, list[tuple[str, bytes]]]] = {}
    for caminho, d in sorted(arquivos.items()):
        pasta, _, arq = caminho.rpartition("/")
        nome, _, ext = arq.rpartition(".")
        grupos.setdefault(ext or " ", {}).setdefault(pasta or " ", []).append((nome, d))
    arvore, dados = bytearray(), bytearray()
    for ext in sorted(grupos):
        arvore += ext.encode() + b"\x00"
        for pasta in sorted(grupos[ext]):
            arvore += pasta.encode() + b"\x00"
            for nome, d in grupos[ext][pasta]:
                arvore += nome.encode() + b"\x00"
                arvore += struct.pack("<IHHIIH", zlib.crc32(d) & 0xFFFFFFFF, 0, 0x7FFF, len(dados), len(d), 0xFFFF)
                dados += d
            arvore += b"\x00"
        arvore += b"\x00"
    arvore += b"\x00"
    cab = struct.pack("<IIIIIII", 0x55AA1234, 2, len(arvore), len(dados), 0, 0, 0)
    return cab + bytes(arvore) + bytes(dados)


# -------------------------------------------------------------------------------- Sony
def tim_4bpp(px_indices: list[int], w: int, h: int, cluts: list[list[int]]) -> bytes:
    cores = len(cluts[0])
    clut_dados = b"".join(struct.pack("<H", c) for cl in cluts for c in cl)
    clut = struct.pack("<IHHHH", 12 + len(clut_dados), 0, 480, cores, len(cluts)) + clut_dados
    linha = bytearray()
    for y in range(h):
        for x in range(0, w, 2):
            a, b = px_indices[y * w + x], px_indices[y * w + x + 1]
            linha.append(a | (b << 4))
    img = struct.pack("<IHHHH", 12 + len(linha), 320, 0, w // 4, h) + bytes(linha)
    return struct.pack("<II", 0x10, 0x8) + clut + img


def tim_16bpp(cores: list[int], w: int, h: int) -> bytes:
    pix = b"".join(struct.pack("<H", c) for c in cores)
    img = struct.pack("<IHHHH", 12 + len(pix), 0, 0, w, h) + pix
    return struct.pack("<II", 0x10, 0x2) + img


def vag_com_loop() -> bytes:
    """6 quadros PS-ADPCM: silencio, rampa (filtro 0), inicio do loop, meio, fim do loop."""
    quadros = [bytes(16)]  # quadro inicial zerado, como no padrao

    def q(filtro: int, desloc: int, flags: int, nibbles: list[int]) -> bytes:
        b = bytearray([(filtro << 4) | desloc, flags])
        for i in range(0, 28, 2):
            b.append((nibbles[i] & 0xF) | ((nibbles[i + 1] & 0xF) << 4))
        return bytes(b)

    rampa = [(i % 8) for i in range(28)]
    quadros.append(q(0, 4, 0, rampa))
    quadros.append(q(1, 6, 0x04, [(-i) % 16 for i in range(28)]))  # inicio do loop
    quadros.append(q(2, 8, 0x00, [3] * 28))
    quadros.append(q(0, 12, 0x03, [7, 9] * 14))  # fim do loop
    corpo = b"".join(quadros)
    cab = b"VAGp" + struct.pack(">III", 0x20, 0, len(corpo)) + struct.pack(">I", 22050) + b"\x00" * 12 + b"cew_teste".ljust(16, b"\x00")
    return cab + corpo


# ---------------------------------------------------------------------------- id Tech MD2
def md2_tetraedro() -> bytes:
    """Tetraedro com 3 quadros ('stand01', 'stand02', 'run1') e skin 64x64."""
    xyz = [(0, 0, 0), (255, 0, 0), (0, 255, 0), (0, 0, 255)]
    st = [(0, 0), (63, 0), (0, 63), (63, 63)]
    tris = [((0, 2, 1), (0, 2, 1)), ((0, 1, 3), (0, 1, 3)), ((0, 3, 2), (0, 3, 2)), ((1, 2, 3), (1, 2, 3))]
    quadros = []
    for nome, desloc in (("stand01", 0.0), ("stand02", 4.0), ("run1", -8.0)):
        q = struct.pack("<3f", 0.125, 0.125, 0.125) + struct.pack("<3f", desloc, 0.0, -16.0) + nome.encode().ljust(16, b"\x00")
        q += b"".join(bytes([*v, 0]) for v in xyz)
        quadros.append(q)
    skins = [b"models/cew/skin.pcx".ljust(64, b"\x00")]
    corpo_st = b"".join(struct.pack("<hh", *s) for s in st)
    corpo_tris = b"".join(struct.pack("<6H", *a, *b) for a, b in tris)
    tam_quadro = 40 + 4 * len(xyz)
    o_skins = 68
    o_st = o_skins + 64 * len(skins)
    o_tris = o_st + len(corpo_st)
    o_quadros = o_tris + len(corpo_tris)
    o_gl = o_quadros + tam_quadro * len(quadros)
    o_fim = o_gl
    cab = b"IDP2" + struct.pack("<16i", 8, 64, 64, tam_quadro, len(skins), len(xyz), len(st), len(tris), 0, len(quadros), o_skins, o_st, o_tris, o_quadros, o_gl, o_fim)
    return cab + b"".join(skins) + corpo_st + corpo_tris + b"".join(quadros)


# ---------------------------------------------------------------------------------- PC
def dds_rgba(px, w: int, h: int) -> bytes:
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<IIIIIII", cab, 4, 124, 0x100F, h, w, w * 4, 0, 1)
    struct.pack_into("<IIIIIIII", cab, 76, 32, 0x41, 0, 32, 0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000)
    struct.pack_into("<I", cab, 108, 0x1000)
    corpo = b"".join(bytes([b, g, r, a]) for r, g, b, a in px)
    return bytes(cab) + corpo


def dds_dxt1(w: int, h: int) -> bytes:
    """Blocos com cores puras alternadas (indices 0 e 1), exatos apos 565."""
    cab = bytearray(128)
    cab[0:4] = b"DDS "
    struct.pack_into("<IIIIIII", cab, 4, 124, 0x81007, h, w, (w // 4) * (h // 4) * 8, 0, 1)
    struct.pack_into("<IIII", cab, 76, 32, 0x4, 0, 0)
    cab[84:88] = b"DXT1"
    struct.pack_into("<I", cab, 108, 0x1000)
    blocos = bytearray()
    for by in range(h // 4):
        for bx in range(w // 4):
            c0, c1 = (0xF800, 0x001F) if (bx + by) % 2 == 0 else (0x07E0, 0xFFE0)
            blocos += struct.pack("<HHI", c0, c1, 0x55555555 if bx % 2 else 0x00000000)
    return bytes(cab) + bytes(blocos)


def tga_rle(px, w: int, h: int) -> bytes:
    cab = struct.pack("<BBBHHBHHHHBB", 0, 0, 10, 0, 0, 0, 0, 0, w, h, 32, 0x28)
    corpo = bytearray()
    i = 0
    while i < len(px):
        n = 1
        while i + n < len(px) and n < 128 and px[i + n] == px[i]:
            n += 1
        r, g, b, a = px[i]
        if n > 1:
            corpo += bytes([0x80 | (n - 1), b, g, r, a])
            i += n
        else:
            corpo += bytes([0, b, g, r, a])
            i += 1
    return cab + bytes(corpo)


def wav_tom(segundos: float, taxa: int = 22050, loop: tuple[int, int] | None = None) -> bytes:
    n = int(segundos * taxa)
    amostras = [int(12000 * math.sin(2 * math.pi * 440 * i / taxa)) for i in range(n)]
    return wav_bytes(Pcm(taxa, 1, [amostras], loop))


ENTIDADES_BSP = """{
"classname" "worldspawn"
"message" "Fase de Teste do CEW"
"wad" "gfx/base.wad"
}
{
"classname" "info_player_start"
"origin" "0 0 24"
"angle" "90"
}
{
"classname" "monster_ogre"
"origin" "256 128 24"
"angle" "180"
}
{
"classname" "monster_tetra"
"origin" "-64 32 0"
}
{
"classname" "light"
"origin" "0 0 128"
"light" "300"
}
{
"classname" "item_health"
"origin" "128 -64 16"
"spawnflags" "1"
}
// porta que sobe (angle -1) e o gatilho que a abre
{
"classname" "func_door"
"model" "*1"
"angle" "-1"
"targetname" "porta1"
}
{
"classname" "trigger_once"
"model" "*2"
"target" "porta1"
}
"""


def bsp_com_entidades() -> bytes:
    """BSP v29 so com o lump de entidades preenchido (os outros 14 lumps vazios)."""
    texto = ENTIDADES_BSP.encode("latin-1") + b"\x00"
    inicio = 4 + 15 * 8
    lumps = [(inicio, len(texto))] + [(inicio + len(texto), 0)] * 14
    return struct.pack("<i", 29) + b"".join(struct.pack("<ii", o, t) for o, t in lumps) + texto


def tiled_fase() -> bytes:
    w, h = 10, 8
    chao = [1 if y == h - 1 else 0 for y in range(h) for x in range(w)]
    mapa = {
        "type": "map", "version": "1.10", "tiledversion": "1.11.0", "orientation": "orthogonal", "renderorder": "right-down",
        "width": w, "height": h, "tilewidth": 16, "tileheight": 16, "infinite": False, "nextlayerid": 5, "nextobjectid": 7,
        "properties": [{"name": "nome", "type": "string", "value": "floresta"}],
        "tilesets": [{"firstgid": 1, "source": "terreno.tsx"}],
        "layers": [
            {"id": 1, "name": "chao", "type": "tilelayer", "width": w, "height": h, "data": chao, "visible": True, "opacity": 1, "x": 0, "y": 0},
            {"id": 2, "name": "objetos", "type": "objectgroup", "visible": True, "opacity": 1, "x": 0, "y": 0, "draworder": "topdown", "objects": [
                {"id": 1, "name": "arvore grande", "type": "tree", "gid": 3, "x": 32, "y": 112, "width": 16, "height": 32, "rotation": 0, "visible": True},
                {"id": 2, "name": "", "type": "pillar", "x": 64, "y": 80, "width": 16, "height": 32, "rotation": 0, "visible": True},
                {"id": 3, "name": "slime1", "type": "enemy_slime", "point": True, "x": 120, "y": 104, "width": 0, "height": 0, "rotation": 0, "visible": True,
                 "properties": [{"name": "vida", "type": "int", "value": 3}, {"name": "patrulha_px", "type": "float", "value": 48.0}]},
                {"id": 4, "name": "inicio", "type": "spawn", "point": True, "x": 16, "y": 104, "width": 0, "height": 0, "rotation": 0, "visible": True},
                {"id": 5, "name": "arbusto", "x": 90, "y": 100, "width": 10, "height": 12, "rotation": 0, "visible": True}]},
            {"id": 3, "name": "decor", "type": "group", "offsetx": 4, "offsety": -2, "visible": True, "opacity": 1, "layers": [
                {"id": 4, "name": "flores", "type": "objectgroup", "visible": True, "opacity": 1, "x": 0, "y": 0, "objects": [
                    {"id": 6, "name": "flor", "type": "flower", "x": 140, "y": 110, "width": 8, "height": 8, "rotation": 45, "visible": True}]}]},
        ],
    }
    return (json.dumps(mapa, ensure_ascii=False, indent=1) + "\n").encode("utf-8")


def texto_sjis() -> bytes:
    linhas = ["こんにちは、世界！", "CEW\x01テスト\x0aです", "Fase 1 - Floresta"]
    return b"\x00".join(s.encode("cp932") for s in linhas) + b"\x00"


def zip_exemplo() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for nome, conteudo in (("dados/config.json", b'{"vidas": 3}\n'), ("leia.txt", b"ola\n")):
            info = zipfile.ZipInfo(nome, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, conteudo)
    return buf.getvalue()


# -------------------------------------------------------------------------------- todas
def todas() -> dict[str, bytes]:
    w = h = 8
    ref = imagem_ref(w, h)
    ref_opaca = imagem_ref(w, h, alfa=False)
    paleta_c8 = b"".join(struct.pack(">H", 0x8000 | (k << 10) | (k << 5) | k) for k in range(16))
    a: dict[str, bytes] = {}
    a["nintendo/texturas.tpl"] = tpl([
        ("RGBA32", w, h, gx_codificar(ref, w, h, "RGBA32"), None, 0),
        ("RGB5A3", w, h, gx_codificar(ref, w, h, "RGB5A3"), None, 0),
        ("RGB565", w, h, gx_codificar(ref_opaca, w, h, "RGB565"), None, 0),
        ("IA8", w, h, gx_codificar(ref, w, h, "IA8"), None, 0),
        ("I8", w, h, gx_codificar(ref_opaca, w, h, "I8"), None, 0),
        ("I4", w, h, gx_codificar(ref_opaca, w, h, "I4"), None, 0),
        ("CMPR", w, h, gx_codificar(ref_opaca, w, h, "CMPR"), None, 0),
        ("C8", w, h, gx_codificar(ref_opaca, w, h, "C8"), paleta_c8, 2),
    ])
    a["nintendo/arquivo.arc"] = u8({"texturas/fundo.tpl": a["nintendo/texturas.tpl"], "leia.txt": b"conteudo U8\n", "dados/vazio/x.bin": b"\x01\x02\x03"})
    a["nintendo/arquivo.szs"] = yaz0_compactar(a["nintendo/arquivo.arc"])
    a["nintendo/pacote.sarc"] = sarc({"Model/cubo.bin": b"\x00" * 40 + b"cubo", "Tex/a.tpl": a["nintendo/texturas.tpl"], "leia.txt": b"SARC\n"})
    a["sony/imagem4.tim"] = tim_4bpp([(x + y) % 16 for y in range(8) for x in range(8)], 8, 8,
                                     [[0] + [0x8000 | (k << 10) | k for k in range(1, 16)], [k << 5 for k in range(16)]])
    a["sony/imagem16.tim"] = tim_16bpp([((x * 4) & 0x1F) | (((y * 4) & 0x1F) << 5) | 0x8000 for y in range(8) for x in range(8)], 8, 8)
    a["sony/som.vag"] = vag_com_loop()
    a["idtech/pak0.pak"] = pak({"maps/e1m1.bsp": b"\x1d\x00\x00\x00" + b"\x00" * 60, "progs/tetra.md2": md2_tetraedro()})
    a["idtech/tetra.md2"] = md2_tetraedro()
    a["valve/pak01_dir.vpk"] = vpk({"materials/brick.vtf": b"VTF\x00" + b"\x00" * 28, "scripts/game.txt": b"\"game\" {}\n", "leia.txt": b"VPK\n"})
    a["generico/rgba.dds"] = dds_rgba(ref, w, h)
    a["generico/dxt1.dds"] = dds_dxt1(8, 8)
    a["generico/imagem.tga"] = tga_rle(ref, w, h)
    a["generico/musica_loop.wav"] = wav_tom(2.5, taxa=11025, loop=(11025, 27562))
    a["generico/efeito.wav"] = wav_tom(0.25)
    a["generico/pacote.zip"] = zip_exemplo()
    a["dados/textos_sjis.bin"] = texto_sjis()
    a["idtech/mapa.bsp"] = bsp_com_entidades()
    a["generico/fase.tmj"] = tiled_fase()
    a["desconhecido/misterio.xyz"] = b"QZX1" + struct.pack(">IHH", 3, 16, 16) + bytes(range(64))
    from converters.comum.imagem import Imagem, png_bytes
    a["web/pronto.png"] = png_bytes(Imagem(2, 2, bytearray([255, 0, 0, 255] * 4)))
    return a


def referencias() -> dict:
    w = h = 8
    return {"imagem_ref_8x8": imagem_ref(w, h), "imagem_ref_opaca_8x8": imagem_ref(w, h, alfa=False)}


def main(argv: list[str]) -> int:
    conferir = "--conferir" in argv
    erros = 0
    for rel, dados in sorted(todas().items()):
        destino = PASTA / rel
        if conferir:
            if not destino.is_file() or destino.read_bytes() != dados:
                print(f"DIFERENTE: {rel}")
                erros += 1
        else:
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_bytes(dados)
    ref = PASTA / "referencias.json"
    texto = json.dumps(referencias(), separators=(",", ":")) + "\n"
    if conferir:
        if not ref.is_file() or ref.read_text() != texto:
            print("DIFERENTE: referencias.json")
            erros += 1
    else:
        ref.write_text(texto)
    print("ok" if not erros else f"{erros} diferencas")
    return 1 if erros else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
