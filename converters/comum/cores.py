"""Conversao de cores: expansao de bits, formatos de 16 bits e espacos de cor."""

from __future__ import annotations


def exp3(v: int) -> int:
    return (v << 5) | (v << 2) | (v >> 1)


def exp4(v: int) -> int:
    return v * 0x11


def exp5(v: int) -> int:
    return (v << 3) | (v >> 2)


def exp6(v: int) -> int:
    return (v << 2) | (v >> 4)


def rgb565(v: int) -> tuple[int, int, int, int]:
    return exp5((v >> 11) & 0x1F), exp6((v >> 5) & 0x3F), exp5(v & 0x1F), 255


def rgb5a3(v: int) -> tuple[int, int, int, int]:
    """Formato de 16 bits do GameCube/Wii: bit 15 = 1 -> RGB555 opaco; 0 -> A3 R4 G4 B4."""
    if v & 0x8000:
        return exp5((v >> 10) & 0x1F), exp5((v >> 5) & 0x1F), exp5(v & 0x1F), 255
    return exp4((v >> 8) & 0xF), exp4((v >> 4) & 0xF), exp4(v & 0xF), exp3((v >> 12) & 0x7)


def ia8(v: int) -> tuple[int, int, int, int]:
    """IA8 como u16 big-endian: byte alto = alfa, byte baixo = intensidade."""
    a, i = v >> 8, v & 0xFF
    return i, i, i, a


def bgr555_psx(v: int, stp_transparente: bool = True) -> tuple[int, int, int, int]:
    """Cor de 16 bits do PlayStation (TIM): bits 0-4 R, 5-9 G, 10-14 B, bit 15 STP.

    Convencao do GPU: valor 0x0000 e totalmente transparente; o bit STP so altera a
    semitransparencia, que aqui vira alfa 255 (opaco) por falta de equivalente direto.
    """
    if v == 0 and stp_transparente:
        return 0, 0, 0, 0
    return exp5(v & 0x1F), exp5((v >> 5) & 0x1F), exp5((v >> 10) & 0x1F), 255


def srgb_para_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_para_srgb(c: float) -> float:
    return c * 12.92 if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055
