"""TGA (Truevision) -> PNG. Tipos 1/2/3 (sem compressao) e 9/10/11 (RLE), 8/15/16/24/32 bpp.

Cabecalho de 18 bytes (little-endian): tamanho do id, tipo de mapa de cores, tipo de imagem,
especificacao do mapa (primeira entrada u16, quantidade u16, bits u8), origem x/y, largura u16,
altura u16, bits por pixel u8, descritor (bits 0-3 = bits de alfa, bit 5 = origem em cima).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import ErroFormato, LeitorBinario, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.cores import exp5
from converters.comum.imagem import Imagem, png_bytes

INFO = {
    "arquivo": "cookbook/generico/tga_to_png.py",
    "descricao": "Converte TGA (sem compressao e RLE; cor verdadeira, tons de cinza e paleta) para PNG.",
    "formatos_entrada": ["generico.tga"],
    "destino": "png",
    "versao": "1.0",
    "papel": "conversor",
}


def _cor(b: bytes, bpp: int, alfa_bits: int) -> tuple[int, int, int, int]:
    if bpp == 32:
        return (b[2], b[1], b[0], b[3] if alfa_bits else 255)
    if bpp == 24:
        return (b[2], b[1], b[0], 255)
    if bpp in (15, 16):
        v = b[0] | b[1] << 8
        a = 255 if (bpp == 15 or not alfa_bits or v & 0x8000) else 0
        return (exp5((v >> 10) & 0x1F), exp5((v >> 5) & 0x1F), exp5(v & 0x1F), a)
    if bpp == 8:
        return (b[0], b[0], b[0], 255)
    raise ErroFormato(f"{bpp} bpp nao suportado")


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "little")
    id_len, tem_mapa, tipo = r.u8_em(0), r.u8_em(1), r.u8_em(2)
    mapa_ini, mapa_qtd, mapa_bits = r.u16_em(3), r.u16_em(5), r.u8_em(7)
    larg, alt, bpp, desc = r.u16_em(12), r.u16_em(14), r.u8_em(16), r.u8_em(17)
    exigir(tipo in (1, 2, 3, 9, 10, 11), f"tipo TGA {tipo} nao suportado")
    exigir(0 < larg <= 16384 and 0 < alt <= 16384, f"dimensoes invalidas {larg}x{alt}")
    exigir(tem_mapa in (0, 1), "campo de mapa de cores invalido")
    alfa_bits = desc & 0xF
    pos = 18 + id_len
    paleta = []
    if tem_mapa:
        nb = (mapa_bits + 7) // 8
        r.conferir(pos, nb * mapa_qtd, "mapa de cores")
        paleta = [_cor(dados[pos + nb * i : pos + nb * (i + 1)], mapa_bits, alfa_bits) for i in range(mapa_qtd)]
        pos += nb * mapa_qtd
    nbp = (bpp + 7) // 8
    total = larg * alt
    pixels: list[bytes] = []
    if tipo in (1, 2, 3):
        r.conferir(pos, total * nbp, "pixels")
        pixels = [dados[pos + i * nbp : pos + (i + 1) * nbp] for i in range(total)]
    else:
        while len(pixels) < total:
            cab = r.u8_em(pos, "pacote RLE")
            pos += 1
            n = (cab & 0x7F) + 1
            if cab & 0x80:
                p = r.bytes_em(pos, nbp, "pixel RLE")
                pos += nbp
                pixels.extend([p] * n)
            else:
                r.conferir(pos, n * nbp, "pixels RLE")
                pixels.extend(dados[pos + k * nbp : pos + (k + 1) * nbp] for k in range(n))
                pos += n * nbp
        pixels = pixels[:total]
    img = Imagem.vazia(larg, alt)
    em_cima = bool(desc & 0x20)
    direita_esquerda = bool(desc & 0x10)
    for i, p in enumerate(pixels):
        x, y = i % larg, i // larg
        if not em_cima:
            y = alt - 1 - y
        if direita_esquerda:
            x = larg - 1 - x
        if tipo in (1, 9):
            k = p[0] if nbp == 1 else (p[0] | p[1] << 8)
            k -= mapa_ini
            if not 0 <= k < len(paleta):
                raise ErroFormato(f"indice de paleta {k} fora do mapa")
            img.definir(x, y, paleta[k])
        else:
            img.definir(x, y, _cor(p, bpp, alfa_bits))
    esc.gravar("textura.png", png_bytes(img), "textura", "png", img.metadados("srgb"))
    if not img.potencia_de_2:
        esc.avisar(f"dimensoes {larg}x{alt} nao sao potencia de 2")
    return {"largura": larg, "altura": alt, "tipo": tipo, "bpp": bpp}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
