"""WAV -> OGG (Vorbis ou Opus) com ffmpeg, guardando os pontos de loop nos metadados.

O OGG nao carrega o loop de forma que o navegador use, entao o loop lido do chunk 'smpl' segue
em metadados.loop (vai para asset_manifest.json). Efeitos curtos (< "max_s_wav" segundos,
padrao 2) ficam em WAV, como pede o padrao de conversao.

Determinismo: o ffmpeg sorteia o numero de serie do fluxo OGG; com "-fflags +bitexact" e
"-flags:a +bitexact" ele usa um valor fixo e nao grava a versao do codificador, entao a mesma
entrada gera os mesmos bytes (conferido em tests/test_conversores.py quando o ffmpeg existe).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from converters.comum.audio import ler_wav
from converters.comum.binario import ErroFormato
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "converters/generico/wav_to_ogg.py",
    "descricao": "Converte WAV para OGG Vorbis/Opus com ffmpeg (efeitos curtos ficam em WAV).",
    "formatos_entrada": ["generico.wav"],
    "destino": "ogg",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"codec\": \"vorbis\"|\"opus\", \"qualidade_vorbis\": 5, \"bitrate_opus\": \"128k\", \"max_s_wav\": 2.0, \"ffmpeg\": \"caminho\"}.",
}


def localizar_ffmpeg(opcoes: dict) -> str | None:
    return opcoes.get("ffmpeg") or os.environ.get("CEW_FFMPEG") or shutil.which("ffmpeg")


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    pcm = ler_wav(dados)
    meta = pcm.metadados()
    if pcm.duracao_s < float(opcoes.get("max_s_wav", 2.0)):
        esc.gravar("audio.wav", dados, "audio", "wav", meta)
        return {"codec": "wav", "duracao_s": meta["duracao_s"]}
    ffmpeg = localizar_ffmpeg(opcoes)
    if not ffmpeg:
        raise ErroFormato("ffmpeg nao encontrado (instale ou informe a opcao 'ffmpeg')")
    codec = opcoes.get("codec", "vorbis")
    if codec == "vorbis":
        args = ["-c:a", "libvorbis", "-q:a", str(opcoes.get("qualidade_vorbis", 5))]
    elif codec == "opus":
        args = ["-c:a", "libopus", "-b:a", str(opcoes.get("bitrate_opus", "128k"))]
    else:
        raise ErroFormato(f"codec desconhecido: {codec}")
    with tempfile.TemporaryDirectory(prefix="cew-ogg-") as tmp:
        ent, sai = Path(tmp, "in.wav"), Path(tmp, "out.ogg")
        ent.write_bytes(dados)
        cmd = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-i", str(ent), "-map_metadata", "-1",
               "-fflags", "+bitexact", "-flags:a", "+bitexact", *args, str(sai)]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=float(opcoes.get("tempo_limite_s", 600)))
        if p.returncode != 0 or not sai.is_file():
            raise ErroFormato(f"ffmpeg falhou ({p.returncode}): {p.stderr.strip()[:500]}")
        ogg = sai.read_bytes()
    if codec == "opus" and pcm.loop:
        # Opus decodifica sempre a 48 kHz: os pontos de loop do manifesto ficam na taxa original
        meta.setdefault("extras", {})["taxa_decodificacao_opus_hz"] = 48000
    esc.gravar("audio.ogg", ogg, "audio", "ogg", meta)
    return {"codec": codec, "duracao_s": meta["duracao_s"]}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
