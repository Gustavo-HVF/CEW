"""Mapeamento de elementos de cena: coordenadas, categorias, assets, regras, ajustes e publicacao."""

from __future__ import annotations

import json
import math
import shutil

import pytest

from cew import cenas, conversao, conversores, plano
from cew.cli import main
from cew.inventario import inventariar
from cew.projeto import Projeto
from converters.comum.eixos import converter_ponto


def _bruta(amostras, tmp_path, nome):
    conv = {"bsp": ("cookbook/idtech/bsp_entidades_to_cena.py", "idtech/mapa.bsp"), "tmj": ("cookbook/generico/tiled_json_to_cena.py", "generico/fase.tmj")}[nome]
    r = conversores.rodar(conv[0], amostras / conv[1], tmp_path / nome)
    assert r["ok"], r["erro"]
    return json.loads((tmp_path / nome / "cena_bruta.json").read_text())


def _rot(q, v):
    x, y, z, w = q
    # v' = q v q*  (formula vetorial)
    tx, ty, tz = 2 * (y * v[2] - z * v[1]), 2 * (z * v[0] - x * v[2]), 2 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty), v[1] + w * ty + (z * tx - x * tz), v[2] + w * tz + (x * ty - y * tx))


@pytest.mark.parametrize("origem", ["z_up_rh", "y_up_lh", "z_up_lh", "y_up_rh"])
def test_quaternion_converte_junto_com_os_pontos(origem):
    """Girar e depois converter == converter e depois girar com o quaternion convertido."""
    q = [0.2, -0.4, 0.5, 0.0]
    n = math.sqrt(sum(c * c for c in q[:3]) + 0.7 ** 2)
    q = [q[0] / n, q[1] / n, q[2] / n, 0.7 / n]
    v = (1.0, 2.0, -3.0)
    a = converter_ponto(_rot(q, v), origem)
    b = _rot(cenas.converter_quaternion(q, origem), converter_ponto(v, origem))
    assert all(abs(x - y) < 1e-5 for x, y in zip(a, b))


def test_bsp_quake_para_metros_y_para_cima(amostras, tmp_path):
    b = _bruta(amostras, tmp_path, "bsp")
    assert b["nome"] == "Fase de Teste do CEW" and len(b["entidades"]) == 7  # worldspawn fica fora
    porta = next(e for e in b["entidades"] if e["tipo_original"] == "func_door")
    assert porta["posicao_estimada"] and porta["propriedades"]["direcao"] == "cima"
    c = cenas.normalizar(b, [], cenas.ler_regras(tmp_path), cenas.ler_ajustes(tmp_path), "e1m1")
    por_tipo = {e["tipo_original"]: e for e in c["entidades"]}
    ogro = por_tipo["monster_ogre"]
    # Quake (256, 128, 24) polegadas, Z para cima -> glTF (x, z, -y) * 0,0254
    assert ogro["posicao"] == pytest.approx([6.5024, 0.6096, -3.2512])
    assert ogro["guinada_graus"] == 180 and ogro["rotacao"] == pytest.approx([0, 1, 0, 0], abs=1e-6)
    assert {e["tipo_original"]: e["categoria"] for e in c["entidades"]} == {
        "info_player_start": "spawn", "monster_ogre": "inimigo", "monster_tetra": "inimigo", "light": "luz",
        "item_health": "item", "func_door": "porta", "trigger_once": "gatilho"}
    assert c["sistema_coordenadas"] == {"eixo_para_cima": "Y", "mao": "direita", "metros_por_unidade": 1.0}


def test_tiled_2d_ancora_rotacao_e_grupos(amostras, tmp_path):
    b = _bruta(amostras, tmp_path, "tmj")
    c = cenas.normalizar(b, [], cenas.ler_regras(tmp_path), cenas.ler_ajustes(tmp_path))
    e = {x["tipo_original"]: x for x in c["entidades"]}
    assert e["tree"]["categoria"] == "vegetacao" and e["tree"]["ancora"] == "base_esquerda"  # objeto-tile (gid)
    assert e["pillar"]["categoria"] == "estrutura" and e["enemy_slime"]["categoria"] == "inimigo" and e["spawn"]["categoria"] == "spawn"
    assert e["arbusto"]["categoria"] == "vegetacao"  # sem classe: categoria pelo nome
    assert e["flower"]["posicao"] == [144.0, 108.0]  # offset do grupo (4, -2) aplicado
    assert e["flower"]["guinada_graus"] == 45  # horario no Tiled, horario na saida
    assert e["enemy_slime"]["propriedades"] == {"vida": 3, "patrulha_px": 48.0}
    assert c["tiles"][0]["largura"] == 10 and sum(1 for g in c["tiles"][0]["dados"] if g) == 10
    assert c["limites"]["largura_px"] == 160


