"""Ciclo do agente: formato ausente de todos os registros -> registrar -> escrever -> testar -> usar.

Simula o que o agente da pessoa faz (skill 04) com um formato ficticio ".qzx" (imagem) e ".qzs" (som,
convertido por um comando externo). Nada aqui depende de conversor pronto do repositorio.
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
from pathlib import Path

import pytest

from cew import conversao, conversores, kit, marcos, plano, reconstrucao
from cew.cli import main
from cew.inventario import inventariar
from cew.projeto import Projeto

CONVERSOR_QZX = '''"""demo.qzx.imagem -> png (conversor escrito pelo agente no teste)."""
from __future__ import annotations

{cabecalho}
from converters.comum.binario import LeitorBinario, exigir
from converters.comum.cli import Escritor, executar
from converters.comum.imagem import Imagem, png_bytes

INFO = {{"arquivo": "{ref}", "descricao": "QZX para PNG", "formatos_entrada": ["demo.qzx.imagem"], "destino": "png", "versao": "1.0", "papel": "conversor"}}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "big")
    exigir(r.bytes_em(0, 4) == b"QZX1", "assinatura QZX1 ausente")
    w, h = r.u16_em(4), r.u16_em(6)
    exigir(0 < w <= 4096 and 0 < h <= 4096, "dimensoes invalidas")
    px = r.bytes_em(8, w * h * 4, "pixels")
    img = Imagem(w, h, bytearray(px))
    esc.gravar("imagem.png", png_bytes(img), "textura", "png", img.metadados("srgb"))
    return {{"largura": w, "altura": h}}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
'''

FERRAMENTA_QZS = '''import struct, sys, wave
dados = open(sys.argv[1], "rb").read()
if dados[:4] != b"QZS1":
    sys.exit("assinatura QZS1 ausente")
taxa = struct.unpack_from(">I", dados, 4)[0]
with wave.open(sys.argv[2], "wb") as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(taxa); w.writeframes(dados[8:])
'''


def qzx(w: int, h: int, cor: tuple) -> bytes:
    return b"QZX1" + struct.pack(">HH", w, h) + bytes(cor) * (w * h)


@pytest.fixture
def alvo(tmp_path, amostras):
    d = tmp_path / "jogo ficticio"
    (d / "gfx").mkdir(parents=True)
    for i, (w, h) in enumerate([(4, 4), (8, 2), (16, 16), (2, 2), (8, 8), (3, 5)]):
        (d / "gfx" / f"sprite{i}.qzx").write_bytes(qzx(w, h, (10 * i, 200, 30, 255)))
    (d / "sfx").mkdir()
    (d / "sfx" / "pulo.qzs").write_bytes(b"QZS1" + struct.pack(">I", 8000) + struct.pack("<8h", *range(0, 8000, 1000)))
    shutil.copy(amostras / "web/pronto.png", d / "icone.png")
    return d


def test_ciclo_completo_formato_ficticio(alvo, tmp_path):
    p = Projeto.abrir("ficticio")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    pl = plano.montar(p)
    grupo = next(g for g in pl["formatos"] if g["formato"] == "desconhecido:.qzx")
    assert grupo["cobertura"] == "falta_conversor" and grupo["prioridade"] == "alta"
    ok, faltas = plano.criterio_saida(p)
    assert not ok and any(".qzx" in f for f in faltas)  # alta prioridade sem decisao bloqueia

    # 1) registrar o formato descoberto (assinatura + extensao) no registro DO PROJETO
    kit.registrar_formato(p, "demo.qzx.imagem", empresa_ou_motor="Estudio Ficticio", extensoes=["qzx"], assinatura_hex="515a5831",
                          ordem_de_bytes="big", tipo="textura", destino="png", confianca="engenharia_reversa")
    kit.registrar_log(p, "demo.qzx.imagem", "pesquisar", "ok", detalhes="carregador no Ghidra le u16 BE em 4 e 6", evidencia=["funcao carregar_qzx 0x401000"])
    # 2) escrever o conversor a partir do esqueleto do kit
    arq = kit.novo_conversor(p, "demo.qzx.imagem", "python", "png")
    ref = "projeto:" + arq.relative_to(p.pasta).as_posix()
    arq.write_text(CONVERSOR_QZX.format(cabecalho=kit.CABECALHO_IMPORT, ref=ref), encoding="utf-8")
    (arq.parent / "amostras" / "minima.qzx").write_bytes(qzx(1, 1, (1, 2, 3, 255)))  # amostra sintetica
    # 3) harness: amostras reais do inventario + a sintetica
    t = kit.testar(p, ref)
    assert t["aprovado"], t["verificacoes"]
    assert {a["origem"] for a in t["amostras"]} == {"real", "sintetica"}
    assert (arq.with_name(arq.stem + ".teste.json")).is_file()
    # 4) ligar o conversor ao formato e seguir o fluxo
    kit.registrar_formato(p, "demo.qzx.imagem", conversor=ref)

    # som via COMANDO externo (embrulha uma ferramenta; aqui um script Python)
    ferramenta = p.pasta / "conversores" / "ferramentas" / "qzs2wav.py"
    ferramenta.parent.mkdir(parents=True)
    ferramenta.write_text(FERRAMENTA_QZS, encoding="utf-8")
    kit.registrar_formato(p, "demo.qzs.som", extensoes=["qzs"], assinatura_hex="515a5331", tipo="audio", destino="wav")
    cmd = kit.novo_conversor(p, "demo.qzs.som", "comando", "wav")
    doc = json.loads(cmd.read_text())
    doc["ferramenta"] = {"nome": "qzs2wav (script do projeto)", "verificar": [sys.executable, "--version"]}
    doc["comando"] = ["{python}", "{projeto}/conversores/ferramentas/qzs2wav.py", "{entrada}", "{saida_arquivo:som.wav}"]
    cmd.write_text(json.dumps(doc, indent=2))
    ref_cmd = "projeto:" + cmd.relative_to(p.pasta).as_posix()
    t2 = kit.testar(p, ref_cmd)
    assert t2["aprovado"], t2["verificacoes"]
    kit.registrar_formato(p, "demo.qzs.som", conversor=ref_cmd)

    inventariar(p, alvo)
    pl = plano.montar(p)
    itens = {i["caminho"]: i for i in pl["itens"]}
    assert itens["gfx/sprite0.qzx"]["cobertura"] == "coberto" and itens["gfx/sprite0.qzx"]["fonte_conversor"] == "projeto"
    assert itens["sfx/pulo.qzs"]["conversor"] == ref_cmd
    ok, faltas = plano.criterio_saida(p)
    assert ok, faltas
    r = conversao.executar(p)
    assert r["erros"] == 0
    man = p.ler("manifesto")
    texturas = [a for a in man["assets"] if a["origem"]["formato"] == "demo.qzx.imagem"]
    assert len(texturas) == 6 and texturas[0]["metadados"]["largura_px"] > 0
    som = next(a for a in man["assets"] if a["origem"]["formato"] == "demo.qzs.som")
    assert som["metadados"]["taxa_amostragem_hz"] == 8000  # metadados lidos da saida do comando

    # idempotencia pelo hash do codigo: mudar o conversor refaz so os itens dele
    assert conversao.executar(p)["convertidos"] == 0
    arq.write_text(arq.read_text() + "\n# ajuste\n", encoding="utf-8")
    plano.montar(p)
    ok, faltas = plano.criterio_saida(p)
    assert not ok and any("desatualizado" in f for f in faltas)  # teste do harness precisa ser refeito
    kit.testar(p, ref)
    plano.montar(p)
    assert conversao.executar(p)["convertidos"] == 6

    log = [json.loads(l) for l in (p.pasta / "log_conversores.jsonl").read_text().splitlines()]
    assert {"pesquisar", "escrever", "testar", "registrar"} <= {l["passo"] for l in log}


def test_harness_reprova_e_bloqueia_no_limite(alvo, monkeypatch):
    p = Projeto.abrir("ruim")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    kit.registrar_formato(p, "demo.qzx.imagem", extensoes=["qzx"], assinatura_hex="515a5831", tipo="textura", destino="png")
    arq = kit.novo_conversor(p, "demo.qzx.imagem", "python", "png")
    ref = "projeto:" + arq.relative_to(p.pasta).as_posix()
    # bug tipico: le sem conferir limites -> IndexError em arquivo truncado
    arq.write_text(CONVERSOR_QZX.format(cabecalho=kit.CABECALHO_IMPORT, ref=ref).replace(
        'exigir(r.bytes_em(0, 4) == b"QZX1", "assinatura QZX1 ausente")', 'assert dados[3] == ord("1") and dados[0:4] == b"QZX1"'), encoding="utf-8")
    monkeypatch.setitem(conversores.config_cew()["harness"], "max_tentativas_por_formato", 2)
    t = kit.testar(p, ref)
    rob = next(v for v in t["verificacoes"] if v["id"] == "robustez")
    assert not t["aprovado"] and not rob["aprovado"] and "falha inesperada" in rob["detalhes"]
    kit.testar(p, ref)
    fmt = json.loads((p.pasta / "formatos.json").read_text())["formatos"][0]
    assert fmt["tentativas"] == 2 and fmt["decisao"]["acao"] == "bloqueado"
    pl = plano.montar(p)
    assert all(i["cobertura"] == "bloqueado" for i in pl["itens"] if i["formato_origem"] == "demo.qzx.imagem")


def test_laco_infinito_vira_tempo_limite(alvo, monkeypatch):
    p = Projeto.abrir("laco")
    arq = kit.novo_conversor(p, "demo.qzx.imagem", "python", "png")
    ref = "projeto:" + arq.relative_to(p.pasta).as_posix()
    arq.write_text(CONVERSOR_QZX.format(cabecalho=kit.CABECALHO_IMPORT, ref=ref).replace("    r = LeitorBinario(dados, \"big\")", "    while True:\n        pass"), encoding="utf-8")
    monkeypatch.setitem(conversores.config_cew()["harness"], "tempo_limite_s", 3)
    r = conversores.rodar(ref, alvo / "gfx" / "sprite0.qzx", p.pasta / "x", {}, False, p.pasta)
    assert not r["ok"] and "tempo limite" in r["erro"]  # o orquestrador segue vivo


def test_cadeia_de_fontes_configuravel(monkeypatch, amostras, tmp_path):
    from cew.registro import registro_do_projeto

    p = Projeto.abrir("fontes")
    reg = registro_do_projeto(p.pasta)
    assert reg.conversor("nintendo.gx.tpl")["fonte"] == "cookbook"
    assert reg.conversor("nintendo.gx.tpl", ["projeto", "generico"])["cobertura"] == "falta_conversor"  # sem cookbook: agente escreve
    copia = kit.copiar_do_cookbook(p, "cookbook/nintendo/tpl_to_png.py")
    ref = "projeto:" + copia.relative_to(p.pasta).as_posix()
    kit.registrar_formato(p, "nintendo.gx.tpl", conversor=ref)
    reg = registro_do_projeto(p.pasta)
    assert reg.conversor("nintendo.gx.tpl")["ref"] == ref  # projeto vence o cookbook
    r = conversores.rodar(ref, amostras / "nintendo/texturas.tpl", tmp_path / "o", {}, False, p.pasta)
    assert r["ok"] and len(r["saidas"]) == 8 and r["conversor"] == ref


def test_decisao_ignorar_libera_o_criterio(alvo):
    p = Projeto.abrir("decide")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    kit.registrar_formato(p, "demo.qzx.imagem", extensoes=["qzx"], assinatura_hex="515a5831", tipo="textura")
    kit.registrar_formato(p, "demo.qzs.som", extensoes=["qzs"], assinatura_hex="515a5331", tipo="audio")
    inventariar(p, alvo)
    plano.montar(p)
    assert not plano.criterio_saida(p)[0]
    kit.registrar_formato(p, "demo.qzx.imagem", decisao="substituir", motivo="sprites serao redesenhados pela pessoa")
    pl = plano.montar(p)
    assert plano.criterio_saida(p)[0]
    assert next(g for g in pl["formatos"] if g["formato"] == "demo.qzx.imagem")["decisao"] == "substituir"


def test_marcos_modelos_e_atualizacao(tmp_path):
    p = Projeto.abrir("marcos")
    doc = marcos.iniciar(p, "app")
    assert [m["id"] for m in doc["marcos"]][0] == "abre" and doc["modelo"] == "app"
    assert (p.pasta / "app/tests/marcos/abre.spec.js").read_text().count("test(") == 1
    assert "test.fixme" in (p.pasta / "app/tests/marcos/navegacao.spec.js").read_text()
    (p.pasta / "app/tests/marcos/abre.spec.js").write_text("// escrito pelo agente\n")
    marcos.iniciar(p, "app")  # nao sobrescreve
    assert (p.pasta / "app/tests/marcos/abre.spec.js").read_text() == "// escrito pelo agente\n"
    _, atingido = marcos.atualizar(p, {"tests/marcos/abre.spec.js": {"aprovado": True, "detalhes": "ok"},
                                       "tests/marcos/navegacao.spec.js": {"aprovado": False, "pendente": True, "detalhes": "fixme"},
                                       "tests/marcos/acao_principal.spec.js": {"aprovado": True, "detalhes": "ok"}})
    assert atingido == "abre"  # so conta a sequencia consecutiva


def test_cli_do_kit(alvo, capsys):
    p = Projeto.abrir("cli-kit")
    p.definir_alvo(alvo)
    assert main(["novo-conversor", "demo.qzx.imagem", "--projeto", "cli-kit"]) == 0
    assert "conversor-testar" in capsys.readouterr().out
    assert main(["formato-registrar", "demo.qzx.imagem", "--projeto", "cli-kit", "--extensao", "qzx", "--assinatura", "515a5831", "--tipo", "textura"]) == 0
    assert main(["log-conversor", "demo.qzx.imagem", "amostrar", "--projeto", "cli-kit", "--detalhes", "3 arquivos"]) == 0
    assert main(["conversores", "--projeto", "cli-kit"]) == 0
    assert "[projeto" in capsys.readouterr().out
    assert main(["marcos", "iniciar", "--projeto", "cli-kit", "--modelo", "jogo"]) == 0
    # esqueleto ainda nao implementado: harness reprova sem derrubar nada
    ref = "projeto:conversores/demo/qzx_imagem_to_png.py"
    assert main(["conversor-testar", ref, "--projeto", "cli-kit", "--entrada", str(alvo / "gfx" / "sprite0.qzx")]) == 1
