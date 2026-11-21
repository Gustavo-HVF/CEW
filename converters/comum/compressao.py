"""Compressoes comuns em jogos: Yaz0, Yay0, LZ10/LZ11 (Nintendo), zlib, gzip.

Referencias publicas (descricao dos algoritmos):
- Yaz0/Yay0: documentacao comunitaria do GameCube/Wii (ex.: http://www.amnoid.de/gc/yaz0.txt).
- LZ10/LZ11: BIOS do GBA/DS (GBATEK, https://problemkaputt.de/gbatek.htm, "LZ77UnCompWram").
Todos os decodificadores limitam o tamanho de saida (contra bombas de descompressao) e falham com
ErroFormato em vez de ler fora do buffer.
"""

from __future__ import annotations

import gzip
import io
import struct
import zlib
from dataclasses import dataclass

from .binario import LIMITE_PADRAO_BYTES, ErroFormato, limitar_tamanho


@dataclass
class Deteccao:
    algoritmo: str
    confianca: float
    tamanho_descompactado: int | None


# ------------------------------------------------------------------------------------- Yaz0
def yaz0_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    if len(dados) < 16 or dados[:4] != b"Yaz0":
        raise ErroFormato("nao e Yaz0 (assinatura 'Yaz0' ausente)")
    tamanho = limitar_tamanho(struct.unpack_from(">I", dados, 4)[0], limite, "tamanho Yaz0 descompactado")
    saida = bytearray()
    pos, n = 16, len(dados)
    while len(saida) < tamanho:
        if pos >= n:
            raise ErroFormato("Yaz0 truncado (cabecalho de grupo ausente)")
        grupo = dados[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(saida) >= tamanho:
                break
            if grupo & (1 << bit):
                if pos >= n:
                    raise ErroFormato("Yaz0 truncado (literal)")
                saida.append(dados[pos])
                pos += 1
            else:
                if pos + 2 > n:
                    raise ErroFormato("Yaz0 truncado (referencia)")
                b1, b2 = dados[pos], dados[pos + 1]
                pos += 2
                dist = ((b1 & 0x0F) << 8 | b2) + 1
                cont = b1 >> 4
                if cont == 0:
                    if pos >= n:
                        raise ErroFormato("Yaz0 truncado (tamanho estendido)")
                    cont = dados[pos] + 0x12
                    pos += 1
                else:
                    cont += 2
                if dist > len(saida):
                    raise ErroFormato(f"Yaz0: referencia {dist} antes do inicio da saida")
                ini = len(saida) - dist
                for i in range(cont):
                    saida.append(saida[ini + i])
    return bytes(saida[:tamanho])


def _buscar(dados: bytes, pos: int, janela: int, max_len: int, tabela: dict) -> tuple[int, int]:
    """Melhor casamento (distancia, tamanho) usando cadeias de prefixos de 3 bytes."""
    if pos + 3 > len(dados):
        return 0, 0
    chave = dados[pos : pos + 3]
    melhor_d, melhor_n = 0, 0
    limite = min(max_len, len(dados) - pos)
    for cand in reversed(tabela.get(chave, ())):
        d = pos - cand
        if d > janela:
            break
        n = 3
        while n < limite and dados[cand + n] == dados[pos + n]:
            n += 1
        if n > melhor_n:
            melhor_d, melhor_n = d, n
            if n == limite:
                break
    return melhor_d, melhor_n


def _registrar(tabela: dict, dados: bytes, pos: int, ate: int) -> None:
    for p in range(pos, min(ate, len(dados) - 2)):
        lista = tabela.setdefault(dados[p : p + 3], [])
        lista.append(p)
        if len(lista) > 64:
            del lista[0]


def yaz0_compactar(dados: bytes) -> bytes:
    """Compactador Yaz0 guloso e deterministico (usado em fixtures e para reempacotar)."""
    saida = bytearray(b"Yaz0" + struct.pack(">I", len(dados)) + b"\x00" * 8)
    pos, tabela = 0, {}
    while pos < len(dados):
        idx_grupo = len(saida)
        saida.append(0)
        grupo = 0
        for bit in range(7, -1, -1):
            if pos >= len(dados):
                break
            d, n = _buscar(dados, pos, 0x1000, 0x111, tabela)
            if n >= 3:
                if n >= 0x12:
                    saida += bytes([(d - 1) >> 8, (d - 1) & 0xFF, n - 0x12])
                else:
                    saida += bytes([((n - 2) << 4) | ((d - 1) >> 8), (d - 1) & 0xFF])
                _registrar(tabela, dados, pos, pos + n)
                pos += n
            else:
                grupo |= 1 << bit
                saida.append(dados[pos])
                _registrar(tabela, dados, pos, pos + 1)
                pos += 1
        saida[idx_grupo] = grupo
    return bytes(saida)


# ------------------------------------------------------------------------------------- Yay0
def yay0_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    if len(dados) < 16 or dados[:4] != b"Yay0":
        raise ErroFormato("nao e Yay0")
    tamanho, off_link, off_chunk = struct.unpack_from(">III", dados, 4)
    limitar_tamanho(tamanho, limite, "tamanho Yay0 descompactado")
    if not (16 <= off_link <= len(dados) and 16 <= off_chunk <= len(dados)):
        raise ErroFormato("Yay0: offsets fora do arquivo")
    saida = bytearray()
    pmask, plink, pchunk = 16, off_link, off_chunk
    mascara, bits = 0, 0
    while len(saida) < tamanho:
        if bits == 0:
            if pmask + 4 > len(dados):
                raise ErroFormato("Yay0 truncado (mascara)")
            mascara = struct.unpack_from(">I", dados, pmask)[0]
            pmask += 4
            bits = 32
        if mascara & 0x80000000:
            if pchunk >= len(dados):
                raise ErroFormato("Yay0 truncado (literal)")
            saida.append(dados[pchunk])
            pchunk += 1
        else:
            if plink + 2 > len(dados):
                raise ErroFormato("Yay0 truncado (link)")
            link = struct.unpack_from(">H", dados, plink)[0]
            plink += 2
            dist = (link & 0xFFF) + 1
            cont = link >> 12
            if cont == 0:
                if pchunk >= len(dados):
                    raise ErroFormato("Yay0 truncado (tamanho)")
                cont = dados[pchunk] + 0x12
                pchunk += 1
            else:
                cont += 2
            if dist > len(saida):
                raise ErroFormato("Yay0: referencia antes do inicio")
            ini = len(saida) - dist
            for i in range(cont):
                saida.append(saida[ini + i])
        mascara = (mascara << 1) & 0xFFFFFFFF
        bits -= 1
    return bytes(saida[:tamanho])


# ------------------------------------------------------------------------------- LZ10 / LZ11
def _lz_cabecalho(dados: bytes, tipo: int, limite: int) -> tuple[int, int]:
    if len(dados) < 4 or dados[0] != tipo:
        raise ErroFormato(f"nao e LZ{tipo:02X}")
    tamanho = dados[1] | dados[2] << 8 | dados[3] << 16
    pos = 4
    if tamanho == 0:
        if len(dados) < 8:
            raise ErroFormato("LZ truncado (tamanho estendido)")
        tamanho = struct.unpack_from("<I", dados, 4)[0]
        pos = 8
    return limitar_tamanho(tamanho, limite, "tamanho LZ descompactado"), pos


def lz10_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    tamanho, pos = _lz_cabecalho(dados, 0x10, limite)
    saida = bytearray()
    while len(saida) < tamanho:
        if pos >= len(dados):
            raise ErroFormato("LZ10 truncado")
        flags = dados[pos]
        pos += 1
        for bit in range(7, -1, -1):
            if len(saida) >= tamanho:
                break
            if flags & (1 << bit):
                if pos + 2 > len(dados):
                    raise ErroFormato("LZ10 truncado (referencia)")
                b1, b2 = dados[pos], dados[pos + 1]
                pos += 2
                cont = (b1 >> 4) + 3
                dist = ((b1 & 0xF) << 8 | b2) + 1
                if dist > len(saida):
                    raise ErroFormato("LZ10: referencia antes do inicio")
                ini = len(saida) - dist
                for i in range(cont):
                    saida.append(saida[ini + i])
            else:
                if pos >= len(dados):
                    raise ErroFormato("LZ10 truncado (literal)")
                saida.append(dados[pos])
                pos += 1
    return bytes(saida[:tamanho])


def lz10_compactar(dados: bytes) -> bytes:
    if len(dados) > 0xFFFFFF:
        cab = bytes([0x10, 0, 0, 0]) + struct.pack("<I", len(dados))
    else:
        cab = bytes([0x10, len(dados) & 0xFF, (len(dados) >> 8) & 0xFF, len(dados) >> 16])
    saida = bytearray(cab)
    pos, tabela = 0, {}
    while pos < len(dados):
        idx = len(saida)
        saida.append(0)
        flags = 0
        for bit in range(7, -1, -1):
            if pos >= len(dados):
                break
            d, n = _buscar(dados, pos, 0x1000, 18, tabela)
            if n >= 3:
                flags |= 1 << bit
                saida += bytes([((n - 3) << 4) | ((d - 1) >> 8), (d - 1) & 0xFF])
                _registrar(tabela, dados, pos, pos + n)
                pos += n
            else:
                saida.append(dados[pos])
                _registrar(tabela, dados, pos, pos + 1)
                pos += 1
        saida[idx] = flags
    return bytes(saida)


def lz11_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    tamanho, pos = _lz_cabecalho(dados, 0x11, limite)
    saida = bytearray()

    def byte() -> int:
        nonlocal pos
        if pos >= len(dados):
            raise ErroFormato("LZ11 truncado")
        v = dados[pos]
        pos += 1
        return v

    while len(saida) < tamanho:
        flags = byte()
        for bit in range(7, -1, -1):
            if len(saida) >= tamanho:
                break
            if not flags & (1 << bit):
                saida.append(byte())
                continue
            b1 = byte()
            ind = b1 >> 4
            if ind == 0:
                b2, b3 = byte(), byte()
                cont = ((b1 & 0xF) << 4 | b2 >> 4) + 0x11
                dist = ((b2 & 0xF) << 8 | b3) + 1
            elif ind == 1:
                b2, b3, b4 = byte(), byte(), byte()
                cont = ((b1 & 0xF) << 12 | b2 << 4 | b3 >> 4) + 0x111
                dist = ((b3 & 0xF) << 8 | b4) + 1
            else:
                b2 = byte()
                cont = ind + 1
                dist = ((b1 & 0xF) << 8 | b2) + 1
            if dist > len(saida):
                raise ErroFormato("LZ11: referencia antes do inicio")
            ini = len(saida) - dist
            for i in range(cont):
                saida.append(saida[ini + i])
    return bytes(saida[:tamanho])


# ------------------------------------------------------------------------------ zlib / gzip
def zlib_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    d = zlib.decompressobj()
    try:
        saida = d.decompress(dados, limite + 1)
    except zlib.error as e:
        raise ErroFormato(f"zlib invalido: {e}") from e
    if len(saida) > limite or d.unconsumed_tail:
        raise ErroFormato(f"zlib descompactado passa do limite de {limite} bytes")
    return saida


def gzip_descompactar(dados: bytes, limite: int = LIMITE_PADRAO_BYTES) -> bytes:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(dados)) as g:
            saida = g.read(limite + 1)
    except (OSError, EOFError, zlib.error) as e:
        raise ErroFormato(f"gzip invalido: {e}") from e
    if len(saida) > limite:
        raise ErroFormato(f"gzip descompactado passa do limite de {limite} bytes")
    return saida


