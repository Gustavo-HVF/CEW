"""Descompilacao (Craft Anything simulado com as saidas reais dos tools) e traducao para o motor."""

from __future__ import annotations

import json
import shutil
import struct
from pathlib import Path

import pytest

from cew import codigo, craft
from cew.cli import main
from cew.inventario import inventariar
from cew.projeto import Projeto

PSEUDO = {
    "0x1000": ("_init", "int64_t _init() { return 0; }"),
    "0x10f0": ("fopen@plt", "int64_t fopen@plt() { return fopen(); }"),
    "0x1100": ("_start", "void _start() { __libc_start_main(main); }"),
    "0x11e9": ("main", 'int64_t main() {\n  rax = fopen@plt("dados/nivel.qzx", "rb");\n  rax = ler_cabecalho(rsp);\n  atualizar_jogador(rax);\n  SDL_PollEvent(&ev);\n  return rax;\n}'),
    "0x1300": ("ler_cabecalho", 'int64_t ler_cabecalho(char *b) {\n  if (memcmp@plt(b, "QZX1", 4) != 0) return -2;\n  return *(uint16_t *)(b + 8) * *(uint16_t *)(b + 10);\n}'),
    "0x1400": ("atualizar_jogador", "void atualizar_jogador(int64_t v) {\n  velocity_y += gravity * dt;\n  if (collide(x, y)) velocity_y = 0;\n}"),
    "0x1500": ("desenhar_sprite", "void desenhar_sprite() { SDL_RenderCopy(r, t, 0, 0); }"),
    "0x1600": ("nunca_chamada", "int64_t nunca_chamada() { return 7; }"),
}


def _elf() -> bytes:
    return b"\x7fELF" + b"\x02\x01\x01" + b"\x00" * 57 + b"BIN" * 20


class CraftFalso:
    """Imita craft-anything-cli com os formatos de resultado lidos no codigo-fonte dele."""

    def __init__(self):
        self.chamadas = []

    def __call__(self, args, projeto_cany=None, deep=True, tempo_s=600, cli=None):
        self.chamadas.append(args)
        tool = args[0]
        if tool == "native-source-folder-write":
            pasta = Path(args[args.index("--folder") + 1])
            pasta.mkdir(parents=True, exist_ok=True)
            funcs = {}
            for end, (nome, corpo) in PSEUDO.items():
                arq = f"{int(end, 16):016x}_{nome.replace('@', '_')}.c"
                (pasta / arq).write_text(f"// {nome} at {end}, from jogo.elf. Approximate pseudo-C from the built-in decompiler.\n{corpo}\n")
                funcs[end] = {"file": arq, "name": nome, "lines": corpo.count("\n") + 2, "structured": True}
            (pasta / "craft-pseudocode-export.json").write_text(json.dumps({"version": 1, "target_name": "jogo.elf", "engine": "clean-room lifter", "functions": funcs}))
            return {"id": "ev_teste", "result": {"finished": True, "functions_done": len(funcs), "functions_total": len(funcs), "state_file": "craft-pseudocode-export.json"}}
        if tool == "managed-ilspy-decompile":
            if "--operation" in args:
                return {"result": {"output": "Class Jogo.Jogador\nClass Jogo.Fisica\nStruct Jogo.Vetor", "total_lines": 3}}
            t = args[args.index("--type-name") + 1]
            return {"result": {"output": f"namespace Jogo {{ public class {t.split('.')[-1]} {{ public void Update() {{ }} }} }}", "total_lines": 1}}
        if tool == "java-vineflower-decompile":
            if "--class" in args:
                c = args[args.index("--class") + 1]
                return {"result": {"file": c + ".java", "total_lines": 1, "source": f"class {c.split('/')[-1]} {{ void tick() {{}} }}"}}
            return {"result": {"files": 2, "sources": [{"file": "jogo/Principal.java", "lines": 1}, {"file": "jogo/Mapa.java", "lines": 1}]}}
        if tool == "js-sources-restore":
            saida = Path(args[args.index("--output-directory") + 1])
            (saida / "modulos").mkdir(parents=True)
            (saida / "modulos" / "jogador.js").write_text("export function update(dt) { return dt * 2; }\n")
            (saida / "leia.txt").write_text("nao e codigo")
            return {"result": {"files": 2}}
        raise AssertionError(f"tool inesperado {tool}")


