"""Conversores contra as amostras sinteticas: valores corretos, determinismo, robustez e CLI."""

from __future__ import annotations

import json
import random
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest

from converters.comum.audio import ler_wav
from converters.comum.binario import ErroFormato
from converters.comum.cli import rodar
from converters.comum.cores import exp5
from converters.comum.gltf import ler_glb
from converters.comum.imagem import ler_png
from cew import conversores

RAIZ = Path(__file__).resolve().parents[1]

CASOS = [
    ("cookbook/nintendo/yaz0_to_bin.py", "nintendo/arquivo.szs"),
    ("cookbook/nintendo/u8_to_dir.py", "nintendo/arquivo.arc"),
    ("cookbook/nintendo/sarc_to_dir.py", "nintendo/pacote.sarc"),
    ("cookbook/nintendo/tpl_to_png.py", "nintendo/texturas.tpl"),
    ("cookbook/sony/tim_to_png.py", "sony/imagem4.tim"),
    ("cookbook/sony/tim_to_png.py", "sony/imagem16.tim"),
    ("cookbook/sony/vag_to_wav.py", "sony/som.vag"),
    ("cookbook/idtech/pak_to_dir.py", "idtech/pak0.pak"),
    ("cookbook/idtech/md2_to_glb.py", "idtech/tetra.md2"),
    ("cookbook/valve/vpk_to_dir.py", "valve/pak01_dir.vpk"),
    ("cookbook/generico/dds_to_png.py", "generico/rgba.dds"),
    ("cookbook/generico/dds_to_png.py", "generico/dxt1.dds"),
    ("cookbook/generico/tga_to_png.py", "generico/imagem.tga"),
    ("converters/generico/wav_to_ogg.py", "generico/efeito.wav"),
    ("converters/generico/zip_to_dir.py", "generico/pacote.zip"),
    ("converters/generico/copiar_web.py", "web/pronto.png"),
    ("converters/dados/texto_to_json.py", "dados/textos_sjis.bin"),
]


def conv(caminho, entrada, saida, opcoes=None, dry=False):
    return conversores.rodar(caminho, entrada, saida, opcoes or {}, dry)


def png(saida: Path, nome: str):
    return ler_png((saida / nome).read_bytes())


def pixels(img):
    return [img.pixel(x, y) for y in range(img.altura) for x in range(img.largura)]


def perto(a, b, tol):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


# ----------------------------------------------------------------------------- valores
def test_yaz0_u8_extracao(amostras, tmp_path):
    r = conv("cookbook/nintendo/yaz0_to_bin.py", amostras / "nintendo/arquivo.szs", tmp_path / "y")
    assert r["ok"] and r["saidas"][0]["caminho"] == "descompactado.arc"
    assert (tmp_path / "y/descompactado.arc").read_bytes() == (amostras / "nintendo/arquivo.arc").read_bytes()
    r = conv("cookbook/nintendo/u8_to_dir.py", amostras / "nintendo/arquivo.arc", tmp_path / "u")
    assert sorted(s["caminho"] for s in r["saidas"]) == ["dados/vazio/x.bin", "leia.txt", "texturas/fundo.tpl"]
    assert (tmp_path / "u/dados/vazio/x.bin").read_bytes() == b"\x01\x02\x03"


def test_sarc(amostras, tmp_path):
    r = conv("cookbook/nintendo/sarc_to_dir.py", amostras / "nintendo/pacote.sarc", tmp_path)
    assert r["ok"] and not r["avisos"]  # hashes dos nomes conferem
    assert sorted(s["caminho"] for s in r["saidas"]) == ["Model/cubo.bin", "Tex/a.tpl", "leia.txt"]
    assert (tmp_path / "Model/cubo.bin").read_bytes().endswith(b"cubo")