DESCOMPACTADORES = {
    "yaz0": yaz0_descompactar,
    "yay0": yay0_descompactar,
    "lz10": lz10_descompactar,
    "lz11": lz11_descompactar,
    "zlib": zlib_descompactar,
    "gzip": gzip_descompactar,
}


def _zlib_valido(c: bytes) -> bool:
    if len(c) < 2:
        return False
    cmf, flg = c[0], c[1]
    return (cmf & 0x0F) == 8 and (cmf >> 4) <= 7 and ((cmf << 8) | flg) % 31 == 0 and not (flg & 0x20)


def detectar(cabeca: bytes, tamanho_arquivo: int) -> Deteccao | None:
    """Detecta compressao pelos primeiros bytes. Confianca menor para assinaturas fracas."""
    if cabeca[:4] == b"Yaz0" and len(cabeca) >= 8:
        return Deteccao("yaz0", 0.98, struct.unpack_from(">I", cabeca, 4)[0])
    if cabeca[:4] == b"Yay0" and len(cabeca) >= 8:
        return Deteccao("yay0", 0.98, struct.unpack_from(">I", cabeca, 4)[0])
    if cabeca[:2] == b"\x1f\x8b":
        return Deteccao("gzip", 0.95, None)
    if cabeca[:4] == b"\x28\xb5\x2f\xfd":
        return Deteccao("zstd", 0.95, None)
    if cabeca[:4] == b"\x04\x22\x4d\x18":
        return Deteccao("lz4", 0.95, None)
    if cabeca[:6] == b"\xfd7zXZ\x00":
        return Deteccao("xz", 0.95, None)
    if cabeca[:3] == b"BZh" and len(cabeca) > 3 and 0x31 <= cabeca[3] <= 0x39:
        return Deteccao("bzip2", 0.9, None)
    if cabeca[:8] == b"CRILAYLA":
        return Deteccao("crilayla", 0.95, None)
    if _zlib_valido(cabeca) and tamanho_arquivo > 8:
        return Deteccao("zlib", 0.6, None)
    if len(cabeca) >= 4 and cabeca[0] in (0x10, 0x11) and tamanho_arquivo > 8:
        tam = cabeca[1] | cabeca[2] << 8 | cabeca[3] << 16
        # assinatura fraca: so conta se a razao de compressao for plausivel
        if tamanho_arquivo < tam <= tamanho_arquivo * 12:
            return Deteccao("lz10" if cabeca[0] == 0x10 else "lz11", 0.35, tam)
    return None
