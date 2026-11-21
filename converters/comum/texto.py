"""Textos de jogos para UTF-8: Shift-JIS, UTF-16, Latin-1 e codigos de controle.

Codigos de controle viram marcacoes "{nome}" documentadas no proprio JSON de saida
(dados/dialogos.json -> "marcacoes"). Bytes que nao decodificam viram "{byte:XX}" para nunca
perder informacao.
"""

from __future__ import annotations

CODIFICACOES = {"shift_jis": "cp932", "sjis": "cp932", "cp932": "cp932", "utf-8": "utf-8", "utf-16le": "utf-16-le", "utf-16be": "utf-16-be", "latin-1": "latin-1"}

MARCACOES_PADRAO = {
    0x0A: ("{nova_linha}", "quebra de linha (0x0A)"),
    0x09: ("{tab}", "tabulacao (0x09)"),
}


def decodificar(dados: bytes, codificacao: str, controles: dict[int, tuple[str, str]] | None = None) -> tuple[str, dict[str, str]]:
    """Decodifica preservando controles (< 0x20) como marcacoes. Devolve (texto, marcacoes usadas)."""
    cod = CODIFICACOES.get(codificacao.lower(), codificacao)
    tabela = dict(MARCACOES_PADRAO)
    if controles:
        tabela.update(controles)
    usadas: dict[str, str] = {}
    partes: list[str] = []
    passo = 2 if cod.startswith("utf-16") else 1
    i, trecho_ini = 0, 0

    def fechar(ate: int) -> None:
        if ate > trecho_ini:
            partes.append(_decodificar_trecho(dados[trecho_ini:ate], cod, usadas))

    while i < len(dados):
        if passo == 1:
            v = dados[i]
        else:
            if i + 1 >= len(dados):
                break
            v = int.from_bytes(dados[i : i + 2], "little" if cod.endswith("le") else "big")
        if v < 0x20:
            fechar(i)
            marca, desc = tabela.get(v, (f"{{ctl:{v:02X}}}", f"codigo de controle 0x{v:02X} (significado a definir)"))
            partes.append(marca)
            usadas[marca] = desc
            i += passo
            trecho_ini = i
            continue
        if passo == 1 and cod == "cp932" and (0x81 <= v <= 0x9F or 0xE0 <= v <= 0xFC):
            i += 2  # primeiro byte de caractere de 2 bytes
            continue
        i += passo
    fechar(min(i, len(dados)))
    return "".join(partes), usadas


def _decodificar_trecho(b: bytes, cod: str, usadas: dict[str, str]) -> str:
    try:
        return b.decode(cod)
    except UnicodeDecodeError:
        saida = []
        for parte in b.decode(cod, errors="surrogateescape"):
            if 0xDC80 <= ord(parte) <= 0xDCFF:
                marca = f"{{byte:{ord(parte) - 0xDC00:02X}}}"
                usadas[marca] = "byte que nao decodifica na codificacao original"
                saida.append(marca)
            else:
                saida.append(parte)
        return "".join(saida)


def separar_por_zero(dados: bytes, passo: int = 1) -> list[tuple[int, bytes]]:
    """Separa uma tabela de strings terminadas em zero, devolvendo (offset, bytes)."""
    itens, ini = [], 0
    i = 0
    while i + passo <= len(dados):
        if dados[i : i + passo] == b"\x00" * passo:
            if i > ini:
                itens.append((ini, dados[ini:i]))
            ini = i + passo
        i += passo
    if ini < len(dados) and dados[ini:].strip(b"\x00"):
        itens.append((ini, dados[ini:]))
    return itens
