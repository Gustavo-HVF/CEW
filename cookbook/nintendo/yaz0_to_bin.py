"""Yaz0 (SZS e afins, Nintendo GameCube/Wii/Switch) -> arquivo descompactado.

Formato: 'Yaz0', u32 BE tamanho descompactado, 8 bytes reservados, dados LZ (ver
converters/comum/compressao.py). O conteudo costuma ser um conteiner U8/RARC/SARC.
"""

from __future__ import annotations

if __package__ in (None, ""):  # permite `python cookbook/nintendo/yaz0_to_bin.py`
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.cli import Escritor, executar
from converters.comum.compressao import yaz0_descompactar

INFO = {
    "arquivo": "cookbook/nintendo/yaz0_to_bin.py",
    "descricao": "Descompacta Yaz0 (.szs, .yaz0, .carc) para o arquivo original.",
    "formatos_entrada": ["nintendo.yaz0"],
    "destino": "bin (tipicamente U8/RARC/SARC)",
    "versao": "1.0",
    "papel": "descompactador",
    "epilogo": "Opcoes: {\"nome_saida\": \"x.arc\"}. Sem nome, a extensao vem do conteudo (U8 -> .arc, SARC -> .sarc, RARC -> .rarc).",
}

_EXTENSAO_POR_MAGIC = {b"\x55\xaa\x38\x2d": ".arc", b"SARC": ".sarc", b"RARC": ".rarc", b"bres": ".brres", b"FRES": ".bfres"}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    saida = yaz0_descompactar(dados)
    nome = opcoes.get("nome_saida") or ("descompactado" + _EXTENSAO_POR_MAGIC.get(saida[:4], ".bin"))
    esc.gravar(nome, saida, "arquivo_extraido", "bin")
    return {"tamanho_compactado": len(dados), "tamanho_descompactado": len(saida)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
