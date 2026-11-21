"""U8 (arquivo .arc do Wii/GameCube) -> pasta com os arquivos.

Estrutura (big-endian), descrita em https://wiibrew.org/wiki/U8_archive:
  0x00 u32 magic 0x55AA382D | 0x04 u32 offset do no raiz | 0x08 u32 tamanho nos+strings
  0x0C u32 offset dos dados | 0x10 16 bytes reservados
No (12 bytes): u8 tipo (0 arquivo, 1 pasta), u24 offset do nome na tabela de strings,
u32 (arquivo: offset dos dados; pasta: indice do pai), u32 (arquivo: tamanho; pasta: indice do
primeiro no depois da pasta). O no 0 e a raiz, e seu ultimo campo e o total de nos.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import ErroFormato, LeitorBinario, contagem_plausivel, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "converters/nintendo/u8_to_dir.py",
    "descricao": "Extrai um conteiner U8 (.arc) preservando as pastas.",
    "formatos_entrada": ["nintendo.u8"],
    "destino": "pasta",
    "versao": "1.0",
    "papel": "extrator",
}

MAGIC = 0x55AA382D


def listar(dados: bytes) -> list[tuple[str, int, int]]:
    """Devolve [(caminho, offset, tamanho)] dos arquivos."""
    r = LeitorBinario(dados, "big")
    exigir(r.u32_em(0, "magic") == MAGIC, "nao e U8 (magic 0x55AA382D ausente)")
    raiz = r.u32_em(4, "offset raiz")
    exigir(r.u8_em(raiz, "tipo raiz") == 1, "no raiz U8 nao e pasta")
    total = r.u32_em(raiz + 8, "total de nos")
    contagem_plausivel(total, 12, len(dados) - raiz, "nos U8")
    tabela_nomes = raiz + total * 12
    arquivos = []
    pilha: list[tuple[str, int]] = [("", total)]
    for i in range(1, total):
        while pilha and i >= pilha[-1][1]:
            pilha.pop()
        exigir(bool(pilha), f"no U8 {i} fora de qualquer pasta")
        base = raiz + i * 12
        tipo = r.u8_em(base)
        off_nome = r.u32_em(base) & 0x00FFFFFF
        nome = r.cstr_em(tabela_nomes + off_nome, 1024)
        exigir(nome not in ("", ".", "..") and "/" not in nome and "\\" not in nome, f"nome U8 invalido no no {i}: {nome!r}")
        caminho = f"{pilha[-1][0]}{nome}"
        a, b = r.u32_em(base + 4), r.u32_em(base + 8)
        if tipo == 1:
            exigir(i < b <= total, f"pasta U8 {caminho!r} com fim invalido ({b})")
            pilha.append((caminho + "/", b))
        elif tipo == 0:
            r.conferir(a, b, f"dados de {caminho}")
            arquivos.append((caminho, a, b))
        else:
            raise ErroFormato(f"tipo de no U8 desconhecido {tipo} em {caminho!r}")
    return arquivos


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    itens = listar(dados)
    for caminho, off, tam in itens:
        esc.gravar(caminho, dados[off : off + tam], "arquivo_extraido", "bin")
    return {"arquivos": len(itens)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