@pytest.fixture
def ca(monkeypatch):
    falso = CraftFalso()
    monkeypatch.setattr(craft, "localizar_cli", lambda: "/falso/craft-anything-cli")
    monkeypatch.setattr(craft, "rodar", falso)
    monkeypatch.setattr(craft, "versao", lambda cli=None: "0.6.1")
    return falso


@pytest.fixture
def projeto(tmp_path):
    alvo = tmp_path / "jogo"
    alvo.mkdir()
    (alvo / "jogo.elf").write_bytes(_elf())
    (alvo / "scripts").mkdir()
    (alvo / "scripts" / "ia.lua").write_text("function pensar(inimigo) return inimigo.vida > 0 end\n")
    p = Projeto.abrir("codigo")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    return p


def test_descompila_nativo_e_copia_fontes(projeto, ca):
    idx = codigo.descompilar(projeto)
    progs = {g["tipo_codigo"]: g for g in idx["programas"]}
    nat = progs["nativo"]
    assert nat["estado"] == "completo" and nat["ferramenta"]["operacao"] == "native_source_folder_write" and nat["ferramenta"]["motor"] == "clean-room lifter"
    assert len(nat["unidades"]) == len(PSEUDO) and all((projeto.pasta / u["arquivo"]).is_file() for u in nat["unidades"])
    assert progs["fonte"]["linguagem_origem"] == "lua" and progs["fonte"]["unidades"][0]["nome"] == "ia"
    n = len(ca.chamadas)
    codigo.descompilar(projeto)
    assert len(ca.chamadas) == n  # idempotente: mesmo binario nao e descompilado de novo


def test_plano_filtra_runtime_e_ordena_pela_entrada(projeto, ca):
    codigo.descompilar(projeto)
    pl = codigo.planejar(projeto, "phaser")
    assert pl["linguagem_destino"] == "javascript" and pl["pasta_destino"] == "app/src/logica"
    u = {x["nome"]: x for x in pl["unidades"] if x["programa"].startswith("jogo")}
    assert all(u[n]["estado"] == "descartada" for n in ("_init", "fopen@plt", "_start"))
    assert u["main"]["distancia_entrada"] == 0 and u["main"]["prioridade"] == "alta"
    assert u["ler_cabecalho"]["distancia_entrada"] == 1 and u["ler_cabecalho"]["prioridade"] == "alta"
    assert u["atualizar_jogador"]["papel"] == "fisica" and "main" in u["atualizar_jogador"]["chamada_por"]
    assert u["desenhar_sprite"]["papel"] == "renderizacao" and u["nunca_chamada"]["distancia_entrada"] is None
    assert u["nunca_chamada"]["prioridade"] == "baixa"
    assert any(e.startswith("SDL_PollEvent -> this.input.keyboard") for e in u["main"]["equivalencias"])  # especifico do Phaser
    assert any(e.startswith("fopen -> ") for e in u["main"]["equivalencias"])
    assert u["main"]["destino"].endswith("/main.js") and u["ler_cabecalho"]["nome_destino"] == "ler_cabecalho"


def test_motor_define_a_linguagem(projeto, ca):
    codigo.descompilar(projeto)
    pl = codigo.planejar(projeto, "godot")
    assert pl["linguagem_destino"] == "gdscript" and all(u["destino"].endswith(".gd") for u in pl["unidades"])
    assert codigo.planejar(projeto, "unity_webgl")["linguagem_destino"] == "csharp"
    assert codigo.planejar(projeto, "construct3")["linguagem_destino"] == "eventos"