def test_regras_assets_e_ajustes(amostras, tmp_path):
    b = _bruta(amostras, tmp_path, "bsp")
    assets = [{"id": "a_" + "1" * 16, "tipo": "modelo", "caminho_web": "assets/modelos/ogre.glb", "origem": {"item_inventario": "i_" + "0" * 16, "caminho": "progs/ogre.mdl", "formato": None, "conversor": None}},
              {"id": "a_" + "2" * 16, "tipo": "modelo", "caminho_web": "assets/modelos/vida.glb", "origem": {"item_inventario": "i_" + "0" * 16, "caminho": "maps/b_medkit.bsp", "formato": None, "conversor": None}}]
    regras = {"schema_version": "1.0", "gerado_por": "cew", "regras": [
        {"quando": {"tipo_original": "light"}, "remover": True},
        {"quando": {"tipo_original": "item_health"}, "categoria": "item", "asset": {"origem_glob": "*medkit*"}, "escala": 2, "deslocamento_m": [0, 0.5, 0]}]}
    c = cenas.normalizar(b, assets, regras, cenas.ler_ajustes(tmp_path), "e1m1")
    t = {e["tipo_original"]: e for e in c["entidades"]}
    assert "light" not in t and c["estatisticas"]["removidas_por_regra"] == 1
    assert t["monster_ogre"]["asset_id"] == "a_" + "1" * 16 and t["monster_ogre"]["asset_por"] == "nome"  # monster_ogre -> ogre.mdl
    assert t["item_health"]["asset_id"] == "a_" + "2" * 16 and t["item_health"]["asset_por"] == "regra"
    assert t["item_health"]["escala"] == [2.0, 2.0, 2.0] and t["item_health"]["posicao"][1] == pytest.approx(0.4064 + 0.5)
    ogro = t["monster_ogre"]["id"]
    ajustes = {"schema_version": "1.0", "gerado_por": "cew", "ajustes": [
        {"op": "mover", "cena": "e1m1", "entidade": ogro, "para": [1, 0, -2]},
        {"op": "girar", "cena": "*", "entidade": ogro, "graus": 90},
        {"op": "deslocar", "cena": "e1m1", "filtro": {"categoria": "inimigo"}, "delta": [0, 1, 0]},
        {"op": "remover", "cena": "e1m1", "filtro": {"categoria": "gatilho"}},
        {"op": "adicionar", "cena": "e1m1", "nova": {"id": "bruta_0", "tipo_original": "pilastra", "categoria": "estrutura", "posicao": [2, 0, 2]}},
        {"op": "grade", "cena": "e1m1", "filtro": {"categoria": "estrutura"}, "passo": 0.5},
        {"op": "definir", "cena": "outra", "entidade": ogro, "valores": {"categoria": "npc"}}]}
    c2 = cenas.normalizar(b, assets, regras, ajustes, "e1m1")
    t2 = {e["tipo_original"]: e for e in c2["entidades"]}
    assert t2["monster_ogre"]["posicao"] == [1.0, 1.0, -2.0] and t2["monster_ogre"]["guinada_graus"] == 270 and t2["monster_ogre"]["ajustado"]
    assert t2["monster_ogre"]["categoria"] == "inimigo"  # ajuste de outra cena nao vale aqui
    assert "trigger_once" not in t2 and t2["pilastra"]["id"].startswith("e_") and t2["pilastra"]["posicao"] == [2.0, 0.0, 2.0]
    assert c2["estatisticas"]["adicionadas"] == 1


