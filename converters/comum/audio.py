"""Audio: WAV PCM com pontos de loop (chunk 'smpl') e decodificador PS-ADPCM (PlayStation).

A web nao guarda loop dentro do OGG, entao os pontos de loop seguem para asset_manifest.json
(metadados.loop) alem de ficarem no chunk 'smpl' do WAV intermediario.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

from .binario import ErroFormato


@dataclass
class Pcm:
    taxa_hz: int
    canais: int
    amostras: list[list[int]]  # um vetor de int16 por canal
    loop: tuple[int, int] | None = None  # (inicio, fim exclusivo) em amostras

    @property
    def quantidade(self) -> int:
        return len(self.amostras[0]) if self.amostras else 0

    @property
    def duracao_s(self) -> float:
        return self.quantidade / self.taxa_hz if self.taxa_hz else 0.0

    def metadados(self) -> dict:
        return {
            "taxa_amostragem_hz": self.taxa_hz,
            "canais": self.canais,
            "amostras": self.quantidade,
            "duracao_s": round(self.duracao_s, 6),
            "loop": {"inicio_amostra": self.loop[0], "fim_amostra": self.loop[1]} if self.loop else None,
        }


def _clamp16(v: int) -> int:
    return -32768 if v < -32768 else 32767 if v > 32767 else v


def wav_bytes(pcm: Pcm) -> bytes:
    if pcm.canais < 1 or any(len(c) != pcm.quantidade for c in pcm.amostras):
        raise ErroFormato("canais com quantidades diferentes de amostras")
    n = pcm.quantidade
    dados = bytearray(n * pcm.canais * 2)
    for i in range(n):
        for c in range(pcm.canais):
            struct.pack_into("<h", dados, (i * pcm.canais + c) * 2, _clamp16(pcm.amostras[c][i]))
    fmt = struct.pack("<HHIIHH", 1, pcm.canais, pcm.taxa_hz, pcm.taxa_hz * pcm.canais * 2, pcm.canais * 2, 16)
    chunks = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    chunks += b"data" + struct.pack("<I", len(dados)) + bytes(dados)
    if pcm.loop:
        ini, fim = pcm.loop
        periodo = int(round(1e9 / pcm.taxa_hz))
        smpl = struct.pack("<9I", 0, 0, periodo, 60, 0, 0, 0, 1, 0)
        smpl += struct.pack("<6I", 0, 0, ini, max(ini, fim - 1), 0, 0)  # fim inclusivo no 'smpl'
        chunks += b"smpl" + struct.pack("<I", len(smpl)) + smpl
    return b"RIFF" + struct.pack("<I", 4 + len(chunks)) + b"WAVE" + chunks


def ler_wav(dados: bytes) -> Pcm:
    if len(dados) < 12 or dados[:4] != b"RIFF" or dados[8:12] != b"WAVE":
        raise ErroFormato("nao e WAV (RIFF/WAVE)")
    pos = 12
    fmt = None
    bruto = None
    loop = None
    while pos + 8 <= len(dados):
        cid, tam = dados[pos : pos + 4], struct.unpack_from("<I", dados, pos + 4)[0]
        corpo = dados[pos + 8 : pos + 8 + tam]
        if len(corpo) < tam:
            raise ErroFormato(f"chunk {cid!r} truncado")
        if cid == b"fmt ":
            if tam < 16:
                raise ErroFormato("chunk fmt curto")
            fmt = struct.unpack_from("<HHIIHH", corpo, 0)
        elif cid == b"data":
            bruto = corpo
        elif cid == b"smpl" and tam >= 36:
            nloops = struct.unpack_from("<I", corpo, 28)[0]
            if nloops >= 1 and tam >= 36 + 24:
                _, _, ini, fim, _, _ = struct.unpack_from("<6I", corpo, 36)
                loop = (ini, fim + 1)
        pos += 8 + tam + (tam & 1)
    if fmt is None or bruto is None:
        raise ErroFormato("WAV sem fmt ou data")
    codec, canais, taxa, _, alinhamento, bits = fmt
    if codec != 1 or bits != 16:
        raise ErroFormato(f"so PCM 16 bits e lido internamente (codec {codec}, {bits} bits)")
    if canais < 1:
        raise ErroFormato("WAV sem canais")
    n = len(bruto) // (2 * canais)
    amostras = [[0] * n for _ in range(canais)]
    for i in range(n):
        for c in range(canais):
            amostras[c][i] = struct.unpack_from("<h", bruto, (i * canais + c) * 2)[0]
    return Pcm(taxa, canais, amostras, loop)


# ----------------------------------------------------------------------------------- PS-ADPCM
PSX_COEF = [(0, 0), (60, 0), (115, -52), (98, -55), (122, -60)]
PSX_FLAG_FIM = 0x01
PSX_FLAG_REPETIR = 0x02
PSX_FLAG_INICIO_LOOP = 0x04


def psx_adpcm_decodificar(dados: bytes, parar_no_fim: bool = True) -> tuple[list[int], tuple[int, int] | None]:
    """Decodifica quadros de 16 bytes (28 amostras cada). Devolve (amostras, loop).

    Byte 0: filtro (nibble alto) e deslocamento (nibble baixo); byte 1: flags; 14 bytes de
    nibbles, o nibble baixo primeiro. Flags: 0x04 inicio do loop; 0x01|0x02 fim do loop
    (volta ao inicio); 0x01 sozinho = fim sem loop.
    """
    if len(dados) % 16:
        dados = dados[: len(dados) - len(dados) % 16]
    saida: list[int] = []
    h1 = h2 = 0
    inicio_loop = fim_loop = None
    for q in range(len(dados) // 16):
        b = dados[q * 16 : q * 16 + 16]
        filtro, desloc, flags = b[0] >> 4, b[0] & 0xF, b[1]
        if filtro >= len(PSX_COEF):
            raise ErroFormato(f"PS-ADPCM: filtro {filtro} invalido no quadro {q}")
        if desloc > 12:
            desloc = 9  # valores > 12 sao tratados como 9 por decodificadores conhecidos
        if flags & PSX_FLAG_INICIO_LOOP and inicio_loop is None:
            inicio_loop = len(saida)
        f0, f1 = PSX_COEF[filtro]
        for i in range(28):
            nib = (b[2 + i // 2] >> (0 if i % 2 == 0 else 4)) & 0xF
            if nib >= 8:
                nib -= 16
            s = ((nib << 12) >> desloc) + ((h1 * f0 + h2 * f1) >> 6)
            s = _clamp16(s)
            saida.append(s)
            h2, h1 = h1, s
        if flags & PSX_FLAG_FIM:
            if flags & PSX_FLAG_REPETIR and inicio_loop is not None:
                fim_loop = len(saida)
            if parar_no_fim:
                break
    loop = (inicio_loop, fim_loop) if inicio_loop is not None and fim_loop is not None else None
    return saida, loop