def test_pacote_traducao_e_testes_de_equivalencia(projeto, ca):
    codigo.descompilar(projeto)
    codigo.planejar(projeto, "phaser")
    r = codigo.pacote(projeto, "ler_cabecalho")
    texto = (projeto.pasta / r["pacote"]).read_text()
    assert "QZX1" in texto and "memcmp" in texto and "## Chamada por" in texto
    destino = projeto.pasta / r["destino"]
    assert "ainda nao traduzida" in destino.read_text()  # esqueleto
    pl = codigo.ler_plano(projeto)
    uid = next(x["id"] for x in pl["unidades"] if x["nome"] == "ler_cabecalho")
    (projeto.pasta / "codigo" / "testes").mkdir(parents=True)
    casos = {"schema_version": "1.0", "gerado_por": "cew", "unidade": uid, "funcao": "ler_cabecalho", "casos": [
        {"nome": "magic errado", "entrada": [{"$bytes": "414243440000000004000400"}], "saida": -2, "origem": "pseudo_c"},
        {"nome": "4x8", "entrada": [{"$bytes": "515a583100000000040008000"[:-1]}], "saida": 32, "origem": "pseudo_c"}]}
    (projeto.pasta / "codigo" / "testes" / f"{uid}.json").write_text(json.dumps(casos))
    res = codigo.testar(projeto, "ler_cabecalho")
    assert not res[0]["aprovado"]  # esqueleto ainda lanca erro
    destino.write_text("export function ler_cabecalho(b) {\n  if (b[0] !== 0x51 || b[1] !== 0x5a || b[2] !== 0x58 || b[3] !== 0x31) return -2;\n"
                       "  const v = new DataView(b.buffer, b.byteOffset, b.byteLength);\n  return v.getUint16(8, true) * v.getUint16(10, true);\n}\n")
    res = codigo.testar(projeto, "ler_cabecalho")
    assert res[0]["aprovado"] and res[0]["aprovados"] == 2
    u = next(x for x in codigo.ler_plano(projeto)["unidades"] if x["id"] == uid)
    assert u["estado"] == "testada" and u["testes"]["aprovado"]
    # replanejar preserva o andamento; editar a traducao depois do teste derruba para "traduzida"
    codigo.planejar(projeto, "phaser")
    assert next(x for x in codigo.ler_plano(projeto)["unidades"] if x["id"] == uid)["estado"] == "testada"
    destino.write_text(destino.read_text() + "// ajuste\n")
    codigo.planejar(projeto, "phaser")
    u = next(x for x in codigo.ler_plano(projeto)["unidades"] if x["id"] == uid)
    assert u["estado"] == "traduzida" and "rode" in u["motivo"]
    from cew import verificacao

    v = verificacao.executar(projeto, web=False)
    item = next(i for i in v["itens"] if i["id"] == "traducao:ler_cabecalho")
    assert item["aprovado"] and item["obrigatorio"]
    assert any(i["id"] == "traducao:cobertura" for i in v["itens"])


def test_registrar_e_descartar(projeto, ca):
    codigo.descompilar(projeto)
    codigo.planejar(projeto, "phaser")
    with pytest.raises(ValueError):
        codigo.registrar(projeto, "main", "traduzida")  # arquivo ainda nao existe
    u = codigo.registrar(projeto, "desenhar_sprite", "descartada", "desenho refeito com sprites do Phaser")
    assert u["estado"] == "descartada"


def test_dotnet_java_javascript(tmp_path, ca):
    alvo = tmp_path / "jogo"
    alvo.mkdir()
    pe = bytearray(b"MZ" + b"\x00" * 58 + struct.pack("<I", 64) + b"PE\x00\x00" + b"\x00" * 100 + b"BSJB" + b"\x00" * 64)
    (alvo / "Jogo.exe").write_bytes(bytes(pe))
    import zipfile

    with zipfile.ZipFile(alvo / "jogo.jar", "w") as z:
        z.writestr("jogo/Principal.class", b"\xca\xfe\xba\xbe\x00\x00\x00\x34")
    (alvo / "bundle.js").write_text("!function(){var a=1}();")
    p = Projeto.abrir("gerenciado")
    p.definir_alvo(alvo)
    inventariar(p, alvo)
    idx = codigo.descompilar(p)
    t = {g["tipo_codigo"]: g for g in idx["programas"]}
    assert t["dotnet"]["linguagem_origem"] == "csharp" and sorted(u["nome"] for u in t["dotnet"]["unidades"]) == ["Jogo.Fisica", "Jogo.Jogador", "Jogo.Vetor"]
    assert sorted(u["nome"] for u in t["java"]["unidades"]) == ["Mapa", "Principal"]
    assert [u["nome"] for u in t["javascript"]["unidades"]] == ["jogador"]  # so arquivos de codigo
    pl = codigo.planejar(p, "threejs")
    assert {u["linguagem_origem"] for u in pl["unidades"]} == {"csharp", "java", "javascript"}
    assert all(u["estado"] == "pendente" for u in pl["unidades"])


