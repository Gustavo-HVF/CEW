"""VPK (Valve, Source) -> pasta. Versoes 1 e 2.

Estrutura descrita em https://developer.valvesoftware.com/wiki/VPK_(file_format):
  cabecalho: u32 0x55AA1234, u32 versao, u32 tamanho da arvore; a v2 acrescenta 4 u32
             (secao de dados, MD5 de arquivos, MD5 geral, assinatura) -> 12 ou 28 bytes
  arvore: extensao\\0 { caminho\\0 { nome\\0 entrada }* \\0 }* \\0 ... ; " " = vazio
  entrada: u32 CRC, u16 bytes de preload, u16 indice do arquivo (0x7FFF = este arquivo,
           dados depois da arvore), u32 offset, u32 tamanho, u16 0xFFFF, preload
Arquivos de dados separados (pak01_000.vpk...) sao lidos da mesma pasta quando a opcao
"pasta_vpk" e informada (o orquestrador informa a pasta do _dir.vpk).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import zlib
from pathlib import Path

from converters.comum.binario import ErroFormato, LeitorBinario, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "cookbook/valve/vpk_to_dir.py",
    "descricao": "Extrai pacotes VPK v1/v2 (Source), conferindo o CRC32 de cada arquivo.",
    "formatos_entrada": ["valve.source.vpk"],
    "destino": "pasta",
    "versao": "1.0",
    "papel": "extrator",
    "epilogo": "Opcoes: {\"pasta_vpk\": \"<pasta com pak01_000.vpk...>\", \"nome_base\": \"pak01\"}.",
}

MAGIC = 0x55AA1234


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "little")
    exigir(r.u32_em(0, "magic") == MAGIC, "nao e VPK (magic 0x55AA1234 ausente)")
    versao, tam_arvore = r.u32_em(4), r.u32_em(8)
    exigir(versao in (1, 2), f"versao VPK {versao} nao suportada")
    cab = 12 if versao == 1 else 28
    fim_arvore = cab + tam_arvore
    r.conferir(cab, tam_arvore, "arvore VPK")
    pasta = Path(opcoes["pasta_vpk"]) if opcoes.get("pasta_vpk") else None
    base = opcoes.get("nome_base")
    abertos: dict[int, bytes] = {}
    r.ir(cab)
    total, faltando = 0, 0

    def ler_cstr() -> str:
        s = r.cstr_em(r.pos, 1024, "utf-8")
        r.pular(len(s.encode("utf-8")) + 1)
        return s

    while True:
        ext = ler_cstr()
        if ext == "":
            break
        while True:
            caminho = ler_cstr()
            if caminho == "":
                break
            while True:
                nome = ler_cstr()
                if nome == "":
                    break
                crc, preload, arq, off, tam = r.u32(), r.u16(), r.u16(), r.u32(), r.u32()
                exigir(r.u16() == 0xFFFF, f"terminador de entrada VPK ausente em {nome}")
                dados_pre = r.ler(preload, "preload")
                rel = "/".join(p for p in (caminho.strip() if caminho != " " else "", nome) if p)
                if ext != " ":
                    rel += "." + ext
                corpo = b""
                if tam:
                    if arq == 0x7FFF:
                        corpo = r.bytes_em(fim_arvore + off, tam, f"dados de {rel}")
                    else:
                        if arq not in abertos:
                            if not (pasta and base):
                                esc.avisar(f"{rel}: dados em {arq:03d}.vpk; informe pasta_vpk e nome_base")
                                faltando += 1
                                continue
                            alvo = pasta / f"{base}_{arq:03d}.vpk"
                            if not alvo.is_file():
                                esc.avisar(f"{rel}: {alvo.name} nao encontrado")
                                faltando += 1
                                continue
                            abertos[arq] = alvo.read_bytes()
                        bloco = abertos[arq]
                        if off + tam > len(bloco):
                            raise ErroFormato(f"{rel}: dados passam do fim de {base}_{arq:03d}.vpk")
                        corpo = bloco[off : off + tam]
                conteudo = dados_pre + corpo
                if zlib.crc32(conteudo) & 0xFFFFFFFF != crc:
                    esc.avisar(f"CRC32 nao confere: {rel}")
                esc.gravar(rel, conteudo, "arquivo_extraido", "bin")
                total += 1
    return {"arquivos": total, "faltando": faltando, "versao": versao}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
