"""Imagens RGBA em memoria, escrita e leitura de PNG sem dependencias externas.

A escrita e deterministica (mesma entrada -> mesmos bytes): nivel de zlib fixo, sem data/hora,
sem chunks opcionais. A leitura cobre PNG de 8 bits nao entrelacado (o que o CEW grava e o que
navegadores/capturas costumam gerar) e serve para a verificacao (comparar com a referencia).
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field

from .binario import ErroFormato

ASSINATURA_PNG = b"\x89PNG\r\n\x1a\n"


@dataclass
class Imagem:
    largura: int
    altura: int
    rgba: bytearray = field(repr=False)  # largura*altura*4 bytes, linha a linha, de cima para baixo

    def __post_init__(self) -> None:
        if self.largura <= 0 or self.altura <= 0:
            raise ErroFormato(f"dimensoes invalidas {self.largura}x{self.altura}")
        if len(self.rgba) != self.largura * self.altura * 4:
            raise ErroFormato("buffer RGBA com tamanho diferente de largura*altura*4")

    @classmethod
    def vazia(cls, largura: int, altura: int) -> "Imagem":
        return cls(largura, altura, bytearray(largura * altura * 4))

    def pixel(self, x: int, y: int) -> tuple[int, int, int, int]:
        i = (y * self.largura + x) * 4
        return tuple(self.rgba[i : i + 4])  # type: ignore[return-value]

    def definir(self, x: int, y: int, cor: tuple[int, int, int, int]) -> None:
        if 0 <= x < self.largura and 0 <= y < self.altura:
            i = (y * self.largura + x) * 4
            self.rgba[i : i + 4] = bytes(cor)

    @property
    def tem_alfa(self) -> bool:
        return any(a != 255 for a in self.rgba[3::4])

    @property
    def potencia_de_2(self) -> bool:
        return _p2(self.largura) and _p2(self.altura)

    def metadados(self, espaco_cor: str = "srgb") -> dict:
        return {
            "largura_px": self.largura,
            "altura_px": self.altura,
            "espaco_cor": espaco_cor,
            "tem_alfa": self.tem_alfa,
            "potencia_de_2": self.potencia_de_2,
        }


def _p2(n: int) -> bool:
    return n > 0 and (n & (n - 1)) == 0


def _chunk(tipo: bytes, dados: bytes) -> bytes:
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF)


def png_bytes(img: Imagem, nivel: int = 9) -> bytes:
    """PNG RGBA 8 bits (ou RGB quando nao ha alfa, para arquivos menores)."""
    alfa = img.tem_alfa
    tipo_cor = 6 if alfa else 2
    linhas = bytearray()
    passo = img.largura * 4
    for y in range(img.altura):
        linha = img.rgba[y * passo : (y + 1) * passo]
        linhas.append(0)  # filtro None: simples e deterministico
        if alfa:
            linhas += linha
        else:
            rgb = bytearray(img.largura * 3)
            rgb[0::3] = linha[0::4]
            rgb[1::3] = linha[1::4]
            rgb[2::3] = linha[2::4]
            linhas += rgb
    ihdr = struct.pack(">IIBBBBB", img.largura, img.altura, 8, tipo_cor, 0, 0, 0)
    return ASSINATURA_PNG + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", zlib.compress(bytes(linhas), nivel)) + _chunk(b"IEND", b"")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def ler_png(dados: bytes, limite_pixels: int = 64 * 1024 * 1024) -> Imagem:
    if dados[:8] != ASSINATURA_PNG:
        raise ErroFormato("nao e PNG")
    pos = 8
    ihdr = None
    idat = bytearray()
    paleta = b""
    trns = b""
    while pos + 8 <= len(dados):
        tam, tipo = struct.unpack_from(">I4s", dados, pos)
        if pos + 12 + tam > len(dados):
            raise ErroFormato("PNG truncado")
        corpo = dados[pos + 8 : pos + 8 + tam]
        if tipo == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", corpo)
        elif tipo == b"IDAT":
            idat += corpo
        elif tipo == b"PLTE":
            paleta = corpo
        elif tipo == b"tRNS":
            trns = corpo
        elif tipo == b"IEND":
            break
        pos += 12 + tam
    if ihdr is None:
        raise ErroFormato("PNG sem IHDR")
    w, h, prof, tipo_cor, _, _, entrelace = ihdr
    if prof != 8 or entrelace != 0:
        raise ErroFormato("so PNG de 8 bits nao entrelacado e suportado pelo leitor interno")
    if w * h > limite_pixels:
        raise ErroFormato("PNG grande demais")
    canais = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(tipo_cor)
    if canais is None:
        raise ErroFormato(f"tipo de cor PNG {tipo_cor} nao suportado")
    bruto = zlib.decompressobj().decompress(bytes(idat), (w * canais + 1) * h + 1)
    passo = w * canais
    if len(bruto) < (passo + 1) * h:
        raise ErroFormato("dados PNG curtos")
    anterior = bytearray(passo)
    img = Imagem.vazia(w, h)
    for y in range(h):
        f = bruto[y * (passo + 1)]
        linha = bytearray(bruto[y * (passo + 1) + 1 : (y + 1) * (passo + 1)])
        for i in range(passo):
            a = linha[i - canais] if i >= canais else 0
            b = anterior[i]
            c = anterior[i - canais] if i >= canais else 0
            if f == 1:
                linha[i] = (linha[i] + a) & 0xFF
            elif f == 2:
                linha[i] = (linha[i] + b) & 0xFF
            elif f == 3:
                linha[i] = (linha[i] + ((a + b) >> 1)) & 0xFF
            elif f == 4:
                linha[i] = (linha[i] + _paeth(a, b, c)) & 0xFF
            elif f != 0:
                raise ErroFormato(f"filtro PNG {f} invalido")
        for x in range(w):
            p = linha[x * canais : (x + 1) * canais]
            if tipo_cor == 6:
                cor = (p[0], p[1], p[2], p[3])
            elif tipo_cor == 2:
                cor = (p[0], p[1], p[2], 255)
            elif tipo_cor == 0:
                cor = (p[0], p[0], p[0], 255)
            elif tipo_cor == 4:
                cor = (p[0], p[0], p[0], p[1])
            else:
                k = p[0]
                if 3 * k + 3 > len(paleta):
                    raise ErroFormato("indice de paleta fora da paleta")
                cor = (paleta[3 * k], paleta[3 * k + 1], paleta[3 * k + 2], trns[k] if k < len(trns) else 255)
            img.definir(x, y, cor)
        anterior = linha
    return img


def comparar(a: Imagem, b: Imagem) -> dict:
    """Diferenca por pixel e SSIM global em luminancia (imagens do mesmo tamanho)."""
    if (a.largura, a.altura) != (b.largura, b.altura):
        return {"mesmo_tamanho": False, "diferenca_media": 1.0, "ssim": 0.0, "pixels_diferentes": a.largura * a.altura}
    n = a.largura * a.altura
    soma = 0
    difs = 0
    la, lb = [], []
    for i in range(n):
        pa = a.rgba[4 * i : 4 * i + 4]
        pb = b.rgba[4 * i : 4 * i + 4]
        d = sum(abs(x - y) for x, y in zip(pa, pb))
        soma += d
        if d:
            difs += 1
        la.append(0.299 * pa[0] + 0.587 * pa[1] + 0.114 * pa[2])
        lb.append(0.299 * pb[0] + 0.587 * pb[1] + 0.114 * pb[2])
    return {
        "mesmo_tamanho": True,
        "diferenca_media": soma / (n * 4 * 255),
        "ssim": ssim_janelas(la, lb, a.largura, a.altura),
        "pixels_diferentes": difs,
    }


def ssim_janelas(la: list[float], lb: list[float], w: int, h: int, janela: int = 8) -> float:
    """SSIM medio sobre janelas 8x8 sem sobreposicao (Wang et al. 2004, constantes K1=0.01, K2=0.03)."""
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    vals = []
    for y0 in range(0, max(1, h - janela + 1), janela):
        for x0 in range(0, max(1, w - janela + 1), janela):
            xs, ys = [], []
            for y in range(y0, min(h, y0 + janela)):
                for x in range(x0, min(w, x0 + janela)):
                    xs.append(la[y * w + x])
                    ys.append(lb[y * w + x])
            m = len(xs)
            mx, my = sum(xs) / m, sum(ys) / m
            vx = sum((v - mx) ** 2 for v in xs) / m
            vy = sum((v - my) ** 2 for v in ys) / m
            cov = sum((p - mx) * (q - my) for p, q in zip(xs, ys)) / m
            vals.append(((2 * mx * my + c1) * (2 * cov + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2)))
    return sum(vals) / len(vals)


def reduzir(img: Imagem, max_lado: int = 256) -> Imagem:
    """Reducao por vizinho mais proximo (para comparar capturas grandes rapidamente)."""
    escala = max(img.largura, img.altura) / max_lado
    if escala <= 1:
        return img
    w, h = max(1, int(img.largura / escala)), max(1, int(img.altura / escala))
    out = Imagem.vazia(w, h)
    for y in range(h):
        for x in range(w):
            out.definir(x, y, img.pixel(min(img.largura - 1, int(x * escala)), min(img.altura - 1, int(y * escala))))
    return out
