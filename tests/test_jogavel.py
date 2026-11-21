"""v2.3: escopo combinado, criterios de 'jogavel', esqueletos alcancaveis e o exemplo de plataforma 2D."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from cew import conversao, escopo, jogavel, marcos, motor, plano, reconstrucao
from cew.cli import main
from cew.inventario import inventariar
from cew.projeto import Projeto

RAIZ = Path(__file__).resolve().parents[1]
EXEMPLO = RAIZ / "exemplos" / "plataforma-2d"


@pytest.fixture
def demo(tmp_path, amostras):
    alvo = tmp_path / "alvo"
    alvo.mkdir()
    shutil.copy(amostras / "generico/fase.tmj", alvo)
    shutil.copy(amostras / "web/pronto.png", alvo / "tree.png")
    for f in (EXEMPLO / "alvo").iterdir():
        shutil.copy(f, alvo)
    p = Projeto.abrir("demo")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    plano.montar(p)
    conversao.executar(p)
    motor.recomendar(p)
    motor.escolher(p, "phaser")
    reconstrucao.gerar(p, "phaser")
    return p


def test_template_traz_nucleo_adaptadores_e_sessao(demo):
    app = demo.pasta / "app"
    for rel in ("src/nucleo/laco.js", "src/nucleo/comportamentos.js", "src/adaptadores/entrada.js", "src/adaptadores/salvamento.js",
                "tests/sessao.spec.js", "ARQUITETURA.md"):
        assert (app / rel).is_file(), rel
    assert "{{" not in (app / "ARQUITETURA.md").read_text()
    assert "testMatch" in (app / "playwright.config.js").read_text()


def test_escopo_analisa_e_define(demo):
    doc = escopo.analisar(demo)
    assert doc["numeros"]["cenas"] == 1 and doc["numeros"]["elementos_de_cena"] == 6 and doc["tamanho_estimado"] == "pequeno"
    assert doc["proposta"]["marcos"] == ["abre", "entrada", "colisao", "laco_central"] and doc["decisao"] is None
    with pytest.raises(ValueError):
        escopo.definir(demo, ["abre", "nao_existe"], "x")
    escopo.definir(demo, ["abre", "entrada", "laco_central"], "primeira fase")
    m = {x["id"]: x["obrigatorio"] for x in marcos.ler(demo)["marcos"]}
    assert m["abre"] and m["entrada"] and m["laco_central"] and not m["colisao"]
    assert any("escopo combinado" in h["evento"] for h in demo.estado()["historico"])


def test_jogavel_avalia_e_so_a_pessoa_confirma(demo):
    doc = jogavel.avaliar(demo)
    crit = {c["id"]: c["aprovado"] for c in doc["criterios"]}
    assert not doc["jogavel"] and not crit["escopo_definido"] and not crit["confirmacao_pessoa"]
    with pytest.raises(PermissionError):
        jogavel.confirmar(demo, "joguei", interativo=False)  # agente nao confirma pela pessoa
    with pytest.raises(ValueError):
        jogavel.confirmar(demo, "joguei", interativo=True)  # criterios ainda reprovados
    assert main(["jogavel", "confirmar", "--projeto", "demo"]) == 1


def test_esqueleto_alcancavel_reprova(demo):
    app = demo.pasta / "app"
    (app / "src" / "logica").mkdir(parents=True)
    (app / "src" / "logica" / "fisica.js").write_text("export function passo() { throw new Error('CEW: passo ainda nao traduzida'); }\n")
    assert jogavel.esqueletos_alcancaveis(demo) == []  # existe, mas o jogo nao importa
    main_js = app / "src" / "main.js"
    main_js.write_text("import { passo } from './logica/fisica.js';\n" + main_js.read_text())
    assert jogavel.esqueletos_alcancaveis(demo) == ["app/src/logica/fisica.js"]
    from cew import verificacao

    v = verificacao.executar(demo, web=False)
    item = next(i for i in v["itens"] if i["id"] == "traducao:esqueletos_alcancaveis")
    assert item["obrigatorio"] and not item["aprovado"]
    fid = next(i for i in v["itens"] if i["categoria"] == "fidelidade")
    assert fid["metricas"] == {"com_evidencia": 7, "total": 7}


@pytest.mark.skipif(not shutil.which("node"), reason="node ausente")
def test_exemplo_plataforma_nucleo_sem_motor(demo):
    """As regras do exemplo rodam em Node com a cena e as constantes que o CEW publicou."""
    app = demo.pasta / "app"
    shutil.copytree(EXEMPLO / "app", app, dirs_exist_ok=True)
    cena = next((demo.caminho("web") / "dados" / "cenas").glob("floresta-*.json"))
    cfg = next((demo.caminho("web") / "dados").glob("configuracoes-*.json"))
    r = subprocess.run(["node", "tests/nucleo_node.mjs", str(cena), str(cfg)], cwd=app, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "nucleo ok" in r.stdout, r.stderr
    escopo.definir(demo, ["abre", "entrada", "colisao", "laco_central", "progressao"], "fase floresta completa")
    assert jogavel.esqueletos_alcancaveis(demo) == []
    assert not jogavel.avaliar(demo)["jogavel"]  # sem cew check e sem a confirmacao da pessoa
