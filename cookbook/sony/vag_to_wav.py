"""VAG (audio PS-ADPCM do PlayStation) -> WAV PCM 16 bits com pontos de loop.

Cabecalho 'VAGp' (big-endian, 0x30 bytes): magic, u32 versao, u32 reservado, u32 tamanho dos
dados, u32 taxa de amostragem, 12 bytes reservados, 16 bytes de nome. Depois, quadros PS-ADPCM
de 16 bytes. Os pontos de loop vem das flags dos quadros (ver converters/comum/audio.py).
A conversao para OGG e feita depois por converters/generico/wav_to_ogg.py.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from converters.comum.audio import Pcm, psx_adpcm_decodificar, wav_bytes
from converters.comum.binario import LeitorBinario, exigir
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "cookbook/sony/vag_to_wav.py",
    "descricao": "Decodifica VAG (PS-ADPCM mono) para WAV PCM 16 bits, guardando os pontos de loop.",
    "formatos_entrada": ["sony.ps.vag"],
    "destino": "wav",
    "versao": "1.0",
    "papel": "conversor",
}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "big")
    exigir(r.bytes_em(0, 4) == b"VAGp", "nao e VAG (magic 'VAGp' ausente)")
    versao, tam, taxa = r.u32_em(4), r.u32_em(12), r.u32_em(16)
    exigir(1000 <= taxa <= 192000, f"taxa de amostragem implausivel: {taxa}")
    nome = r.texto_fixo_em(0x20, 16)
    corpo = dados[0x30 : 0x30 + tam] if tam else dados[0x30:]
    if tam and 0x30 + tam > len(dados):
        esc.avisar(f"tamanho declarado ({tam}) passa do arquivo; usando o que existe")
    amostras, loop = psx_adpcm_decodificar(corpo)
    pcm = Pcm(taxa, 1, [amostras], loop)
    meta = pcm.metadados()
    meta["extras"] = {"nome_interno": nome, "versao_vag": versao}
    esc.gravar("audio.wav", wav_bytes(pcm), "audio", "wav", meta)
    return {"amostras": pcm.quantidade, "taxa_hz": taxa, "loop": list(loop) if loop else None}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
