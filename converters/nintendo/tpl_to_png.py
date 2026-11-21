"""TPL (texturas do GameCube/Wii) -> PNG.

Estrutura (big-endian), descrita em https://wiki.tockdom.com/wiki/TPL_(File_Format):
  0x00 u32 magic 0x0020AF30 | 0x04 u32 quantidade de imagens | 0x08 u32 offset da tabela
  tabela: por imagem, u32 offset do cabecalho da imagem e u32 offset do cabecalho da paleta (0 = sem)
  imagem (0x24): u16 altura, u16 largura, u32 formato, u32 offset dos dados, wrapS, wrapT,
                 minFilter, magFilter (u32), f32 LODBias, u8 edgeLOD, u8 minLOD, u8 maxLOD, u8
  paleta (0x0C): u16 quantidade, u8, u8, u32 formato da paleta, u32 offset dos dados
So o nivel 0 de mipmap e exportado; os mipmaps sao regenerados na web.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.binario import LeitorBinario, contagem_plausivel, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.imagem import png_bytes
from converters.comum.texturas import GX_FORMATOS, decodificar_gx, decodificar_paleta_gx, gx_tamanho_dados

INFO = {
    "arquivo": "converters/nintendo/tpl_to_png.py",
    "descricao": "Converte texturas TPL (I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA32, C4, C8, C14X2, CMPR) para PNG.",
    "formatos_entrada": ["nintendo.gx.tpl"],
    "destino": "png",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"espaco_cor\": \"srgb\"|\"linear\"} (use linear para mapas de normal/rugosidade).",
}

MAGIC = 0x0020AF30


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "big")
    exigir(r.u32_em(0, "magic") == MAGIC, "nao e TPL (magic 0x0020AF30 ausente)")
    qtd, tabela = r.u32_em(4), r.u32_em(8)
    contagem_plausivel(qtd, 8, len(dados) - tabela, "imagens TPL")
    espaco = opcoes.get("espaco_cor", "srgb")
    formatos = []
    for i in range(qtd):
        off_img, off_pal = r.u32_em(tabela + 8 * i), r.u32_em(tabela + 8 * i + 4)
        alt, larg, fmt, off_dados = r.u16_em(off_img), r.u16_em(off_img + 2), r.u32_em(off_img + 4), r.u32_em(off_img + 8)
        nome_fmt = GX_FORMATOS.get(fmt)
        exigir(nome_fmt is not None, f"imagem {i}: formato GX desconhecido {fmt}")
        paleta = None
        if nome_fmt in ("C4", "C8", "C14X2"):
            exigir(off_pal != 0, f"imagem {i}: formato {nome_fmt} sem paleta")
            n_cores, fmt_pal, off_pdados = r.u16_em(off_pal), r.u32_em(off_pal + 4), r.u32_em(off_pal + 8)
            paleta = decodificar_paleta_gx(r.bytes_em(off_pdados, n_cores * 2, "paleta"), fmt_pal, n_cores)
        tam = gx_tamanho_dados(nome_fmt, larg, alt)
        img = decodificar_gx(r.bytes_em(off_dados, tam, f"dados da imagem {i}"), nome_fmt, larg, alt, paleta)
        min_lod, max_lod = r.u8_em(off_img + 0x21), r.u8_em(off_img + 0x22)
        if max_lod > min_lod:
            esc.avisar(f"imagem {i}: {max_lod - min_lod} niveis de mipmap ignorados (regenerar na web)")
        if not img.potencia_de_2:
            esc.avisar(f"imagem {i}: dimensoes {larg}x{alt} nao sao potencia de 2")
        nome = "textura.png" if qtd == 1 else f"textura_{i:03d}.png"
        meta = img.metadados(espaco)
        meta["extras"] = {"formato_gx": nome_fmt}
        esc.gravar(nome, png_bytes(img), "textura", "png", meta)
        formatos.append(nome_fmt)
    return {"imagens": qtd, "formatos_gx": formatos}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