def test_tpl_formatos_gx(amostras, tmp_path, referencias):
    r = conv("cookbook/nintendo/tpl_to_png.py", amostras / "nintendo/texturas.tpl", tmp_path)
    assert r["ok"] and r["estatisticas"]["formatos_gx"] == ["RGBA32", "RGB5A3", "RGB565", "IA8", "I8", "I4", "CMPR", "C8"]
    ref = [tuple(p) for p in referencias["imagem_ref_8x8"]]
    opaca = [tuple(p) for p in referencias["imagem_ref_opaca_8x8"]]
    assert pixels(png(tmp_path, "textura_000.png")) == ref  # RGBA32 sem perda
    assert all(perto(a, b, 18) for a, b in zip(pixels(png(tmp_path, "textura_001.png")), ref))  # RGB5A3
    assert all(perto(a, b, 8) for a, b in zip(pixels(png(tmp_path, "textura_002.png")), opaca))  # RGB565
    assert pixels(png(tmp_path, "textura_003.png")) == [(p[0], p[0], p[0], p[3]) for p in ref]  # IA8
    assert pixels(png(tmp_path, "textura_004.png")) == [(p[0], p[0], p[0], 255) for p in opaca]  # I8
    assert all(perto(a, (p[0], p[0], p[0], 255), 17) for a, p in zip(pixels(png(tmp_path, "textura_005.png")), opaca))  # I4
    cmpr = png(tmp_path, "textura_006.png")  # CMPR: indices 0/1 -> no maximo 2 cores por sub-bloco 4x4
    for by in range(0, 8, 4):
        for bx in range(0, 8, 4):
            assert len({cmpr.pixel(bx + x, by + y) for y in range(4) for x in range(4)}) <= 2
    c8 = pixels(png(tmp_path, "textura_007.png"))  # C8 com paleta RGB5A3 cinza
    assert c8 == [(exp5(p[0] & 0xF),) * 3 + (255,) for p in opaca]
    assert r["saidas"][0]["metadados"]["tem_alfa"] is True and r["saidas"][2]["metadados"]["tem_alfa"] is False


def test_tim(amostras, tmp_path):
    r = conv("cookbook/sony/tim_to_png.py", amostras / "sony/imagem4.tim", tmp_path / "a")
    img = png(tmp_path / "a", "imagem.png")
    for y in range(8):
        for x in range(8):
            k = (x + y) % 16
            assert img.pixel(x, y) == ((0, 0, 0, 0) if k == 0 else (exp5(k), 0, exp5(k), 255))
    r = conv("cookbook/sony/tim_to_png.py", amostras / "sony/imagem4.tim", tmp_path / "b", {"todas_cluts": True})
    assert [s["caminho"] for s in r["saidas"]] == ["imagem_clut00.png", "imagem_clut01.png"]
    conv("cookbook/sony/tim_to_png.py", amostras / "sony/imagem16.tim", tmp_path / "c")
    img = png(tmp_path / "c", "imagem.png")
    assert img.pixel(3, 5) == (exp5(12), exp5(20), 0, 255)


def test_vag_loop(amostras, tmp_path):
    r = conv("cookbook/sony/vag_to_wav.py", amostras / "sony/som.vag", tmp_path)
    assert r["ok"] and r["estatisticas"]["loop"] == [56, 140]
    pcm = ler_wav((tmp_path / "audio.wav").read_bytes())
    assert pcm.taxa_hz == 22050 and pcm.quantidade == 140 and pcm.loop == (56, 140)
    assert pcm.amostras[0][:28] == [0] * 28
    assert pcm.amostras[0][28:36] == [(i % 8) * 256 for i in range(8)]  # filtro 0, deslocamento 4
    assert r["saidas"][0]["metadados"]["loop"] == {"inicio_amostra": 56, "fim_amostra": 140}


def test_pak_vpk(amostras, tmp_path):
    r = conv("cookbook/idtech/pak_to_dir.py", amostras / "idtech/pak0.pak", tmp_path / "p")
    assert sorted(s["caminho"] for s in r["saidas"]) == ["maps/e1m1.bsp", "progs/tetra.md2"]
    r = conv("cookbook/valve/vpk_to_dir.py", amostras / "valve/pak01_dir.vpk", tmp_path / "v")
    assert r["ok"] and not r["avisos"]  # CRC32 confere
    assert sorted(s["caminho"] for s in r["saidas"]) == ["leia.txt", "materials/brick.vtf", "scripts/game.txt"]


