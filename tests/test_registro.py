from __future__ import annotations

import struct

from cew.registro import Identificacao, Registro, aplicar_contexto, aplicar_gemini, identificar_arquivo


def reg():
    return Registro.carregar()


def test_assinatura(amostras):
    i = identificar_arquivo(amostras / "nintendo/arquivo.arc")
    assert (i.id, i.camada) == ("nintendo.u8", "assinatura") and i.confianca >= 0.9


def test_tim_contra_renderware_desempatado_pela_estrutura(amostras):
    i = identificar_arquivo(amostras / "sony/imagem4.tim")
    assert i.id == "sony.psx.tim" and i.camada == "estrutura" and "renderware.dff" in i.candidatos
    # chunk RenderWare Clump valido: id 0x10, tamanho que cabe, carimbo de versao 3.x (formato novo)
    dff = struct.pack("<III", 0x10, 4, 0x1803FFFF) + b"\x00" * 4
    j = reg().identificar(dff, dff, len(dff), "carro.dff")
    assert j.id == "renderware.dff"


def test_sem_assinatura_extensao_e_estrutura(amostras):
    i = identificar_arquivo(amostras / "generico/imagem.tga")
    assert (i.id, i.camada) == ("generico.tga", "estrutura")


def test_extensao_sem_assinatura_esperada_tem_confianca_baixa():
    i = reg().identificar(b"nada aqui", b"nada aqui", 9, "x.vag")
    assert i.id == "sony.ps.vag" and i.confianca < 0.3


def test_desconhecido(amostras):
    i = identificar_arquivo(amostras / "desconhecido/misterio.xyz")
    assert i.id is None and i.camada == "nenhuma"


def test_assinatura_no_fim_do_arquivo():
    corpo = b"\x00" * 100 + bytes.fromhex("e1126f5a") + b"\x00" * 40
    i = reg().identificar(corpo[:64], corpo[-64:], len(corpo), "jogo.pak")
    assert i.id == "epic.unreal.pak"


def test_camada_contexto_e_gemini():
    r = reg()
    base = Identificacao(None, "nenhuma", 0.0)
    regra = [{"padrao": "*.xyz", "formato_id": "generico.tabela_texto", "confianca": 0.85, "evidencia": {"fonte": "ghidra", "funcao": "carregar"}}]
    c = aplicar_contexto(base, "dados/a.xyz", regra, r)
    assert (c.id, c.camada) == ("generico.tabela_texto", "contexto") and "carregar" in c.evidencia
    g = aplicar_gemini(base, {"formato_id_proposto": "x.y.z", "confianca": 0.9, "tipo": "dados"}, r)
    assert g.camada == "gemini" and g.confianca == 0.6  # teto: hipotese do Gemini nunca passa de 0.6
