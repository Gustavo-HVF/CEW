from __future__ import annotations

import json

import pytest

from cew.gemini import ClienteGemini, ErroGemini, Parte, USO_SESSAO
from tests.conftest import resposta_gemini


def test_teste_real_usa_contrato_rest(gemini_falso):
    r = ClienteGemini().testar()
    assert r["teste_ok"] and r["tipo_erro"] is None
    ch = gemini_falso["chamadas"][0]
    assert ch["url"].endswith(":generateContent") and "/models/" in ch["url"]
    assert "x-goog-api-key" in ch["cabecalhos"] and "key=" not in ch["url"]
    gen = ch["corpo"]["generationConfig"]
    assert gen["responseMimeType"] == "application/json" and "responseJsonSchema" in gen
    assert "systemInstruction" in ch["corpo"]


def test_sem_chave(monkeypatch):
    c = ClienteGemini(chave="")
    c.chave = None
    r = c.testar()
    assert r["tipo_erro"] == "sem_chave" and not r["teste_ok"]


@pytest.mark.parametrize("status,corpo,tipo", [
    (400, {"error": {"code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT", "details": [{"reason": "API_KEY_INVALID"}]}}, "chave_invalida"),
    (429, {"error": {"code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED"}}, "cota"),
    (404, {"error": {"code": 404, "message": "models/x is not found", "status": "NOT_FOUND"}}, "modelo"),
    (403, {"error": {"code": 403, "message": "denied", "status": "PERMISSION_DENIED"}}, "permissao"),
])
def test_classificacao_de_erros(gemini_falso, status, corpo, tipo):
    gemini_falso["respostas"].extend([(status, json.dumps(corpo).encode())] * 5)
    assert ClienteGemini().testar()["tipo_erro"] == tipo


def test_resposta_invalida_e_refeita(gemini_falso):
    gemini_falso["respostas"].extend([resposta_gemini({"nao": "ok"}), resposta_gemini({"ok": True})])
    assert ClienteGemini().testar()["teste_ok"]
    assert len(gemini_falso["chamadas"]) == 2


def test_falha_depois_de_n_tentativas(gemini_falso):
    gemini_falso["respostas"].extend([resposta_gemini({"errado": 1})] * 10)
    c = ClienteGemini()
    with pytest.raises(ErroGemini) as e:
        c.gerar("x", [Parte(texto="oi")], "gemini/resposta_teste_conexao", usar_cache=False)
    assert e.value.tipo == "resposta_invalida" and len(gemini_falso["chamadas"]) == c.config["tentativas"]


def test_cache_por_hash_evita_segunda_chamada(gemini_falso):
    c = ClienteGemini()
    a = c.gerar("x", [Parte(texto="mesma pergunta")], "gemini/resposta_teste_conexao")
    b = c.gerar("x", [Parte(texto="mesma pergunta")], "gemini/resposta_teste_conexao")
    assert a == b and len(gemini_falso["chamadas"]) == 1


def test_chave_nunca_vai_para_log_nem_cache(gemini_falso, tmp_path):
    c = ClienteGemini()
    c.gerar("x", [Parte(texto="pergunta")], "gemini/resposta_teste_conexao")
    c.testar()
    textos = [p.read_text() for p in tmp_path.rglob("*") if p.is_file() and p.suffix in (".json", ".jsonl")]
    assert textos and all(c.chave not in t and "AIza" not in t for t in textos)


def test_limite_de_chamadas_da_sessao(gemini_falso):
    c = ClienteGemini()
    c.config["limite_sessao"]["max_chamadas"] = 1
    c.testar()
    r = c.testar()
    assert r["tipo_erro"] == "cota"
    assert USO_SESSAO.chamadas == 1


def test_imagem_inline_entra_no_log_so_como_hash(gemini_falso, tmp_path):
    c = ClienteGemini()
    c.gerar("x", [Parte(texto="compare"), Parte(mime="image/png", dados=b"\x89PNG...")], "gemini/resposta_teste_conexao", usar_cache=False)
    corpo = gemini_falso["chamadas"][0]["corpo"]
    assert corpo["contents"][0]["parts"][1]["inlineData"]["mimeType"] == "image/png"
    log = next((tmp_path / "logs" / "gemini").glob("*.jsonl")).read_text()
    assert "sha256" in log and "iVBOR" not in log
