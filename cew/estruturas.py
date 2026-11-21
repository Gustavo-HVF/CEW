"""Camada 3 da identificacao: conferencia de estrutura (tamanhos e offsets coerentes).

Cada verificador recebe o comeco do arquivo (`cabeca`, ate 64 KiB), o fim (`cauda`, 64 bytes) e o
tamanho total, e responde True (coerente) ou False. Nunca le fora do que recebeu. O nome da
funcao e o que vai em "verificador_estrutura" no formats/registry.json.
"""

from __future__ import annotations

import struct
from typing import Callable

Verificador = Callable[[bytes, bytes, int], bool]
VERIFICADORES: dict[str, Verificador] = {}


def verificador(fn: Verificador) -> Verificador:
    VERIFICADORES[fn.__name__] = fn
    return fn


def _u32(b: bytes, o: int, ordem: str = "<") -> int | None:
    return struct.unpack_from(ordem + "I", b, o)[0] if o + 4 <= len(b) else None


def _u16(b: bytes, o: int, ordem: str = "<") -> int | None:
    return struct.unpack_from(ordem + "H", b, o)[0] if o + 2 <= len(b) else None


@verificador
def tim_psx(c: bytes, cauda: bytes, tam: int) -> bool:
    flags = _u32(c, 4)
    if flags is None or flags & ~0xF or (flags & 7) > 3:
        return False
    pos = 8
    if flags & 8:
        bloco = _u32(c, pos)
        if bloco is None or bloco < 12 or pos + bloco > tam:
            return False
        pos += bloco
    bloco = _u32(c, pos)
    w16, h = _u16(c, pos + 8), _u16(c, pos + 10)
    return bloco is not None and w16 and h and bloco >= 12 + w16 * h * 2 - 2 and pos + bloco <= tam + 2


@verificador
def renderware_chunk(c: bytes, cauda: bytes, tam: int) -> bool:
    """Chunk RenderWare: u32 id, u32 tamanho (cabe no arquivo), u32 versao da biblioteca."""
    tamanho, versao = _u32(c, 4), _u32(c, 8)
    if tamanho is None or versao is None or tamanho + 12 > tam:
        return False
    if versao & 0xFFFF0000:
        # carimbo novo: id da biblioteca = ((v >> 14) & 0x3FF00) + 0x30000 | ((v >> 16) & 0x3F)
        lib = (((versao >> 14) & 0x3FF00) + 0x30000) | ((versao >> 16) & 0x3F)
        return 0x30000 <= lib <= 0x3FFFF
    return 0x0200 <= versao <= 0x0400  # carimbo antigo (RW 3.0-3.1)


@verificador
def unity_serializado(c: bytes, cauda: bytes, tam: int) -> bool:
    """SerializedFile do Unity: u32 BE tamanho dos metadados, u32 BE tamanho do arquivo, u32 BE versao."""
    meta, total, versao = _u32(c, 0, ">"), _u32(c, 4, ">"), _u32(c, 8, ">")
    if meta is None or total is None or versao is None:
        return False
    if versao >= 22:
        total64 = struct.unpack_from(">Q", c, 0x18)[0] if len(c) >= 0x20 else 0
        return 9 <= versao <= 50 and total64 == tam
    return 9 <= versao <= 50 and total == tam and meta < tam


@verificador
def tga(c: bytes, cauda: bytes, tam: int) -> bool:
    if len(c) < 18:
        return False
    id_len, mapa, tipo = c[0], c[1], c[2]
    w, h, bpp = _u16(c, 12), _u16(c, 14), c[16]
    if cauda.endswith(b"TRUEVISION-XFILE.\x00"):
        return True
    return mapa in (0, 1) and tipo in (1, 2, 3, 9, 10, 11) and bool(w) and bool(h) and bpp in (8, 15, 16, 24, 32) and 18 + id_len < tam


@verificador
def quake1_bsp(c: bytes, cauda: bytes, tam: int) -> bool:
    if _u32(c, 0) != 29 or len(c) < 4 + 15 * 8:
        return False
    for i in range(15):
        off, ln = struct.unpack_from("<ii", c, 4 + 8 * i)
        if off < 0 or ln < 0 or off + ln > tam:
            return False
    return True


@verificador
def u8_arc(c: bytes, cauda: bytes, tam: int) -> bool:
    raiz, tam_nos, dados = _u32(c, 4, ">"), _u32(c, 8, ">"), _u32(c, 12, ">")
    return raiz is not None and tam_nos is not None and dados is not None and raiz < tam and raiz + tam_nos <= tam and dados <= tam


@verificador
def sarc(c: bytes, cauda: bytes, tam: int) -> bool:
    if len(c) < 0x14 or c[6:8] not in (b"\xfe\xff", b"\xff\xfe"):
        return False
    o = ">" if c[6:8] == b"\xfe\xff" else "<"
    total, dados = _u32(c, 8, o), _u32(c, 12, o)
    return total == tam and dados is not None and dados <= tam and c[0x14:0x18] == b"SFAT"


@verificador
def pak_quake(c: bytes, cauda: bytes, tam: int) -> bool:
    off, ln = _u32(c, 4), _u32(c, 8)
    return off is not None and ln is not None and ln % 64 == 0 and off + ln <= tam


@verificador
def vpk(c: bytes, cauda: bytes, tam: int) -> bool:
    versao, arvore = _u32(c, 4), _u32(c, 8)
    return versao in (1, 2) and arvore is not None and arvore < tam