def test_fallback_ghidra_sem_craft(projeto, monkeypatch):
    monkeypatch.setattr(craft, "localizar_cli", lambda: None)
    item = next(i for i in projeto.ler("inventario")["itens"] if i["caminho"] == "jogo.elf")
    analise = {"schema_version": "1.0", "gerado_por": "cew-ghidra", "programa": {"nome": "jogo.elf", "sha256": item["sha256"]},
               "ferramenta": {"nome": "Ghidra", "versao": "12.1.4"}, "strings": [], "chamadas": [],
               "funcoes": [{"nome": "main", "endereco": "0x001011e9", "pseudo_c": "int main(void) { return carregar(); }"},
                           {"nome": "carregar", "endereco": "0x00101200", "pseudo_c": "int carregar(void) { return 1; }"}]}
    (projeto.caminho("analise") / "jogo.json").write_text(json.dumps(analise))
    idx = codigo.descompilar(projeto)
    nat = next(g for g in idx["programas"] if g["tipo_codigo"] == "nativo")
    assert nat["ferramenta"]["motor"] == "ghidra" and [u["nome"] for u in nat["unidades"]] == ["main", "carregar"]
    pl = codigo.planejar(projeto, "pixijs")
    assert next(u for u in pl["unidades"] if u["nome"] == "carregar")["distancia_entrada"] == 1


def test_sem_craft_e_sem_ghidra_fica_indisponivel(projeto, monkeypatch):
    monkeypatch.setattr(craft, "localizar_cli", lambda: None)
    nat = next(g for g in codigo.descompilar(projeto)["programas"] if g["tipo_codigo"] == "nativo")
    assert nat["estado"] == "indisponivel" and "cew setup" in nat["mensagem"]


def test_rascunho_gemini(projeto, ca, gemini_falso):
    from tests.conftest import resposta_gemini

    gemini_falso["respostas"].append(resposta_gemini({"schema_version": "1.0", "gerado_por": "cew-gemini-worker", "codigo": "export function main() { return 0; }",
                                                      "explicacao": "le o nivel e atualiza o jogador", "dependencias": ["ler_cabecalho"], "duvidas": [], "confianca": 0.4}))
    codigo.descompilar(projeto)
    codigo.planejar(projeto, "phaser")
    r = codigo.pacote(projeto, "main", gemini=True)
    assert (projeto.pasta / r["rascunho_gemini"]).read_text().startswith("export function main")
    corpo = gemini_falso["chamadas"][0]["corpo"]
    assert "traducao" in corpo["contents"][0]["parts"][0]["text"]
    destino = (projeto.pasta / r["destino"]).read_text()
    assert "ainda nao traduzida" in destino  # o rascunho nunca e aplicado sozinho


def test_cli_codigo(projeto, ca, capsys):
    assert main(["codigo", "descompilar", "--projeto", "codigo"]) == 0
    assert main(["codigo", "planejar", "--projeto", "codigo", "--motor", "phaser"]) == 0
    assert main(["codigo", "status", "--projeto", "codigo"]) == 0
    out = capsys.readouterr().out
    assert "javascript" in out and "main" in out and "_start" not in out.split("javascript", 1)[1]
    assert main(["codigo", "pacote", "main", "--projeto", "codigo"]) == 0
    assert main(["codigo", "testar", "--projeto", "codigo"]) == 0  # sem casos ainda: nada falha
