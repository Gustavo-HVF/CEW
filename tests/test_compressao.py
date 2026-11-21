from __future__ import annotations

import os
import random
import zlib

import pytest

from converters.comum import compressao as c
from converters.comum.binario import ErroFormato


@pytest.mark.parametrize("dados", [b"", b"a", b"abcabcabcabcabc" * 50, bytes(range(256)) * 9, os.urandom(3000), b"\x00" * 5000])
def test_yaz0_ida_e_volta(dados):
    comp = c.yaz0_compactar(dados)
    assert comp[:4] == b"Yaz0"
    assert c.yaz0_descompactar(comp) == dados


@pytest.mark.parametrize("dados", [b"x", b"repete" * 300, os.urandom(2000)])
def test_lz10_ida_e_volta(dados):
    assert c.lz10_descompactar(c.lz10_compactar(dados)) == dados


def test_lz11_referencia_curta_manual():
    # 0x11, tamanho 6; flags 0b01000000: literal 'a', depois referencia (ind=2 -> 3 bytes, dist 1) ... 'aaaa' + literal 'b' + literal 'c'
    dados = bytes([0x11, 6, 0, 0, 0b01000000, ord("a"), 0x20, 0x00, ord("b"), ord("c")])
    assert c.lz11_descompactar(dados) == b"aaaabc"


def test_bomba_de_descompressao_bloqueada():
    comp = c.yaz0_compactar(b"\x00" * 100_000)
    with pytest.raises(ErroFormato):
        c.yaz0_descompactar(comp, limite=10_000)
    with pytest.raises(ErroFormato):
        c.zlib_descompactar(zlib.compress(b"\x00" * 100_000), limite=10_000)


def test_yaz0_truncado_e_referencia_invalida():
    comp = c.yaz0_compactar(b"abcabcabc" * 40)
    with pytest.raises(ErroFormato):
        c.yaz0_descompactar(comp[:20])
    falso = b"Yaz0" + (10).to_bytes(4, "big") + b"\x00" * 8 + b"\x00\x0f\xff"
    with pytest.raises(ErroFormato):
        c.yaz0_descompactar(falso)


def test_deteccao():
    assert c.detectar(b"Yaz0\x00\x00\x10\x00", 100).algoritmo == "yaz0"
    assert c.detectar(zlib.compress(b"abc" * 100)[:16], 50).algoritmo == "zlib"
    assert c.detectar(b"\x1f\x8b\x08\x00", 100).algoritmo == "gzip"
    assert c.detectar(b"\x28\xb5\x2f\xfd", 100).algoritmo == "zstd"
    assert c.detectar(b"PNG?", 100) is None
    rnd = random.Random(5)
    for _ in range(200):  # bytes aleatorios nunca quebram a deteccao
        c.detectar(bytes(rnd.randrange(256) for _ in range(16)), rnd.randrange(1, 10**6))
