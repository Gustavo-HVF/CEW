"""Skills: cabecalho YAML (name, description) e as oito secoes pedidas; documentos obrigatorios presentes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
SECOES = ["Gatilho", "Entradas", "Passos com comandos", "Delegacao", "Padroes de conversao", "Saidas", "Criterios para avancar", "Erros comuns e o que fazer"]
SKILLS = sorted((RAIZ / "skills").glob("*/SKILL.md"))


def test_seis_skills():
    assert [p.parent.name for p in SKILLS] == [
        "01-setup-e-validacao-gemini", "02-inventario-e-mapeamento-de-formatos", "03-engenharia-reversa-craft-ghidra",
        "04-delegacao-gemini-e-conversores", "05-selecao-e-arquitetura-motor-grafico", "06-verificacao-e-refinamento-web"]


@pytest.mark.parametrize("arq", SKILLS, ids=lambda p: p.parent.name)
def test_formato_da_skill(arq):
    texto = arq.read_text(encoding="utf-8")
    m = re.match(r"^---\nname: ([a-z0-9-]+)\ndescription: (.+)\n---\n", texto)
    assert m, "cabecalho YAML com name e description"
    assert len(m.group(2)) > 40
    secoes = re.findall(r"^## (.+)$", texto, flags=re.M)
    assert secoes == SECOES


def test_comandos_citados_existem():
    from cew.cli import parser

    subs = set(parser()._subparsers._group_actions[0].choices)  # type: ignore[union-attr]
    for arq in SKILLS:
        for cmd in re.findall(r"`cew ([a-z]+)", arq.read_text(encoding="utf-8")):
            assert cmd in subs, (arq.parent.name, cmd)


def test_documentos_obrigatorios():
    for rel in ["README.md", ".env.example", ".gitignore", "pyproject.toml", "requirements.txt", "package.json", "config/versoes.json", "config/gemini.json",
                ".vscode/tasks.json", ".vscode/settings.json", ".vscode/launch.json", ".vscode/mcp.json", "scripts/setup_craft_anything.py",
                "scripts/orchestrator.py", "scripts/mcp_server.py", "scripts/ghidra/ExportarCEW.java", "formats/registry.json", "docs/DECISOES.md",
                "docs/formatos/MODELO.md", "docs/especificacoes/README.md"]:
        assert (RAIZ / rel).is_file(), rel
    assert "GEMINI_API_KEY" in (RAIZ / ".env.example").read_text() and "GHIDRA_INSTALL_DIR" in (RAIZ / ".env.example").read_text()
    gi = (RAIZ / ".gitignore").read_text()
    assert all(x in gi for x in (".env", "cache/", "logs/", "build/"))
