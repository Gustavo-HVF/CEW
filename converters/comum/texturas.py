"""Decodificacao de formatos de textura de GPU para RGBA 8 bits.

- GameCube/Wii (GX): I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA32, C4, C8, C14X2 e CMPR, todos
  em blocos ("tiling") e big-endian. Referencias publicas: YAGCD e wiki.tockdom.com
  ("Image Formats"); a implementacao segue a descricao desses documentos.
- BC1/BC2/BC3 (DXT1/DXT3/DXT5), little-endian, usados em DDS no PC.

Interpolacao de cores do CMPR/BC1: regra padrao S3TC (2/3 + 1/3). O hardware do GameCube pode
diferir em 1-2 niveis por canal; a verificacao compara com tolerancia.
"""

from __future__ import annotations

import struct
from typing import Callable, Sequence

from .binario import ErroFormato
from .cores import exp3, exp4, ia8, rgb5a3, rgb565
from .imagem import Imagem

Cor = tuple[int, int, int, int]

GX_FORMATOS = {
    0x0: "I4", 0x1: "I8", 0x2: "IA4", 0x3: "IA8", 0x4: "RGB565", 0x5: "RGB5A3", 0x6: "RGBA32",
    0x8: "C4", 0x9: "C8", 0xA: "C14X2", 0xE: "CMPR",
}
# (largura do bloco, altura do bloco, bits por pixel)
GX_BLOCOS = {
    "I4": (8, 8, 4), "I8": (8, 4, 8), "IA4": (8, 4, 8), "IA8": (4, 4, 16), "RGB565": (4, 4, 16),
    "RGB5A3": (4, 4, 16), "RGBA32": (4, 4, 32), "C4": (8, 8, 4), "C8": (8, 4, 8), "C14X2": (4, 4, 16),
    "CMPR": (8, 8, 4),
}
GX_PALETAS = {0: "IA8", 1: "RGB565", 2: "RGB5A3"}


def gx_tamanho_dados(nome: str, largura: int, altura: int) -> int:
    bw, bh, bpp = GX_BLOCOS[nome]
    blocos_x = (largura + bw - 1) // bw
    blocos_y = (altura + bh - 1) // bh
    return blocos_x * blocos_y * bw * bh * bpp // 8


def decodificar_paleta_gx(dados: bytes, formato_paleta: int, quantidade: int) -> list[Cor]:
    nome = GX_PALETAS.get(formato_paleta)
    if nome is None:
        raise ErroFormato(f"formato de paleta GX desconhecido: {formato_paleta}")
    if len(dados) < quantidade * 2:
        raise ErroFormato("paleta truncada")
    fn = {"IA8": ia8, "RGB565": rgb565, "RGB5A3": rgb5a3}[nome]
    return [fn(struct.unpack_from(">H", dados, 2 * i)[0]) for i in range(quantidade)]


