"""PAK do Quake / Quake II -> pasta.

Estrutura (little-endian), como no codigo-fonte publicado pela id Software
(https://github.com/id-Software/Quake-2, qcommon/qfiles.h: dpackheader_t / dpackfile_t):
  'PACK', s32 offset do diretorio, s32 tamanho do diretorio
  entrada (64 bytes): char nome[56], s32 offset, s32 tamanho
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import LeitorBinario, contagem_plausivel, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "converters/idtech/pak_to_dir.py",
    "descricao": "Extrai arquivos PAK do Quake/Quake II.",
    "formatos_entrada": ["idtech.quake.pak"],
    "destino": "pasta",
    "versao": "1.0",
    "papel": "extrator",
}


def listar(dados: bytes) -> list[tuple[str, int, int]]:
    r = LeitorBinario(dados, "little")
    exigir(r.bytes_em(0, 4) == b"PACK", "nao e PAK (magic 'PACK' ausente)")
    off, tam = r.s32_em(4), r.s32_em(8)
    exigir(off >= 12 and tam >= 0 and tam % 64 == 0, "diretorio PAK invalido")
    r.conferir(off, tam, "diretorio PAK")
    n = contagem_plausivel(tam // 64, 64, len(dados) - off, "entradas PAK")
    itens = []
    for i in range(n):
        e = off + 64 * i
        nome = r.texto_fixo_em(e, 56, "latin-1")
        o, t = r.s32_em(e + 56), r.s32_em(e + 60)
        exigir(nome != "" and t >= 0 and o >= 0, f"entrada PAK {i} invalida")
        r.conferir(o, t, f"dados de {nome}")
        itens.append((nome, o, t))
    return itens


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    itens = listar(dados)
    for nome, o, t in itens:
        esc.gravar(nome, dados[o : o + t], "arquivo_extraido", "bin")
    return {"arquivos": len(itens)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