def test_md2_glb(amostras, tmp_path):
    r = conv("cookbook/idtech/md2_to_glb.py", amostras / "idtech/tetra.md2", tmp_path)
    doc, binario = ler_glb((tmp_path / "modelo.glb").read_bytes())
    assert doc["asset"]["version"] == "2.0"
    prim = doc["meshes"][0]["primitives"][0]
    assert len(prim["targets"]) == 2 and sorted(a["name"] for a in doc["animations"]) == ["run", "stand"]
    pos = doc["accessors"][prim["attributes"]["POSITION"]]
    assert pos["count"] == 4 and "min" in pos and "max" in pos
    vista = doc["bufferViews"][pos["bufferView"]]
    pts = [struct.unpack_from("<3f", binario, vista["byteOffset"] + 12 * i) for i in range(4)]
    # vertice (255,0,0)*0.125 + (0,0,-16) no Quake (Z para cima) -> (x, z, -y) * 0.0254 no glTF
    assert any(perto(p, (31.875 * 0.0254, -16 * 0.0254, 0.0), 1e-5) for p in pts)
    assert r["saidas"][0]["metadados"]["eixo_para_cima"] == "Y"


@pytest.mark.skipif(not shutil.which("node") or not (RAIZ / "node_modules" / "gltf-validator").is_dir(), reason="rode npm install para o glTF Validator")
def test_md2_glb_validator_oficial(amostras, tmp_path):
    conv("cookbook/idtech/md2_to_glb.py", amostras / "idtech/tetra.md2", tmp_path)
    p = subprocess.run(["node", str(RAIZ / "tests/js/validar_gltf.mjs"), str(tmp_path / "modelo.glb")], capture_output=True, text=True, cwd=RAIZ)
    res = json.loads(p.stdout)
    assert res["erros"] == 0 and res["resultados"][0]["avisos"] == 0, p.stdout


def test_dds_tga(amostras, tmp_path, referencias):
    ref = [tuple(p) for p in referencias["imagem_ref_8x8"]]
    conv("cookbook/generico/dds_to_png.py", amostras / "generico/rgba.dds", tmp_path / "a")
    assert pixels(png(tmp_path / "a", "textura.png")) == ref
    conv("cookbook/generico/dds_to_png.py", amostras / "generico/dxt1.dds", tmp_path / "b")
    img = png(tmp_path / "b", "textura.png")
    assert img.pixel(0, 0) == (255, 0, 0, 255) and img.pixel(4, 0) == (255, 255, 0, 255) and img.pixel(4, 4) == (0, 0, 255, 255) and img.pixel(0, 4) == (0, 255, 0, 255)
    conv("cookbook/generico/tga_to_png.py", amostras / "generico/imagem.tga", tmp_path / "c")
    assert pixels(png(tmp_path / "c", "textura.png")) == ref


def test_wav_curto_fica_wav(amostras, tmp_path):
    r = conv("converters/generico/wav_to_ogg.py", amostras / "generico/efeito.wav", tmp_path)
    assert r["saidas"][0]["formato"] == "wav"


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg ausente")
def test_wav_para_ogg_com_loop_e_deterministico(amostras, tmp_path):
    a = conv("converters/generico/wav_to_ogg.py", amostras / "generico/musica_loop.wav", tmp_path / "a")
    b = conv("converters/generico/wav_to_ogg.py", amostras / "generico/musica_loop.wav", tmp_path / "b")
    assert a["ok"], a["erro"]
    assert a["saidas"][0]["formato"] == "ogg" and (tmp_path / "a/audio.ogg").read_bytes()[:4] == b"OggS"
    assert a["saidas"][0]["metadados"]["loop"] == {"inicio_amostra": 11025, "fim_amostra": 27562}
    assert a["saidas"][0]["sha256"] == b["saidas"][0]["sha256"]


