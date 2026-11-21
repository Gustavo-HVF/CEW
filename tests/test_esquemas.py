"""Esquemas: draft 2020-12 validos, exemplos validos, configs e registro validos, contrato com o Gemini."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from cew import esquemas
from cew.gemini import PALAVRAS_RESPONSE_JSON_SCHEMA, para_response_json_schema

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLOS = sorted((RAIZ / "schemas" / "exemplos").rglob("*.json"))


def test_todos_os_esquemas_sao_validos():
    nomes = esquemas.nomes_esquemas()
    assert len(nomes) >= 28
    for n in nomes:
        Draft202012Validator.check_schema(esquemas.esquema(n))


@pytest.mark.parametrize("arquivo", EXEMPLOS, ids=lambda p: p.relative_to(RAIZ / "schemas" / "exemplos").as_posix())
def test_exemplos_validos(arquivo):
    nome = arquivo.relative_to(RAIZ / "schemas" / "exemplos").with_suffix("").as_posix()
    assert esquemas.erros(json.loads(arquivo.read_text(encoding="utf-8")), nome) == []


def test_todo_esquema_principal_tem_exemplo():
    com_exemplo = {p.relative_to(RAIZ / "schemas" / "exemplos").with_suffix("").as_posix() for p in EXEMPLOS}
    sem = set(esquemas.nomes_esquemas()) - com_exemplo - {"comum", "registry", "config_gemini", "config_versoes", "log_gemini"}
    assert not sem, f"esquemas sem exemplo: {sorted(sem)}"


def test_configs_e_registro():
    esquemas.ler_json(RAIZ / "config" / "gemini.json", "config_gemini")
    esquemas.ler_json(RAIZ / "config" / "versoes.json", "config_versoes")
    esquemas.ler_json(RAIZ / "config" / "cew.json", "config_cew")
    esquemas.ler_json(RAIZ / "config" / "equivalencias_api.json", "equivalencias_api")
    reg = esquemas.ler_json(RAIZ / "formats" / "registry.json", "registry")
    ids = [f["id"] for f in reg["formatos"]]
    assert len(ids) == len(set(ids))
    for f in reg["formatos"]:
        if f["conversor"]:
            assert (RAIZ / f["conversor"]).is_file(), f["id"]
        for c in f["contem"]:
            assert c in ids, (f["id"], c)


def test_cabecalho_obrigatorio_e_rejeicao():
    with pytest.raises(esquemas.ErroEsquema):
        esquemas.validar({"projeto": "x", "itens": []}, "plano_conversao")


def test_respostas_gemini_so_usam_palavras_aceitas():
    """responseJsonSchema aceita um subconjunto de JSON Schema (SDK google-genai 3.6.1)."""
    for nome in esquemas.nomes_esquemas():
        if not nome.startswith("gemini/resposta_"):
            continue
        enviado = para_response_json_schema(esquemas.esquema(nome))

        def visitar(n, caminho=""):
            if isinstance(n, dict):
                for k, v in n.items():
                    if caminho.endswith("/properties") or caminho.endswith("/$defs"):
                        visitar(v, f"{caminho}/{k}")
                        continue
                    assert k in PALAVRAS_RESPONSE_JSON_SCHEMA, f"{nome}: palavra nao aceita {k} em {caminho}"
                    if k == "enum":
                        assert all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for x in v), f"{nome}: enum so de strings/numeros"
                    visitar(v, f"{caminho}/{k}")
            elif isinstance(n, list):
                for x in n:
                    visitar(x, caminho)

        visitar(enviado)


def test_gravar_valida_antes(tmp_path):
    with pytest.raises(esquemas.ErroEsquema):
        esquemas.gravar_json(tmp_path / "x.json", {"schema_version": "1.0", "gerado_por": "cew"}, "inventario")
    assert not (tmp_path / "x.json").exists()


def test_fixtures_regeneram_identicas():
    p = subprocess.run([sys.executable, str(RAIZ / "tests" / "fixtures" / "gerar_fixtures.py"), "--conferir"], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout


@pytest.mark.skipif(not __import__("shutil").which("node") or not (RAIZ / "node_modules" / "ajv").is_dir(), reason="rode npm install para o ajv")
def test_ajv_concorda():
    p = subprocess.run(["node", str(RAIZ / "tests" / "js" / "validar_esquemas.mjs")], capture_output=True, text=True, cwd=RAIZ)
    assert p.returncode == 0, p.stderr + p.stdout
