"""ZIP (tambem APK, IPA, JAR, .pk3 do Quake III) -> pasta, com protecao contra zip slip e bombas.

Arquivos cifrados dentro do ZIP sao listados e pulados (o CEW nao decifra conteudo protegido).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import io
import zipfile
import zlib

from converters.comum.binario import ErroFormato
from converters.comum.cli import Escritor, executar

INFO = {
    "arquivo": "converters/generico/zip_to_dir.py",
    "descricao": "Extrai ZIP/APK/IPA/JAR/PK3 com limites de tamanho e de razao de compressao.",
    "formatos_entrada": ["generico.zip"],
    "destino": "pasta",
    "versao": "1.0",
    "papel": "extrator",
    "epilogo": "Opcoes: {\"max_total_bytes\": 2147483648, \"max_razao\": 200}.",
}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    max_total = int(opcoes.get("max_total_bytes", 2 * 1024**3))
    max_razao = float(opcoes.get("max_razao", 200))
    try:
        z = zipfile.ZipFile(io.BytesIO(dados))
    except (zipfile.BadZipFile, ValueError, EOFError, OSError, NotImplementedError, UnicodeDecodeError) as e:
        raise ErroFormato(f"ZIP invalido: {e}") from e
    total, pulados = 0, 0
    with z:
        for info in sorted(z.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            if info.flag_bits & 0x1:
                esc.avisar(f"cifrado, pulado: {info.filename}")
                pulados += 1
                continue
            if info.compress_size and info.file_size / info.compress_size > max_razao:
                raise ErroFormato(f"razao de compressao suspeita em {info.filename}")
            total += info.file_size
            if total > max_total:
                raise ErroFormato(f"conteudo passa de {max_total} bytes")
            try:
                with z.open(info) as f:
                    corpo = f.read(info.file_size + 1)
            except (zipfile.BadZipFile, zlib.error, EOFError, NotImplementedError, RuntimeError, ValueError) as e:
                raise ErroFormato(f"ZIP corrompido em {info.filename}: {e}") from e
            if len(corpo) != info.file_size:
                raise ErroFormato(f"tamanho real diferente do declarado: {info.filename}")
            esc.gravar(info.filename, corpo, "arquivo_extraido", "bin")
    return {"arquivos": len(esc.saidas), "pulados_cifrados": pulados}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