def test_ids_estaveis_e_ajustes_sobrevivem_a_reconversao(amostras, tmp_path):
    """Tiled tem id por objeto: mover o objeto no mapa original nao perde o ajuste feito no CEW."""
    b = _bruta(amostras, tmp_path, "tmj")
    c = cenas.normalizar(b, [], cenas.ler_regras(tmp_path), cenas.ler_ajustes(tmp_path), "fase")
    pilar = next(e for e in c["entidades"] if e["tipo_original"] == "pillar")
    ajustes = {"schema_version": "1.0", "gerado_por": "cew", "ajustes": [{"op": "definir", "cena": "fase", "entidade": pilar["id"], "valores": {"nome": "pilastra norte"}}]}
    mapa = json.loads((amostras / "generico/fase.tmj").read_text())
    mapa["layers"][1]["objects"][1]["x"] = 70  # o pilar mudou de lugar na nova versao do jogo
    (tmp_path / "v2.tmj").write_text(json.dumps(mapa))
    conversores.rodar("cookbook/generico/tiled_json_to_cena.py", tmp_path / "v2.tmj", tmp_path / "v2")
    b2 = json.loads((tmp_path / "v2" / "cena_bruta.json").read_text())
    c2 = cenas.normalizar(b2, [], cenas.ler_regras(tmp_path), ajustes, "fase")
    p2 = next(e for e in c2["entidades"] if e["tipo_original"] == "pillar")
    assert p2["id"] == pilar["id"] and p2["nome"] == "pilastra norte" and p2["posicao"][0] == 70.0
    assert [e["id"] for e in c["entidades"]] == [e["id"] for e in c2["entidades"]]


def test_pipeline_publica_cenas_no_manifesto(amostras, tmp_path):
    alvo = tmp_path / "jogo"
    (alvo / "maps").mkdir(parents=True)
    (alvo / "progs").mkdir()
    shutil.copy(amostras / "idtech/mapa.bsp", alvo / "maps/e1m1.bsp")
    shutil.copy(amostras / "idtech/tetra.md2", alvo / "progs/tetra.md2")
    shutil.copy(amostras / "generico/fase.tmj", alvo / "fase.tmj")
    p = Projeto.abrir("mapas")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    plano.montar(p)
    assert conversao.executar(p)["erros"] == 0
    man = p.ler("manifesto")
    mapas = {a["metadados"]["extras"]["cena"]: a for a in man["assets"] if a["tipo"] == "mapa"}
    assert set(mapas) == {"e1m1", "floresta"} and all(a["caminho_web"].startswith("dados/cenas/") for a in mapas.values())
    publicadas = {c["id_cena"]: c for _, c in cenas.cenas_publicadas(p)}
    tetra = next(e for e in publicadas["e1m1"]["entidades"] if e["tipo_original"] == "monster_tetra")
    modelo = next(a for a in man["assets"] if a["tipo"] == "modelo")
    assert tetra["asset_id"] == modelo["id"]  # o inimigo carrega com o modelo convertido
    # ajuste pela CLI e republicado; rodar a conversao de novo mantem o ajuste
    assert main(["cena", "ajustar", "e1m1", "--projeto", "mapas", "--op", "mover", "--entidade", tetra["id"], "--para", "3,0,3"]) == 0
    assert main(["cena", "regra", "--projeto", "mapas", "--tipo-original", "light", "--remover"]) == 0
    conversao.executar(p)
    c = {c["id_cena"]: c for _, c in cenas.cenas_publicadas(p)}["e1m1"]
    assert next(e for e in c["entidades"] if e["id"] == tetra["id"])["posicao"] == [3.0, 0.0, 3.0]
    assert all(e["tipo_original"] != "light" for e in c["entidades"])
    from cew import verificacao

    v = verificacao.executar(p, web=False)
    itens = [i for i in v["itens"] if i["categoria"] == "cena"]
    assert len(itens) == 2 and all(i["aprovado"] for i in itens), itens
    assert main(["cena", "listar", "--projeto", "mapas"]) == 0


def test_cena_quebrada_reprova_na_verificacao(amostras, tmp_path):
    test_pipeline_publica_cenas_no_manifesto(amostras, tmp_path)
    p = Projeto.abrir("mapas")
    a, c = next((a, c) for a, c in cenas.cenas_publicadas(p) if c["id_cena"] == "e1m1")
    c["entidades"][0]["asset_id"] = "a_" + "f" * 16
    (p.caminho("web") / a["caminho_web"]).write_text(json.dumps(c))
    from cew import verificacao

    v = verificacao.executar(p, web=False)
    item = next(i for i in v["itens"] if i["id"] == "cena:e1m1")
    assert not item["aprovado"] and "inexistentes" in item["detalhes"]
