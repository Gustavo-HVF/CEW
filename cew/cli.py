"""CLI `cew`: menu interativo, fluxo retomavel em etapas, --dry-run e comandos avulsos.

    cew                      menu (so abre depois do teste real do Gemini)
    cew setup                ambiente + Craft Anything + Gemini -> reports/ambiente.json
    cew run                  fluxo completo, retomavel (estado em projects/<nome>/estado.json)
    cew status | check       estado do projeto | etapa Verificar
    cew etapa <nome>         roda uma etapa
    cew gemini testar|modelos, cew validar, cew identificar, cew conversores, cew converter,
    cew sandbox, cew skills instalar, cew projetos
Codigos de saida: 0 ok, 1 falha, 2 uso, 3 Gemini indisponivel, 4 etapa bloqueada.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import __version__
from .caminhos import raiz_repositorio
from .config import carregar_env, salvar_no_env
from .esquemas import ErroEsquema, ler_json, nomes_esquemas
from .gemini import ClienteGemini, mensagem_amigavel
from .logs import Log
from .projeto import CRITERIOS, ETAPAS, Projeto, listar_projetos

SAIDA_GEMINI = 3
SAIDA_BLOQUEADA = 4


class Bloqueio(Exception):
    """Criterio de saida de uma etapa nao foi cumprido."""


def interativo() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty() and not os.environ.get("CEW_NAO_INTERATIVO")


def perguntar(texto: str, padrao: str = "") -> str:
    try:
        r = input(f"{texto}{f' [{padrao}]' if padrao else ''}: ").strip()
    except EOFError:
        return padrao
    return r or padrao


# ------------------------------------------------------------------------------ Gemini gate
def portao_gemini(dry_run: bool = False, cliente: ClienteGemini | None = None) -> bool:
    """Item 1.1/1.2: sem chave o fluxo para e pede a chave; o teste real precisa passar."""
    carregar_env()
    cliente = cliente or ClienteGemini()
    if not cliente.tem_chave:
        print("GEMINI_API_KEY nao encontrada (ambiente ou .env).")
        if not interativo():
            print(mensagem_amigavel("sem_chave"))
            return False
        chave = getpass.getpass("Cole a chave do Gemini (nao aparece na tela): ").strip()
        if not chave:
            return False
        os.environ["GEMINI_API_KEY"] = chave
        cliente.chave = chave
        if perguntar("Salvar no .env deste repositorio? (s/n)", "s").lower().startswith("s"):
            arq = salvar_no_env("GEMINI_API_KEY", chave)
            print(f"Chave salva em {arq} (fora do git).")
    if dry_run:
        print("[dry-run] faria o teste real do Gemini (modelo %s)" % cliente.config["modelo"])
        return True
    print(f"Testando o Gemini ({cliente.config['modelo']})...", flush=True)
    r = cliente.testar()
    if r["teste_ok"]:
        print(f"Gemini ok ({r['latencia_ms']} ms).")
        return True
    print(f"Teste do Gemini falhou: {r['erro']}\n{mensagem_amigavel(r['tipo_erro'])}")
    return False


# ------------------------------------------------------------------------------ etapas
def etapa_ambiente(p: Projeto, a: argparse.Namespace) -> str:
    from . import ambiente

    rel = ambiente.verificar(testar_gemini=False, doctor=not a.dry_run)
    rel["gemini"].update(teste_ok=True, chave_presente=True)  # o portao acabou de testar de verdade
    rel["obrigatorios_faltando"] = [f for f in rel["obrigatorios_faltando"] if f != "gemini"]
    rel["pronto"] = not rel["obrigatorios_faltando"]
    if not a.dry_run:
        ambiente.gravar(rel)
    print(ambiente.resumo_texto(rel))
    if rel["obrigatorios_faltando"] and not a.ignorar_ambiente:
        raise Bloqueio("faltando: " + ", ".join(rel["obrigatorios_faltando"]) + " (rode 'cew setup'; --ignorar-ambiente so para desenvolvimento)")
    return "ambiente conferido" + (" (faltas ignoradas: " + ", ".join(rel["obrigatorios_faltando"]) + ")" if rel["obrigatorios_faltando"] else "")


def etapa_alvo(p: Projeto, a: argparse.Namespace) -> str:
    alvo = a.alvo or (p.estado().get("alvo") or {}).get("caminho")
    if not alvo and interativo():
        alvo = perguntar("Caminho do arquivo ou pasta alvo (executavel, ROM, pacote, pasta do jogo)")
    if not alvo:
        raise Bloqueio("nenhum alvo: use --alvo <caminho>")
    c = Path(alvo).expanduser()
    if not c.exists() or not os.access(c, os.R_OK):
        raise Bloqueio(f"alvo inacessivel: {c}")
    if not a.dry_run:
        p.definir_alvo(c)
    return f"alvo: {c.resolve()}"


def etapa_inventario(p: Projeto, a: argparse.Namespace) -> str:
    from .inventario import inventariar

    alvo = (p.estado().get("alvo") or {}).get("caminho") or a.alvo
    doc = inventariar(p, Path(alvo), dry_run=a.dry_run)
    r = doc["resumo"]
    print(f"{r['total']} arquivos: {r['identificados']} identificados, {r['desconhecidos']} desconhecidos, {r['compactados']} compactados")
    return f"{r['total']} itens"


def etapa_engenharia(p: Projeto, a: argparse.Namespace) -> str:
    from . import engenharia, plano

    if not a.dry_run:
        plano.montar(p)
    rel = engenharia.executar(p, dry_run=a.dry_run, usar_ghidra=not a.sem_ghidra, usar_craft=not a.sem_craft)
    for av in rel["avisos"]:
        print("aviso:", av)
    if a.dry_run:
        print(json.dumps(rel, ensure_ascii=False, indent=2))
        return "dry-run"
    ok, faltas = engenharia.criterio_saida(p)
    if not ok:
        raise Bloqueio("especificacoes sem evidencia: " + "; ".join(faltas[:10]) + " (complete analise/hipoteses.json com a skill 03)")
    return f"{rel.get('hipoteses', 0)} hipoteses, {len(rel['ghidra'])} programas no Ghidra"


def etapa_conversao(p: Projeto, a: argparse.Namespace) -> str:
    from . import conversao, plano

    if not a.dry_run:
        plano.montar(p)
    if not a.sem_delegacao:
        for linha in plano.delegar_desconhecidos(p, dry_run=a.dry_run):
            print("gemini:", json.dumps(linha, ensure_ascii=False))
    rel = conversao.executar(p, dry_run=a.dry_run)
    print(f"convertidos {rel['convertidos']}, erros {rel['erros']}, assets {rel.get('assets', '-')}")
    if a.dry_run:
        return "dry-run"
    erros = [i for i in p.ler("plano")["itens"] if i["estado"] == "erro"]
    if erros:
        raise Bloqueio(f"{len(erros)} itens em erro no plano (ex.: {erros[0].get('caminho')}: {erros[0].get('erro')})")
    if not a.sem_testes and shutil.which(sys.executable):
        t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", str(raiz_repositorio() / "tests" / "test_conversores.py")], capture_output=True, text=True, cwd=raiz_repositorio())
        if t.returncode != 0:
            raise Bloqueio("testes dos conversores falharam: " + t.stdout[-600:])
    return f"{rel['convertidos']} convertidos"


def etapa_motor(p: Projeto, a: argparse.Namespace) -> str:
    from . import motor

    pref = json.loads(a.perfil) if a.perfil else None
    doc = motor.recomendar(p, pref, dry_run=a.dry_run)
    print(f"Perfil: {doc['perfil']['dimensao']}, fisica {doc['perfil']['fisica']}, {doc['perfil']['quantidade_assets']} assets")
    for m in doc["motores"]:
        print(f"  {m['nota']:>4}  {m['id']:<12} {m['nome']}" + ("" if m["modelo_gerado_pelo_cew"] else "  (sem modelo automatico)"))
    escolha = a.motor or (doc.get("escolha_usuario") or {}).get("motor")
    if not escolha and interativo():
        escolha = perguntar("Motor escolhido", doc["recomendado"])
    if not escolha:
        raise Bloqueio(f"escolha o motor com --motor (recomendado: {doc['recomendado']})")
    if not a.dry_run:
        motor.escolher(p, escolha)
    return f"motor: {escolha}"


def etapa_reconstrucao(p: Projeto, a: argparse.Namespace) -> str:
    from . import reconstrucao

    m = p.estado()["motor_escolhido"] or a.motor
    if m not in reconstrucao.COM_MODELO:
        raise Bloqueio(f"o CEW nao gera projeto para {m}: siga skills/05 e crie app/ manualmente, depois rode 'cew check'")
    arqs = reconstrucao.gerar(p, m, dry_run=a.dry_run)
    print(f"{len(arqs)} arquivos em app/ ({m}); assets lidos de ../web")
    return f"app/ gerado ({m})"


def etapa_verificacao(p: Projeto, a: argparse.Namespace) -> str:
    from . import verificacao

    doc = verificacao.executar(p, web=not a.sem_web, instalar=a.instalar_dependencias, gemini=a.gemini, chromium=a.chromium, dry_run=a.dry_run)
    reprov = [i for i in doc["itens"] if i["obrigatorio"] and not i["aprovado"]]
    print(f"{len(doc['itens'])} verificacoes; {len(reprov)} obrigatorias reprovadas")
    for i in reprov[:15]:
        print(f"  x {i['id']}: {i['detalhes'][:160]}")
    if not doc["aprovado"]:
        raise Bloqueio("relatorio_verificacao.json reprovado")
    return "verificacao aprovada"


def etapa_pronto(p: Projeto, a: argparse.Namespace) -> str:
    print(f"Pronto. Jogo web em {p.pasta / 'app'} (npm run dev / npm run preview).")
    return "pronto"


FUNCOES = {"ambiente": etapa_ambiente, "alvo": etapa_alvo, "inventario": etapa_inventario, "engenharia": etapa_engenharia, "conversao": etapa_conversao,
           "motor": etapa_motor, "reconstrucao": etapa_reconstrucao, "verificacao": etapa_verificacao, "pronto": etapa_pronto}


def rodar_etapa(p: Projeto, nome: str, a: argparse.Namespace) -> bool:
    print(f"\n== {nome} ({CRITERIOS[nome]})")
    p.marcar(nome, "em_andamento", dry_run=a.dry_run)
    try:
        msg = FUNCOES[nome](p, a)
        p.marcar(nome, "concluida", msg, dry_run=a.dry_run)
        return True
    except Bloqueio as e:
        p.marcar(nome, "bloqueada", str(e), dry_run=a.dry_run)
        print(f"BLOQUEADA: {e}")
        return False
    except (ErroEsquema, FileNotFoundError, ValueError, RuntimeError) as e:
        p.marcar(nome, "erro", str(e)[:500], dry_run=a.dry_run)
        Log("cew").erro(str(e), etapa=nome)
        print(f"ERRO: {e}")
        return False


def cmd_run(a: argparse.Namespace) -> int:
    if not portao_gemini(a.dry_run):
        return SAIDA_GEMINI
    p = Projeto.abrir(a.projeto)
    st = p.estado()
    ate = ETAPAS.index(a.ate) if a.ate else len(ETAPAS) - 1
    inicio = 0 if a.desde_inicio else ETAPAS.index(st["etapa_atual"])
    if a.alvo and inicio > ETAPAS.index("alvo"):
        inicio = ETAPAS.index("alvo")  # alvo novo: refaz a partir dele
    print(f"Projeto {p.nome} em {p.pasta} - retomando em '{ETAPAS[inicio]}'")
    for nome in ETAPAS[inicio : ate + 1]:
        if not rodar_etapa(p, nome, a):
            return SAIDA_BLOQUEADA
        if a.dry_run and nome == "alvo" and not (p.estado().get("alvo")):
            print("[dry-run] as proximas etapas precisam do alvo gravado; pare aqui ou rode sem --dry-run")
            break
    return 0


def cmd_etapa(a: argparse.Namespace) -> int:
    p = Projeto.abrir(a.projeto)
    if a.nome == "ambiente" and not portao_gemini(a.dry_run):
        return SAIDA_GEMINI
    return 0 if rodar_etapa(p, a.nome, a) else SAIDA_BLOQUEADA


def cmd_status(a: argparse.Namespace) -> int:
    if not a.projeto:
        for x in listar_projetos():
            print(json.dumps(x, ensure_ascii=False))
        return 0
    st = Projeto.abrir(a.projeto, criar=False).estado()
    print(f"Projeto {st['projeto']}: etapa atual {st['etapa_atual']} (fase {st.get('fase_craft_anything')}), alvo {(st.get('alvo') or {}).get('caminho')}, motor {st['motor_escolhido']}")
    for nome in ETAPAS:
        e = st["etapas"].get(nome, {})
        print(f"  {nome:<13} {e.get('estado', 'pendente'):<13} {e.get('mensagem', '')[:100]}")
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    p = Projeto.abrir(a.projeto, criar=False)
    return 0 if rodar_etapa(p, "verificacao", a) else 1


def cmd_setup(a: argparse.Namespace) -> int:
    from . import ambiente, setup_craft

    ssh = True if a.ssh else (False if a.https else None)
    try:
        rel = setup_craft.executar(ssh=ssh, com_app=a.com_app, sem_craft=a.sem_craft, dry_run=a.dry_run)
    except RuntimeError as e:
        print(f"ERRO: {e}")
        return 1
    print(ambiente.resumo_texto(rel))
    if not a.dry_run:
        print("Relatorio: reports/ambiente.json")
    if not rel["gemini"]["teste_ok"] and not a.dry_run:
        print(mensagem_amigavel(rel["gemini"].get("tipo_erro")))
    return 0 if rel["pronto"] or a.dry_run else 1


def cmd_gemini(a: argparse.Namespace) -> int:
    c = ClienteGemini()
    if a.acao == "testar":
        r = c.testar()
        print(json.dumps(r, ensure_ascii=False, indent=2))
        if not r["teste_ok"]:
            print(mensagem_amigavel(r["tipo_erro"]))
        return 0 if r["teste_ok"] else SAIDA_GEMINI
    for m in c.modelos():
        if "generateContent" in m["metodos"]:
            print(m["nome"])
    return 0


def cmd_validar(a: argparse.Namespace) -> int:
    nome = a.esquema
    arq = Path(a.arquivo)
    if not nome:
        mapa = {"inventario.json": "inventario", "plano_conversao.json": "plano_conversao", "asset_manifest.json": "asset_manifest", "estado.json": "estado",
                "recomendacao_motor.json": "recomendacao_motor", "relatorio_verificacao.json": "relatorio_verificacao", "registry.json": "registry",
                "ambiente.json": "ambiente", "cew.json": "cew_projeto", "hipoteses.json": "hipoteses_formato", "contexto.json": "contexto_formatos"}
        nome = mapa.get(arq.name)
    if not nome:
        print(f"informe --esquema (opcoes: {', '.join(nomes_esquemas())})")
        return 2
    try:
        ler_json(arq, nome)
        print(f"ok: {arq} valida contra {nome}")
        return 0
    except ErroEsquema as e:
        print("\n".join(e.erros))
        return 1


def cmd_identificar(a: argparse.Namespace) -> int:
    from .registro import identificar_arquivo

    for c in a.arquivos:
        print(json.dumps({"arquivo": c, **identificar_arquivo(Path(c)).para_json()}, ensure_ascii=False))
    return 0


def cmd_conversores(a: argparse.Namespace) -> int:
    from .conversores import listar

    for i in listar():
        print(f"{i['arquivo']:<44} {', '.join(i['formatos_entrada'])} -> {i['destino']}")
    return 0


def cmd_converter(a: argparse.Namespace) -> int:
    from .conversores import rodar

    saida = Path(a.saida) if a.saida else Path(a.entrada).with_name(Path(a.entrada).name + ".cew")
    r = rodar(a.conversor, Path(a.entrada), saida, json.loads(a.opcoes), a.dry_run)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r["ok"] else 1


def cmd_sandbox(a: argparse.Namespace) -> int:
    from .sandbox import executar_rascunho

    arq = Path(a.rascunho)
    if arq.name.endswith(".resposta.json"):
        resp = json.loads(arq.read_text(encoding="utf-8"))
        if not resp.get("rascunho_conversor"):
            print("a resposta nao tem rascunho_conversor")
            return 1
        codigo = resp["rascunho_conversor"]["codigo"]
    else:
        codigo = arq.read_text(encoding="utf-8")
    pasta = Path(a.pasta) if a.pasta else arq.parent / ("sandbox_" + arq.name.split(".")[0][:16])
    r = executar_rascunho(codigo, pasta, Path(a.entrada) if a.entrada else None, tempo_s=a.tempo)
    print(json.dumps(r.para_json(), ensure_ascii=False, indent=2))
    return 0 if r.codigo_saida == 0 else 1


def cmd_skills(a: argparse.Namespace) -> int:
    origem = raiz_repositorio() / "skills"
    destino = Path(a.destino) if a.destino else raiz_repositorio() / ".claude" / "skills"
    for d in sorted(origem.iterdir()):
        if (d / "SKILL.md").is_file():
            alvo = destino / d.name
            print(("[dry-run] " if a.dry_run else "") + f"{d / 'SKILL.md'} -> {alvo / 'SKILL.md'}")
            if not a.dry_run:
                alvo.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(d / "SKILL.md", alvo / "SKILL.md")
    return 0


def menu(a: argparse.Namespace) -> int:
    if not portao_gemini(a.dry_run):
        print("O menu do CEW so abre com o Gemini funcionando.")
        return SAIDA_GEMINI
    projeto = a.projeto or perguntar("Projeto", (listar_projetos() or [{"projeto": "meu-jogo"}])[0]["projeto"])
    while True:
        print(f"\nCEW {__version__} - projeto '{projeto}'\n 1) continuar o fluxo\n 2) status\n 3) escolher/trocar alvo\n 4) rodar uma etapa\n 5) verificar (check)\n"
              " 6) testar Gemini\n 7) conversores\n 8) trocar de projeto\n 0) sair")
        op = perguntar("Opcao", "1")
        base = argparse.Namespace(**{**vars(a), "projeto": projeto})
        if op == "0":
            return 0
        if op == "1":
            cmd_run(base)
        elif op == "2":
            cmd_status(base)
        elif op == "3":
            base.alvo = perguntar("Caminho do alvo")
            rodar_etapa(Projeto.abrir(projeto), "alvo", base)
        elif op == "4":
            nome = perguntar("Etapa (" + "/".join(ETAPAS) + ")", Projeto.abrir(projeto).estado()["etapa_atual"])
            if nome in ETAPAS:
                rodar_etapa(Projeto.abrir(projeto), nome, base)
        elif op == "5":
            rodar_etapa(Projeto.abrir(projeto), "verificacao", base)
        elif op == "6":
            cmd_gemini(argparse.Namespace(acao="testar"))
        elif op == "7":
            cmd_conversores(base)
        elif op == "8":
            projeto = perguntar("Projeto", projeto)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="cew", description="CEW - Convert Everything for the Web")
    p.add_argument("--version", action="version", version=f"cew {__version__}")
    p.add_argument("--dry-run", action="store_true", help="mostra o que faria, sem gravar nem chamar servicos")
    p.add_argument("--projeto", default=None, help="nome do projeto em projects/")
    comuns = argparse.ArgumentParser(add_help=False)
    comuns.add_argument("--dry-run", action="store_true", default=argparse.SUPPRESS, help="mostra o que faria, sem gravar")
    comuns.add_argument("--projeto", default=argparse.SUPPRESS, help="nome do projeto em projects/")
    sub = p.add_subparsers(dest="comando")
    _add = sub.add_parser

    def add_parser(nome: str, **kw):  # toda subcomando aceita --projeto e --dry-run depois do nome
        return _add(nome, parents=[comuns], **kw)

    sub.add_parser = add_parser  # type: ignore[method-assign]

    def opcoes_fluxo(s: argparse.ArgumentParser) -> None:
        s.add_argument("--alvo", help="arquivo ou pasta alvo")
        s.add_argument("--motor", help="motor escolhido (phaser, pixijs, threejs, babylonjs, ...)")
        s.add_argument("--perfil", help="preferencias do perfil em JSON, ex.: '{\"fisica\": \"complexa\"}'")
        s.add_argument("--sem-ghidra", action="store_true")
        s.add_argument("--sem-craft", action="store_true", help="nao chama o craft-anything-cli")
        s.add_argument("--sem-delegacao", action="store_true", help="nao envia formatos desconhecidos ao Gemini")
        s.add_argument("--sem-testes", action="store_true", help="nao roda os testes dos conversores no criterio da conversao")
        s.add_argument("--sem-web", action="store_true", help="verificacao sem build/navegador")
        s.add_argument("--instalar-dependencias", action="store_true", help="permite npm install em app/ durante a verificacao")
        s.add_argument("--gemini", action="store_true", help="segunda opiniao visual do Gemini na verificacao")
        s.add_argument("--chromium", default=os.environ.get("CEW_CHROMIUM"), help="Chromium para o Playwright")
        s.add_argument("--ignorar-ambiente", action="store_true", help="segue mesmo com ferramentas obrigatorias faltando (desenvolvimento)")

    s = sub.add_parser("setup", help="ambiente, Craft Anything e teste do Gemini")
    s.add_argument("--ssh", action="store_true")
    s.add_argument("--https", action="store_true")
    s.add_argument("--com-app", action="store_true", help="compila tambem o app desktop do Craft Anything")
    s.add_argument("--sem-craft", action="store_true", help="nao clona/compila o Craft Anything")
    s.set_defaults(func=cmd_setup)
    s = sub.add_parser("run", help="fluxo completo, retomavel")
    opcoes_fluxo(s)
    s.add_argument("--ate", choices=ETAPAS)
    s.add_argument("--desde-inicio", action="store_true")
    s.set_defaults(func=cmd_run)
    s = sub.add_parser("etapa", help="roda uma etapa")
    s.add_argument("nome", choices=ETAPAS)
    opcoes_fluxo(s)
    s.set_defaults(func=cmd_etapa)
    s = sub.add_parser("status")
    s.set_defaults(func=cmd_status)
    s = sub.add_parser("check", help="etapa Verificar")
    opcoes_fluxo(s)
    s.set_defaults(func=cmd_check)
    s = sub.add_parser("gemini")
    s.add_argument("acao", choices=["testar", "modelos"])
    s.set_defaults(func=cmd_gemini)
    s = sub.add_parser("validar", help="valida um JSON contra o esquema")
    s.add_argument("arquivo")
    s.add_argument("--esquema")
    s.set_defaults(func=cmd_validar)
    s = sub.add_parser("identificar", help="identifica arquivos pelo registro de formatos")
    s.add_argument("arquivos", nargs="+")
    s.set_defaults(func=cmd_identificar)
    s = sub.add_parser("conversores")
    s.set_defaults(func=cmd_conversores)
    s = sub.add_parser("converter", help="roda um conversor")
    s.add_argument("conversor", help="ex.: converters/nintendo/tpl_to_png.py")
    s.add_argument("entrada")
    s.add_argument("-o", "--saida")
    s.add_argument("--opcoes", default="{}")
    s.set_defaults(func=cmd_converter)
    s = sub.add_parser("sandbox", help="roda um rascunho do Gemini isolado")
    s.add_argument("rascunho", help="arquivo .py ou <sha>.resposta.json")
    s.add_argument("--entrada")
    s.add_argument("--pasta")
    s.add_argument("--tempo", type=int, default=60)
    s.set_defaults(func=cmd_sandbox)
    s = sub.add_parser("skills", help="copia skills/ para .claude/skills (Claude Code)")
    s.add_argument("acao", choices=["instalar"])
    s.add_argument("--destino")
    s.set_defaults(func=cmd_skills)
    s = sub.add_parser("projetos")
    s.set_defaults(func=lambda a: cmd_status(argparse.Namespace(projeto=None)))
    return p


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")  # acentos no console do Windows
        except (ValueError, OSError):
            pass
    p = parser()
    a = p.parse_args(argv)
    carregar_env()
    if not a.comando:
        defaults = p.parse_args(["run"] + (["--dry-run"] if a.dry_run else []))
        defaults.projeto = a.projeto
        return menu(defaults)
    if a.comando in ("run", "etapa", "check") and not a.projeto:
        if a.comando == "run" and interativo():
            a.projeto = perguntar("Nome do projeto", "meu-jogo")
        else:
            p.error("informe --projeto <nome>")
    return int(a.func(a) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
