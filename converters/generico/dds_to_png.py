"""DDS (DirectDraw Surface) -> PNG. BC1/BC2/BC3 (DXT1/3/5) e RGB(A) nao comprimido.

Estrutura descrita pela Microsoft ("DDS Programming Guide",
https://learn.microsoft.com/windows/win32/direct3ddds/dx-graphics-dds-pguide):
'DDS ', DDS_HEADER de 124 bytes (altura em +12, largura em +16 a partir do inicio do arquivo,
DDS_PIXELFORMAT em +76: flags +80, fourCC +84, bits +88, mascaras R/G/B/A +92..+104), dados
em 128; com fourCC 'DX10' ha um DDS_HEADER_DXT10 de 20 bytes (dxgiFormat primeiro).
So o nivel 0 de mipmap e a primeira face sao exportados.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import LeitorBinario, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.imagem import png_bytes
from converters.comum.texturas import decodificar_bc, decodificar_linear

INFO = {
    "arquivo": "converters/generico/dds_to_png.py",
    "descricao": "Converte DDS (BC1/BC2/BC3 e RGB/RGBA sem compressao) para PNG.",
    "formatos_entrada": ["generico.dds"],
    "destino": "png",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"espaco_cor\": \"srgb\"|\"linear\"}. Formatos *_SRGB do DX10 marcam srgb automaticamente.",
}

DDPF_ALPHAPIXELS, DDPF_FOURCC, DDPF_RGB, DDPF_LUMINANCE = 0x1, 0x4, 0x40, 0x20000
DXGI = {71: ("BC1", "linear"), 72: ("BC1", "srgb"), 74: ("BC2", "linear"), 75: ("BC2", "srgb"), 77: ("BC3", "linear"), 78: ("BC3", "srgb"),
        28: ("RGBA8", "linear"), 29: ("RGBA8", "srgb"), 87: ("BGRA8", "linear"), 91: ("BGRA8", "srgb")}


def _por_mascara(mascara: int):
    if mascara == 0:
        return None
    desloc = (mascara & -mascara).bit_length() - 1
    maximo = mascara >> desloc
    return lambda v: ((v & mascara) >> desloc) * 255 // maximo


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "little")
    exigir(r.bytes_em(0, 4) == b"DDS ", "nao e DDS (magic 'DDS ' ausente)")
    exigir(r.u32_em(4) == 124, "tamanho do DDS_HEADER diferente de 124")
    alt, larg = r.u32_em(12), r.u32_em(16)
    pf_flags, fourcc, bits = r.u32_em(80), r.bytes_em(84, 4), r.u32_em(88)
    masc = [r.u32_em(92 + 4 * i) for i in range(4)]
    caps2 = r.u32_em(112)
    if caps2 & 0x200:
        esc.avisar("cubemap: so a primeira face foi exportada")
    if caps2 & 0x200000:
        esc.avisar("textura de volume: so a primeira fatia foi exportada")
    inicio = 128
    espaco = opcoes.get("espaco_cor")
    if pf_flags & DDPF_FOURCC:
        if fourcc == b"DX10":
            dxgi = r.u32_em(128)
            inicio = 148
            exigir(dxgi in DXGI, f"dxgiFormat {dxgi} nao suportado")
            fmt, esp_dx = DXGI[dxgi]
            espaco = espaco or esp_dx
        else:
            fmt = {b"DXT1": "BC1", b"DXT2": "BC2", b"DXT3": "BC2", b"DXT4": "BC3", b"DXT5": "BC3"}.get(fourcc)
            exigir(fmt is not None, f"fourCC {fourcc!r} nao suportado")
        if fmt.startswith("BC"):
            img = decodificar_bc(dados[inicio:], fmt, larg, alt)
        else:
            ordem = (0, 1, 2, 3) if fmt == "RGBA8" else (2, 1, 0, 3)
            img = decodificar_linear(dados[inicio:], larg, alt, 32, lambda d, o: tuple(d[o + k] for k in ordem))  # type: ignore[arg-type,return-value]
    elif pf_flags & (DDPF_RGB | DDPF_LUMINANCE):
        exigir(bits in (8, 16, 24, 32), f"{bits} bits por pixel nao suportado")
        nb = bits // 8
        fr, fg, fb = (_por_mascara(m) for m in masc[:3])
        fa = _por_mascara(masc[3]) if pf_flags & DDPF_ALPHAPIXELS else None
        lum = bool(pf_flags & DDPF_LUMINANCE)

        def px(d: bytes, o: int):
            v = int.from_bytes(d[o : o + nb], "little")
            r_ = fr(v) if fr else 0
            a = fa(v) if fa else 255
            if lum:
                return (r_, r_, r_, a)
            return (r_, fg(v) if fg else 0, fb(v) if fb else 0, a)

        img = decodificar_linear(dados[inicio:], larg, alt, bits, px)
    else:
        exigir(False, f"pixel format DDS nao suportado (flags 0x{pf_flags:X})")
    meta = img.metadados(espaco or "srgb")
    esc.gravar("textura.png", png_bytes(img), "textura", "png", meta)
    if not img.potencia_de_2:
        esc.avisar(f"dimensoes {larg}x{alt} nao sao potencia de 2")
    return {"largura": larg, "altura": alt}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
