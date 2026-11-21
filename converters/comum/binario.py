"""Leitura binaria defensiva (item 11).

Todo acesso confere limites antes de ler: um arquivo corrompido gera ErroFormato, nunca uma
leitura fora do buffer, um laco infinito ou uma alocacao gigante.
"""

from __future__ import annotations

import struct
from typing import Literal

Ordem = Literal["big", "little"]

# Teto padrao para tamanhos declarados dentro de arquivos (descompactado, contagens etc.).
LIMITE_PADRAO_BYTES = 512 * 1024 * 1024


class ErroFormato(ValueError):
    """Dados nao batem com o formato esperado (tamanho, offset, assinatura)."""


class LeitorBinario:
    def __init__(self, dados: bytes | bytearray | memoryview, ordem: Ordem = "little", base: int = 0):
        self.dados = memoryview(dados).cast("B") if not isinstance(dados, memoryview) else dados
        self.ordem: Ordem = ordem
        self.base = base
        self.pos = 0

    # --- utilitarios --------------------------------------------------------------------------
    def __len__(self) -> int:
        return len(self.dados)

    @property
    def _p(self) -> str:
        return ">" if self.ordem == "big" else "<"

    def conferir(self, offset: int, tamanho: int, oque: str = "dados") -> None:
        if offset < 0 or tamanho < 0 or offset + tamanho > len(self.dados):
            raise ErroFormato(
                f"{oque}: leitura de {tamanho} bytes em 0x{offset + self.base:X} passa do fim (tamanho 0x{len(self.dados):X})"
            )

    def ir(self, offset: int) -> "LeitorBinario":
        if offset < 0 or offset > len(self.dados):
            raise ErroFormato(f"offset 0x{offset:X} fora do arquivo (tamanho 0x{len(self.dados):X})")
        self.pos = offset
        return self

    def pular(self, n: int) -> None:
        self.ir(self.pos + n)

    def restante(self) -> int:
        return len(self.dados) - self.pos

    # --- leituras em posicao absoluta --------------------------------------------------------
    def bytes_em(self, offset: int, tamanho: int, oque: str = "bytes") -> bytes:
        self.conferir(offset, tamanho, oque)
        return bytes(self.dados[offset : offset + tamanho])

    def _un(self, fmt: str, offset: int, oque: str):
        n = struct.calcsize(fmt)
        self.conferir(offset, n, oque)
        return struct.unpack_from(self._p + fmt, self.dados, offset)[0]

    def u8_em(self, o: int, oque: str = "u8") -> int:
        return self._un("B", o, oque)

    def s8_em(self, o: int, oque: str = "s8") -> int:
        return self._un("b", o, oque)

    def u16_em(self, o: int, oque: str = "u16") -> int:
        return self._un("H", o, oque)

    def s16_em(self, o: int, oque: str = "s16") -> int:
        return self._un("h", o, oque)

    def u32_em(self, o: int, oque: str = "u32") -> int:
        return self._un("I", o, oque)

    def s32_em(self, o: int, oque: str = "s32") -> int:
        return self._un("i", o, oque)

    def u64_em(self, o: int, oque: str = "u64") -> int:
        return self._un("Q", o, oque)

    def f32_em(self, o: int, oque: str = "f32") -> float:
        return self._un("f", o, oque)

    def cstr_em(self, offset: int, limite: int = 4096, codificacao: str = "utf-8") -> str:
        """String terminada em zero; erro se nao houver terminador dentro do limite/arquivo."""
        if offset < 0 or offset >= len(self.dados):
            raise ErroFormato(f"string em 0x{offset:X} fora do arquivo")
        fim = min(len(self.dados), offset + limite)
        trecho = bytes(self.dados[offset:fim])
        z = trecho.find(b"\x00")
        if z < 0:
            raise ErroFormato(f"string em 0x{offset:X} sem terminador em {limite} bytes")
        return trecho[:z].decode(codificacao, errors="replace")

    def texto_fixo_em(self, offset: int, tamanho: int, codificacao: str = "ascii") -> str:
        b = self.bytes_em(offset, tamanho, "texto")
        return b.split(b"\x00", 1)[0].decode(codificacao, errors="replace")

    # --- leituras sequenciais -----------------------------------------------------------------
    def _seq(self, fn, n: int, oque: str):
        v = fn(self.pos, oque)
        self.pos += n
        return v

    def u8(self, oque: str = "u8") -> int:
        return self._seq(self.u8_em, 1, oque)

    def u16(self, oque: str = "u16") -> int:
        return self._seq(self.u16_em, 2, oque)

    def s16(self, oque: str = "s16") -> int:
        return self._seq(self.s16_em, 2, oque)

    def u32(self, oque: str = "u32") -> int:
        return self._seq(self.u32_em, 4, oque)

    def s32(self, oque: str = "s32") -> int:
        return self._seq(self.s32_em, 4, oque)

    def f32(self, oque: str = "f32") -> float:
        return self._seq(self.f32_em, 4, oque)

    def ler(self, n: int, oque: str = "bytes") -> bytes:
        b = self.bytes_em(self.pos, n, oque)
        self.pos += n
        return b


def exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise ErroFormato(mensagem)


def limitar_tamanho(declarado: int, limite: int = LIMITE_PADRAO_BYTES, oque: str = "tamanho declarado") -> int:
    if declarado < 0 or declarado > limite:
        raise ErroFormato(f"{oque} ({declarado} bytes) acima do limite de {limite} bytes")
    return declarado


def contagem_plausivel(n: int, tamanho_item: int, bytes_disponiveis: int, oque: str = "contagem") -> int:
    """Uma contagem lida do arquivo so e aceita se os itens cabem nos bytes que restam."""
    if n < 0 or n * max(1, tamanho_item) > bytes_disponiveis:
        raise ErroFormato(f"{oque} = {n} nao cabe nos {bytes_disponiveis} bytes restantes")
    return n


def alinhar(valor: int, alinhamento: int) -> int:
    return (valor + alinhamento - 1) // alinhamento * alinhamento
