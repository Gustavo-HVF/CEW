"""TIM (imagens do PlayStation 1) -> PNG.

Estrutura (little-endian), descrita em psx-spx (https://psx-spx.consoledev.net/) e na
documentacao de formatos do SDK:
  u32 id 0x00000010 | u32 flags: bits 0-2 modo (0=4bpp, 1=8bpp, 2=16bpp, 3=24bpp), bit 3 = tem CLUT
  CLUT (se houver): u32 tamanho do bloco, u16 x, u16 y, u16 cores por CLUT, u16 quantidade, dados u16
  imagem: u32 tamanho do bloco, u16 x, u16 y, u16 largura em unidades de 16 bits, u16 altura, dados
Cor de 16 bits: R 0-4, G 5-9, B 10-14, bit 15 STP; 0x0000 = transparente.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import ErroFormato, LeitorBinario, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.cores import bgr555_psx
from converters.comum.imagem import Imagem, png_bytes

INFO = {
    "arquivo": "converters/sony/tim_to_png.py",
    "descricao": "Converte imagens TIM (4, 8, 16 e 24 bpp, com ou sem CLUT) para PNG.",
    "formatos_entrada": ["sony.psx.tim"],
    "destino": "png",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"clut\": 0} escolhe a paleta; {\"todas_cluts\": true} gera um PNG por paleta; {\"preto_transparente\": false} desliga a regra 0x0000 = transparente.",
}


def analisar(dados: bytes) -> dict:
    r = LeitorBinario(dados, "little")
    exigir(r.u32_em(0, "id") == 0x10, "nao e TIM (id 0x10 ausente)")
    flags = r.u32_em(4)
    exigir(flags & ~0xF == 0, f"flags TIM invalidas: 0x{flags:X}")
    modo, tem_clut = flags & 7, bool(flags & 8)
    exigir(modo <= 3, f"modo TIM invalido {modo}")
    pos = 8
    clut = None
    if tem_clut:
        tam_bloco = r.u32_em(pos)
        cores, qtd = r.u16_em(pos + 8), r.u16_em(pos + 10)
        exigir(tam_bloco >= 12 and 12 + cores * qtd * 2 <= tam_bloco, "bloco CLUT inconsistente")
        r.conferir(pos + 12, cores * qtd * 2, "CLUT")
        clut = {"cores": cores, "quantidade": qtd, "offset": pos + 12}
        pos += tam_bloco
    tam_img = r.u32_em(pos, "bloco de imagem")
    larg16, alt = r.u16_em(pos + 8), r.u16_em(pos + 10)
    exigir(tam_img >= 12 and 12 + larg16 * alt * 2 <= tam_img, "bloco de imagem inconsistente")
    r.conferir(pos + 12, larg16 * alt * 2, "pixels")
    largura = {0: larg16 * 4, 1: larg16 * 2, 2: larg16, 3: larg16 * 2 // 3}[modo]
    exigir(largura > 0 and alt > 0, "imagem TIM vazia")
    exigir(modo >= 2 or clut is not None, "TIM 4/8 bpp sem CLUT")
    return {"modo": modo, "clut": clut, "largura": largura, "altura": alt, "offset_pixels": pos + 12, "passo": larg16 * 2}


def decodificar(dados: bytes, info: dict, indice_clut: int = 0, preto_transparente: bool = True) -> Imagem:
    r = LeitorBinario(dados, "little")
    modo, w, h, base, passo = info["modo"], info["largura"], info["altura"], info["offset_pixels"], info["passo"]
    paleta = []
    if modo < 2:
        c = info["clut"]
        if not 0 <= indice_clut < c["quantidade"]:
            raise ErroFormato(f"CLUT {indice_clut} nao existe (ha {c['quantidade']})")
        o = c["offset"] + indice_clut * c["cores"] * 2
        paleta = [bgr555_psx(r.u16_em(o + 2 * k), preto_transparente) for k in range(c["cores"])]
    img = Imagem.vazia(w, h)

    def cor(k: int):
        if k >= len(paleta):
            raise ErroFormato(f"indice {k} fora da CLUT de {len(paleta)} cores")
        return paleta[k]

    for y in range(h):
        linha = base + y * passo
        for x in range(w):
            if modo == 0:
                b = dados[linha + x // 2]
                c = cor((b >> 4) if x % 2 else (b & 0xF))  # nibble baixo primeiro
            elif modo == 1:
                c = cor(dados[linha + x])
            elif modo == 2:
                c = bgr555_psx(r.u16_em(linha + 2 * x), preto_transparente)
            else:
                o = linha + 3 * x
                c = (dados[o], dados[o + 1], dados[o + 2], 255)
            img.definir(x, y, c)
    return img


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    info = analisar(dados)
    pt = bool(opcoes.get("preto_transparente", True))
    if info["modo"] < 2 and opcoes.get("todas_cluts"):
        indices = list(range(info["clut"]["quantidade"]))
    else:
        indices = [int(opcoes.get("clut", 0))]
    for i in indices:
        img = decodificar(dados, info, i, pt)
        nome = "imagem.png" if len(indices) == 1 else f"imagem_clut{i:02d}.png"
        meta = img.metadados("srgb")
        meta["extras"] = {"bpp_original": [4, 8, 16, 24][info["modo"]], "clut": i if info["modo"] < 2 else None}
        esc.gravar(nome, png_bytes(img), "textura", "png", meta)
        if not img.potencia_de_2:
            esc.avisar(f"dimensoes {img.largura}x{img.altura} nao sao potencia de 2")
    return {"largura": info["largura"], "altura": info["altura"], "bpp": [4, 8, 16, 24][info["modo"]]}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
