"""Arquivos que a web ja le (PNG, JPEG, WebP, KTX2, OGG, MP3, WAV, GLB, MIDI, JSON) -> copia conferida.

Confere a assinatura antes de copiar, para um arquivo com extensao errada nao entrar no jogo.
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import json

from converters.comum.audio import ler_wav
from converters.comum.binario import ErroFormato
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "converters/generico/copiar_web.py",
    "descricao": "Copia arquivos ja prontos para a web, conferindo a assinatura.",
    "formatos_entrada": ["generico.png", "generico.jpeg", "generico.webp", "generico.ktx2", "generico.ogg", "generico.mp3", "generico.wav", "khronos.gltf.glb", "generico.midi", "generico.json"],
    "destino": "o mesmo formato",
    "versao": "1.0",
    "papel": "conversor",
}

TIPOS = [
    (b"\x89PNG\r\n\x1a\n", "png", "textura"), (b"\xff\xd8\xff", "jpg", "textura"), (b"\xabKTX 20\xbb\r\n\x1a\n", "ktx2", "textura"),
    (b"OggS", "ogg", "audio"), (b"ID3", "mp3", "audio"), (b"glTF", "glb", "modelo"), (b"MThd", "mid", "audio"),
]


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    for magic, ext, tipo in TIPOS:
        if dados.startswith(magic):
            esc.gravar(f"arquivo.{ext}", dados, tipo, ext)
            return {"formato": ext}
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        esc.gravar("arquivo.webp", dados, "textura", "webp")
        return {"formato": "webp"}
    if dados[:4] == b"RIFF" and dados[8:12] == b"WAVE":
        meta = ler_wav(dados).metadados()
        esc.gravar("arquivo.wav", dados, "audio", "wav", meta)
        return {"formato": "wav"}
    if len(dados) >= 2 and dados[0] == 0xFF and dados[1] & 0xE0 == 0xE0:
        esc.gravar("arquivo.mp3", dados, "audio", "mp3")
        return {"formato": "mp3"}
    try:
        json.loads(dados.decode("utf-8"))
        esc.gravar("arquivo.json", dados, "dados", "json")
        return {"formato": "json"}
    except (UnicodeDecodeError, ValueError):
        pass
    raise ErroFormato("assinatura nao corresponde a nenhum formato web conhecido")


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