def test_zip_e_texto(amostras, tmp_path):
    r = conv("converters/generico/zip_to_dir.py", amostras / "generico/pacote.zip", tmp_path / "z")
    assert sorted(s["caminho"] for s in r["saidas"]) == ["dados/config.json", "leia.txt"]
    r = conv("converters/dados/texto_to_json.py", amostras / "dados/textos_sjis.bin", tmp_path / "t")
    doc = json.loads((tmp_path / "t/dialogos.json").read_text(encoding="utf-8"))
    assert doc["linhas"][0]["texto"] == "こんにちは、世界！"
    assert doc["linhas"][1]["texto"] == "CEW{ctl:01}テスト{nova_linha}です"
    assert "{ctl:01}" in doc["marcacoes"]


def test_zip_slip_recusado(tmp_path):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("../../fora.txt", b"x")
    (tmp_path / "mal.zip").write_bytes(buf.getvalue())
    r = conv("converters/generico/zip_to_dir.py", tmp_path / "mal.zip", tmp_path / "saida")
    assert not r["ok"] and "inseguro" in r["erro"]
    assert not (tmp_path / "fora.txt").exists()


# --------------------------------------------------------------------- determinismo
@pytest.mark.parametrize("caminho,amostra", CASOS)
def test_deterministico(caminho, amostra, amostras, tmp_path):
    a = conv(caminho, amostras / amostra, tmp_path / "a")
    b = conv(caminho, amostras / amostra, tmp_path / "b")
    assert a["ok"], a["erro"]
    assert [(s["caminho"], s["sha256"]) for s in a["saidas"]] == [(s["caminho"], s["sha256"]) for s in b["saidas"]]


# ------------------------------------------------------------------------- robustez
@pytest.mark.parametrize("caminho,amostra", CASOS)
def test_entrada_corrompida_nao_quebra(caminho, amostra, amostras, tmp_path):
    """Arquivo truncado ou com bytes trocados: ErroFormato (ok=false) ou saida valida, nunca excecao."""
    dados = (amostras / amostra).read_bytes()
    rnd = random.Random(1234)
    variantes = [dados[:n] for n in sorted({0, 1, 4, 8, 16, 33, len(dados) // 2, len(dados) - 1}) if n < len(dados)]
    for _ in range(25):
        b = bytearray(dados)
        for _ in range(rnd.randint(1, 8)):
            b[rnd.randrange(len(b))] = rnd.randrange(256)
        variantes.append(bytes(b))
    for i, v in enumerate(variantes):
        arq = tmp_path / f"v{i}{Path(amostra).suffix}"
        arq.write_bytes(v)
        r = conv(caminho, arq, tmp_path / f"s{i}")
        assert r["ok"] or not r["erro"].startswith("falha inesperada"), (i, r["erro"])


# ------------------------------------------------------------------------------ CLI
def test_cli_help_e_dry_run(amostras, tmp_path):
    for caminho, amostra in CASOS[:6] + CASOS[8:9]:
        h = subprocess.run([sys.executable, str(RAIZ / caminho), "--help"], capture_output=True, text=True)
        assert h.returncode == 0 and "--dry-run" in h.stdout
        saida = tmp_path / Path(caminho).stem
        d = subprocess.run([sys.executable, str(RAIZ / caminho), str(amostras / amostra), "-o", str(saida), "--dry-run"], capture_output=True, text=True)
        r = json.loads(d.stdout)
        assert d.returncode == 0 and r["dry_run"] is True and r["saidas"]
        assert not saida.exists()  # dry-run nao grava nada


def test_catalogo_bate_com_registro():
    from cew.registro import Registro

    reg = Registro.carregar()
    arquivos = {i["arquivo"] for i in conversores.listar()}
    for f in reg.formatos:
        if f["conversor"]:
            assert f["conversor"] in arquivos, f["id"]
    for i in conversores.listar():
        assert i["arquivo"] == i["arquivo"].lower() and {"descricao", "formatos_entrada", "destino", "papel"} <= set(i)
        for fid in i["formatos_entrada"]:
            assert reg.get(fid) is not None, (i["arquivo"], fid)
