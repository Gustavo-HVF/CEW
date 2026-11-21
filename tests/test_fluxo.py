"""Fluxo completo nas amostras: inventario -> plano -> conversao -> manifesto -> motor -> app -> verificacao."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from cew import conversao, engenharia, motor, plano, reconstrucao, verificacao
from cew.cli import main
from cew.inventario import Limites, inventariar
from cew.projeto import Projeto


@pytest.fixture
def alvo(tmp_path, amostras):
    d = tmp_path / "alvo com espaço e acentuação"
    shutil.copytree(amostras, d)
    (d / "referencias.json").unlink()
    return d


def test_inventario_recursivo_e_ids_estaveis(alvo, tmp_path):
    p = Projeto.abrir("Meu Jogo")
    a = inventariar(p, alvo)
    caminhos = {i["caminho"]: i for i in a["itens"]}
    assert "nintendo/arquivo.szs!/descompactado.arc!/texturas/fundo.tpl" in caminhos
    szs = caminhos["nintendo/arquivo.szs"]
    assert szs["estado"] == "compactado" and szs["compressao"]["algoritmo"] == "yaz0" and szs["compressao"]["descompactado_em"]
    assert caminhos["desconhecido/misterio.xyz"]["estado"] == "desconhecido"
    b = inventariar(p, alvo)
    assert [i["id"] for i in a["itens"]] == [i["id"] for i in b["itens"]]
    # mesmo conteudo em outra pasta (outro computador) -> mesmos ids
    outro = tmp_path / "outro"
    shutil.copytree(alvo, outro)
    c = inventariar(Projeto.abrir("outro"), outro)
    assert [i["id"] for i in a["itens"]] == [i["id"] for i in c["itens"]]


def test_limite_de_profundidade(alvo):
    p = Projeto.abrir("raso")
    doc = inventariar(p, alvo, limites=Limites(profundidade_maxima=0))
    assert all(i["profundidade"] == 0 for i in doc["itens"])


def test_fluxo_ate_verificacao_sem_web(alvo, gemini_falso):
    p = Projeto.abrir("fluxo")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    pl = plano.montar(p)
    assert pl["resumo"]["aguardando_gemini"] >= 1
    rel = engenharia.executar(p, usar_ghidra=False, usar_craft=False)
    ok, faltas = engenharia.criterio_saida(p)
    assert ok, faltas
    rel = plano.delegar_desconhecidos(p)
    assert any(x["acao"] == "resposta recebida" for x in rel)
    tarefas = list(p.caminho("tarefas_gemini").glob("*.tarefa.json"))
    assert tarefas
    r = conversao.executar(p)
    assert r["erros"] == 0 and r["assets"] > 10
    man = p.ler("manifesto")
    caminhos = [a["caminho_web"] for a in man["assets"]]
    assert all(c == c.lower() and " " not in c for c in caminhos)
    audio = {a["caminho_web"].split("/")[-1].rsplit("-", 1)[0]: a for a in man["assets"] if a["tipo"] == "audio"}
    assert audio["som"]["metadados"]["loop"] == {"inicio_amostra": 56, "fim_amostra": 140}
    # rodar de novo: nada muda (idempotencia) e os ids/caminhos web sao os mesmos
    assert conversao.executar(p)["convertidos"] == 0
    assert [a["id"] for a in p.ler("manifesto")["assets"]] == [a["id"] for a in man["assets"]]
    # Gemini entra como camada 5 do inventario na proxima rodada
    inv2 = inventariar(p, alvo)
    mist = next(i for i in inv2["itens"] if i["caminho"] == "desconhecido/misterio.xyz")
    assert mist["formato"]["camada"] == "gemini" and mist["formato"]["confianca"] <= 0.6
    doc = motor.recomendar(p)
    assert doc["perfil"]["dimensao"] in ("3d", "misto") and 0 <= doc["motores"][0]["nota"] <= 10
    motor.escolher(p, "threejs")
    arqs = reconstrucao.gerar(p, "threejs")
    assert "app/src/main.js" in arqs and (p.pasta / "app" / "package.json").is_file()
    v = verificacao.executar(p, web=False)
    reprov = [i for i in v["itens"] if i["obrigatorio"] and not i["aprovado"]]
    glb_sem_validador = all(i["categoria"] == "modelo" for i in reprov)
    assert v["aprovado"] or glb_sem_validador, reprov


def test_cli_sem_chave_para_e_pede_a_chave(capsys):
    assert main(["run", "--projeto", "x", "--alvo", "."]) == 3
    assert "GEMINI_API_KEY" in capsys.readouterr().out


def test_cli_run_retomavel(alvo, gemini_falso, capsys):
    args = ["run", "--projeto", "cli", "--alvo", str(alvo), "--ignorar-ambiente", "--sem-ghidra", "--sem-craft", "--sem-testes", "--motor", "phaser", "--ate", "motor"]
    assert main(args) == 0
    st = Projeto.abrir("cli").estado()
    assert st["etapa_atual"] == "reconstrucao" and st["motor_escolhido"] == "phaser"
    assert all(st["etapas"][e]["estado"] == "concluida" for e in ("alvo", "inventario", "engenharia", "conversao", "motor"))
    assert main(["status", "--projeto", "cli"]) == 0
    assert main(["run", "--projeto", "cli", "--ate", "reconstrucao", "--ignorar-ambiente"]) == 0  # retoma de onde parou
    assert (Projeto.abrir("cli").pasta / "app" / "src" / "main.js").is_file()


def test_cli_dry_run_nao_grava(alvo, gemini_falso, tmp_path):
    assert main(["run", "--projeto", "seco", "--alvo", str(alvo), "--dry-run", "--ignorar-ambiente", "--ate", "alvo"]) == 0
    p = Projeto.abrir("seco")
    assert p.estado()["alvo"] is None and not p.existe("inventario")
    assert gemini_falso["chamadas"] == []  # dry-run nao chama o Gemini


def test_craft_json_valido_para_o_craft_anything(alvo):
    from cew.projeto import validar_craft_json

    p = Projeto.abrir("ca")
    p.definir_alvo(alvo)
    doc = json.loads((p.pasta / "craft.json").read_text())
    validar_craft_json(doc)
    assert doc["target"] == {"kind": "local", "path": str(alvo.resolve())} and doc["version"] == 5
    for d in ("capture", "app", "checks", "investigation.cany", "inbox"):
        assert (p.pasta / d).is_dir()