def _cores_dxt1(c0: int, c1: int, quatro_cores: bool | None = None) -> list[Cor]:
    a, b = rgb565(c0), rgb565(c1)
    modo4 = (c0 > c1) if quatro_cores is None else quatro_cores
    if modo4:
        return [a, b,
                tuple((2 * x + y) // 3 for x, y in zip(a[:3], b[:3])) + (255,),  # type: ignore[list-item]
                tuple((x + 2 * y) // 3 for x, y in zip(a[:3], b[:3])) + (255,)]  # type: ignore[list-item]
    return [a, b, tuple((x + y) // 2 for x, y in zip(a[:3], b[:3])) + (255,), (0, 0, 0, 0)]  # type: ignore[list-item]


def decodificar_gx(dados: bytes, nome: str, largura: int, altura: int, paleta: Sequence[Cor] | None = None) -> Imagem:
    if nome not in GX_BLOCOS:
        raise ErroFormato(f"formato GX desconhecido: {nome}")
    if largura <= 0 or altura <= 0 or largura > 8192 or altura > 8192:
        raise ErroFormato(f"dimensoes de textura invalidas: {largura}x{altura}")
    necessario = gx_tamanho_dados(nome, largura, altura)
    if len(dados) < necessario:
        raise ErroFormato(f"textura {nome} {largura}x{altura} precisa de {necessario} bytes, ha {len(dados)}")
    if nome in ("C4", "C8", "C14X2") and not paleta:
        raise ErroFormato(f"formato {nome} precisa de paleta")
    bw, bh, bpp = GX_BLOCOS[nome]
    img = Imagem.vazia(largura, altura)
    pos = 0
    tam_bloco = bw * bh * bpp // 8

    def cor_paleta(k: int) -> Cor:
        assert paleta is not None
        if k >= len(paleta):
            raise ErroFormato(f"indice {k} fora da paleta de {len(paleta)} cores")
        return paleta[k]

    for by in range(0, altura, bh):
        for bx in range(0, largura, bw):
            bloco = dados[pos : pos + tam_bloco]
            pos += tam_bloco
            if nome == "CMPR":
                for sub in range(4):
                    sx, sy = bx + (sub % 2) * 4, by + (sub // 2) * 4
                    s = bloco[sub * 8 : sub * 8 + 8]
                    c0, c1 = struct.unpack_from(">HH", s, 0)
                    cores = _cores_dxt1(c0, c1)
                    for y in range(4):
                        linha = s[4 + y]
                        for x in range(4):
                            img.definir(sx + x, sy + y, cores[(linha >> (6 - 2 * x)) & 3])
                continue
            if nome == "RGBA32":
                for i in range(16):
                    a, r = bloco[2 * i], bloco[2 * i + 1]
                    g, b = bloco[32 + 2 * i], bloco[32 + 2 * i + 1]
                    img.definir(bx + i % 4, by + i // 4, (r, g, b, a))
                continue
            for i in range(bw * bh):
                x, y = bx + i % bw, by + i // bw
                if bpp == 4:
                    v = (bloco[i // 2] >> (4 if i % 2 == 0 else 0)) & 0xF
                    cor = (exp4(v),) * 3 + (255,) if nome == "I4" else cor_paleta(v)
                elif bpp == 8:
                    v = bloco[i]
                    if nome == "I8":
                        cor = (v, v, v, 255)
                    elif nome == "IA4":
                        i4 = exp4(v & 0xF)
                        cor = (i4, i4, i4, exp4(v >> 4))
                    else:
                        cor = cor_paleta(v)
                else:
                    v = struct.unpack_from(">H", bloco, 2 * i)[0]
                    if nome == "IA8":
                        cor = ia8(v)
                    elif nome == "RGB565":
                        cor = rgb565(v)
                    elif nome == "RGB5A3":
                        cor = rgb5a3(v)
                    else:
                        cor = cor_paleta(v & 0x3FFF)
                img.definir(x, y, cor)  # type: ignore[arg-type]
    return img


# ------------------------------------------------------------------------------- BC1/2/3 (PC)
def _bloco_bc1(b: bytes, forcar4: bool = False) -> list[Cor]:
    c0, c1, idx = struct.unpack_from("<HHI", b, 0)
    cores = _cores_dxt1(c0, c1, True if forcar4 else None)
    return [cores[(idx >> (2 * i)) & 3] for i in range(16)]


def _alfa_bc3(b: bytes) -> list[int]:
    a0, a1 = b[0], b[1]
    bits = int.from_bytes(b[2:8], "little")
    if a0 > a1:
        tab = [a0, a1] + [((7 - k) * a0 + k * a1) // 7 for k in range(1, 7)]
    else:
        tab = [a0, a1] + [((5 - k) * a0 + k * a1) // 5 for k in range(1, 5)] + [0, 255]
    return [tab[(bits >> (3 * i)) & 7] for i in range(16)]


def decodificar_bc(dados: bytes, formato: str, largura: int, altura: int) -> Imagem:
    tam = {"BC1": 8, "BC2": 16, "BC3": 16}.get(formato)
    if tam is None:
        raise ErroFormato(f"formato BC desconhecido: {formato}")
    if largura <= 0 or altura <= 0 or largura > 16384 or altura > 16384:
        raise ErroFormato(f"dimensoes invalidas: {largura}x{altura}")
    bx_n, by_n = (largura + 3) // 4, (altura + 3) // 4
    if len(dados) < bx_n * by_n * tam:
        raise ErroFormato(f"{formato} {largura}x{altura} precisa de {bx_n * by_n * tam} bytes, ha {len(dados)}")
    img = Imagem.vazia(largura, altura)
    pos = 0
    for by in range(by_n):
        for bx in range(bx_n):
            b = dados[pos : pos + tam]
            pos += tam
            if formato == "BC1":
                px = _bloco_bc1(b)
            else:
                cor = _bloco_bc1(b[8:], forcar4=True)
                if formato == "BC2":
                    alfas = [exp4((int.from_bytes(b[:8], "little") >> (4 * i)) & 0xF) for i in range(16)]
                else:
                    alfas = _alfa_bc3(b[:8])
                px = [c[:3] + (a,) for c, a in zip(cor, alfas)]  # type: ignore[misc]
            for i, c in enumerate(px):
                img.definir(bx * 4 + i % 4, by * 4 + i // 4, c)
    return img


# --------------------------------------------------------------------------- nao comprimidos
def decodificar_linear(dados: bytes, largura: int, altura: int, bpp: int, extrair: Callable[[bytes, int], Cor], passo_linha: int | None = None) -> Imagem:
    """Pixels lineares (sem blocos); `extrair(dados, offset)` devolve RGBA."""
    passo = passo_linha or (largura * bpp // 8)
    if len(dados) < passo * altura:
        raise ErroFormato(f"imagem {largura}x{altura} precisa de {passo * altura} bytes, ha {len(dados)}")
    img = Imagem.vazia(largura, altura)
    nb = bpp // 8
    for y in range(altura):
        base = y * passo
        for x in range(largura):
            img.definir(x, y, extrair(dados, base + x * nb))
    return img


__all__ = ["GX_FORMATOS", "GX_BLOCOS", "decodificar_gx", "decodificar_paleta_gx", "decodificar_bc", "decodificar_linear", "gx_tamanho_dados", "exp3"]
