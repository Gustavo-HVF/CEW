"""Configuracao comum: cada teste roda com projects/ e logs/ temporarios."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

AMOSTRAS = RAIZ / "tests" / "fixtures" / "amostras"


@pytest.fixture(autouse=True)
def isolar(tmp_path, monkeypatch):
    monkeypatch.setenv("CEW_PROJETOS", str(tmp_path / "projects"))
    monkeypatch.setenv("CEW_LOGS", str(tmp_path / "logs"))
    monkeypatch.setenv("CEW_REPORTS", str(tmp_path / "reports"))
    monkeypatch.setenv("CEW_NAO_INTERATIVO", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import cew.gemini as g

    g.USO_SESSAO.__init__()
    yield


@pytest.fixture
def amostras() -> Path:
    return AMOSTRAS


@pytest.fixture
def referencias() -> dict:
    return json.loads((AMOSTRAS / "referencias.json").read_text())


def resposta_gemini(obj: dict, tokens: int = 10) -> bytes:
    return json.dumps({"candidates": [{"content": {"parts": [{"text": json.dumps(obj)}]}, "finishReason": "STOP"}],
                       "usageMetadata": {"promptTokenCount": tokens, "candidatesTokenCount": tokens}}).encode()


@pytest.fixture
def gemini_falso(monkeypatch, tmp_path):
    """ClienteGemini com transporte falso; devolve a lista de chamadas feitas."""
    import cew.gemini as g

    chamadas: list = []
    respostas: list = []

    def transporte(metodo, url, cab, corpo, tempo):
        chamadas.append({"metodo": metodo, "url": url, "cabecalhos": dict(cab), "corpo": json.loads(corpo) if corpo else None})
        if respostas:
            r = respostas.pop(0)
            return r if isinstance(r, tuple) else (200, r)
        esquema = json.loads(corpo)["generationConfig"].get("responseJsonSchema", {}) if corpo else {}
        if "ok" in esquema.get("properties", {}):
            return 200, resposta_gemini({"ok": True})
        return 200, resposta_gemini({"schema_version": "1.0", "gerado_por": "cew-gemini-worker", "formato_id_proposto": "teste.qzx.misterio",
                                     "confianca": 0.5, "ordem_de_bytes": "big", "cabecalho": [{"campo": "magic", "offset": 0, "tipo": "char[4]", "evidencia": "QZX1"}],
                                     "secoes": [], "duvidas": []})

    original = g.ClienteGemini.__post_init__

    def post(self):
        self.config = self.config or {}
        original(self)
        self.transporte = transporte
        self.chave = "AIzaTESTE_TESTE_TESTE_TESTE_TESTE_TESTE_12"
        self.config["cache"] = {"ativo": True, "pasta": str(tmp_path / "cache")}
        self.config["espera_entre_tentativas_s"] = 0

    monkeypatch.setattr(g.ClienteGemini, "__post_init__", post)
    return {"chamadas": chamadas, "respostas": respostas}
