"""SARC (Wii U / 3DS / Switch) -> pasta com os arquivos.

Estrutura descrita em https://zeldamods.org/wiki/SARC:
  SARC (0x14): magic, u16 tamanho do cabecalho, u16 BOM (FEFF = big, FFFE = little),
               u32 tamanho do arquivo, u32 offset dos dados, u16 versao, u16 reservado
  SFAT (0x0C): magic, u16 tamanho, u16 quantidade de nos, u32 chave do hash (0x65)
  no (0x10):   u32 hash do nome, u32 atributos (byte alto 1 = tem nome; 16 bits baixos = offset
               do nome / 4 dentro do SFNT), u32 inicio e u32 fim relativos ao offset dos dados
  SFNT (0x08): magic, u16 tamanho, u16 reservado; nomes terminados em zero, alinhados a 4
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import LeitorBinario, contagem_plausivel, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "cookbook/nintendo/sarc_to_dir.py",
    "descricao": "Extrai um conteiner SARC (.sarc, .pack, .bars...), conferindo o hash de cada nome.",
    "formatos_entrada": ["nintendo.sarc"],
    "destino": "pasta",
    "versao": "1.0",
    "papel": "extrator",
}


def hash_nome(nome: bytes, chave: int) -> int:
    h = 0
    for c in nome:
        h = (h * chave + c) & 0xFFFFFFFF
    return h


def listar(dados: bytes) -> tuple[list[tuple[str, int, int]], list[str]]:
    exigir(dados[:4] == b"SARC", "nao e SARC")
    bom = dados[6:8]
    exigir(bom in (b"\xfe\xff", b"\xff\xfe"), f"BOM SARC invalido: {bom.hex()}")
    r = LeitorBinario(dados, "big" if bom == b"\xfe\xff" else "little")
    tam_cab = r.u16_em(4)
    off_dados = r.u32_em(0x0C, "offset dos dados")
    exigir(off_dados <= len(dados), "offset de dados SARC fora do arquivo")
    sfat = tam_cab
    exigir(r.bytes_em(sfat, 4) == b"SFAT", "bloco SFAT ausente")
    tam_sfat, qtd, chave = r.u16_em(sfat + 4), r.u16_em(sfat + 6), r.u32_em(sfat + 8)
    contagem_plausivel(qtd, 16, len(dados) - sfat - tam_sfat, "nos SFAT")
    sfnt = sfat + tam_sfat + qtd * 16
    exigir(r.bytes_em(sfnt, 4) == b"SFNT", "bloco SFNT ausente")
    nomes_base = sfnt + r.u16_em(sfnt + 4)
    itens, avisos = [], []
    for i in range(qtd):
        n = sfat + tam_sfat + i * 16
        h, attr, ini, fim = r.u32_em(n), r.u32_em(n + 4), r.u32_em(n + 8), r.u32_em(n + 12)
        if attr >> 24 == 1:
            nome = r.cstr_em(nomes_base + (attr & 0xFFFF) * 4, 1024)
            if hash_nome(nome.encode("utf-8"), chave) != h:
                avisos.append(f"hash do nome nao confere: {nome}")
        else:
            nome = f"_sem_nome/{h:08x}.bin"
        exigir(not nome.startswith("/") and ".." not in nome.split("/"), f"nome SARC inseguro: {nome!r}")
        exigir(ini <= fim, f"intervalo invalido em {nome}")
        r.conferir(off_dados + ini, fim - ini, f"dados de {nome}")
        itens.append((nome, off_dados + ini, fim - ini))
    return itens, avisos


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    itens, avisos = listar(dados)
    for a in avisos:
        esc.avisar(a)
    for nome, off, tam in itens:
        esc.gravar(nome, dados[off : off + tam], "arquivo_extraido", "bin")
    return {"arquivos": len(itens), "ordem_de_bytes": "big" if dados[6:8] == b"\xfe\xff" else "little"}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