@verificador
def md2(c: bytes, cauda: bytes, tam: int) -> bool:
    return _u32(c, 4) == 8 and (_u32(c, 64) or 0) <= tam


@verificador
def md3(c: bytes, cauda: bytes, tam: int) -> bool:
    return _u32(c, 4) == 15


@verificador
def dds(c: bytes, cauda: bytes, tam: int) -> bool:
    return _u32(c, 4) == 124 and _u32(c, 76) == 32


@verificador
def riff_wave(c: bytes, cauda: bytes, tam: int) -> bool:
    return c[8:12] == b"WAVE"


def _fmt_wave(c: bytes) -> tuple[int, bytes] | None:
    """(codec, GUID do subformato) do primeiro chunk fmt de um RIFF WAVE."""
    pos = 12
    while pos + 8 <= len(c):
        cid, n = c[pos : pos + 4], _u32(c, pos + 4) or 0
        if cid == b"fmt ":
            codec = _u16(c, pos + 8) or 0
            guid = c[pos + 8 + 24 : pos + 8 + 40] if codec == 0xFFFE and n >= 40 else b""
            return codec, guid
        pos += 8 + n + (n & 1)
    return None


@verificador
def wav_pcm(c: bytes, cauda: bytes, tam: int) -> bool:
    f = _fmt_wave(c)
    return c[8:12] == b"WAVE" and f is not None and f[0] in (1, 3)


@verificador
def wav_wwise(c: bytes, cauda: bytes, tam: int) -> bool:
    f = _fmt_wave(c)
    return (c[:4] in (b"RIFF", b"RIFX")) and c[8:12] == b"WAVE" and f is not None and f[0] in (0xFFFF, 0xFFFE, 0x0002, 0x0166) and f[0] != 1


ATRAC3_GUID = bytes.fromhex("bfaa23e958cb7144a119fffa01e4ce62")
ATRAC9_GUID = bytes.fromhex("d2426e47ba7b154ab1bc29a2cd7d70bb")


@verificador
def wav_atrac3(c: bytes, cauda: bytes, tam: int) -> bool:
    f = _fmt_wave(c)
    return f is not None and (f[0] == 0x0270 or f[1] == ATRAC3_GUID)


@verificador
def wav_atrac9(c: bytes, cauda: bytes, tam: int) -> bool:
    f = _fmt_wave(c)
    return f is not None and f[1] == ATRAC9_GUID


@verificador
def riff_webp(c: bytes, cauda: bytes, tam: int) -> bool:
    return c[8:12] == b"WEBP"


@verificador
def adx(c: bytes, cauda: bytes, tam: int) -> bool:
    off = _u16(c, 2, ">")
    return off is not None and 4 <= off < len(c) and c[off - 2 : off + 4] == b"(c)CRI"


@verificador
def zip_local(c: bytes, cauda: bytes, tam: int) -> bool:
    return b"PK\x05\x06" in cauda or tam > 22


@verificador
def gx_bti(c: bytes, cauda: bytes, tam: int) -> bool:
    """Cabecalho BTI (0x20 bytes): formato GX valido, dimensoes e offset de dados coerentes."""
    if len(c) < 0x20:
        return False
    fmt, w, h, off = c[0], _u16(c, 2, ">"), _u16(c, 4, ">"), _u32(c, 0x1C, ">")
    return fmt in (0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 14) and 0 < (w or 0) <= 1024 and 0 < (h or 0) <= 1024 and off is not None and 0x20 <= off < tam


@verificador
def nes_ines(c: bytes, cauda: bytes, tam: int) -> bool:
    return len(c) >= 16 and c[4] > 0


@verificador
def gba_rom(c: bytes, cauda: bytes, tam: int) -> bool:
    if len(c) < 0xC0:
        return False
    chk = (-sum(c[0xA0:0xBD]) - 0x19) & 0xFF
    return c[0xB2] == 0x96 and c[0xBD] == chk


@verificador
def gameboy_rom(c: bytes, cauda: bytes, tam: int) -> bool:
    if len(c) < 0x150:
        return False
    x = 0
    for b in c[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    return c[0x14D] == x


@verificador
def pe_windows(c: bytes, cauda: bytes, tam: int) -> bool:
    off = _u32(c, 0x3C)
    return off is not None and off + 4 <= len(c) and c[off : off + 4] == b"PE\x00\x00"


@verificador
def java_class(c: bytes, cauda: bytes, tam: int) -> bool:
    """CAFEBABE tambem e Mach-O universal; classe Java tem versao maior >= 45 em +6."""
    maior = _u16(c, 6, ">")
    return maior is not None and 45 <= maior <= 80


@verificador
def macho_universal(c: bytes, cauda: bytes, tam: int) -> bool:
    n = _u32(c, 4, ">")
    return n is not None and 0 < n < 20


@verificador
def iso9660(c: bytes, cauda: bytes, tam: int) -> bool:
    return cabeca_iso(c)


def cabeca_iso(c: bytes) -> bool:
    return c[0x8001:0x8006] == b"CD001"


def verificar(nome: str | None, cabeca: bytes, cauda: bytes, tamanho: int) -> bool | None:
    """True/False pelo verificador; None se o formato nao tem verificador ou ele falhou ao ler."""
    if not nome:
        return None
    fn = VERIFICADORES.get(nome)
    if fn is None:
        return None
    try:
        return bool(fn(cabeca, cauda, tamanho))
    except (struct.error, IndexError, ValueError):
        return False
