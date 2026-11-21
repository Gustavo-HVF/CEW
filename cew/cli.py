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
    from .plano import criterio_saida

    ok, faltas = criterio_saida(p)
    if not ok:
        raise Bloqueio("; ".join(faltas[:8]) + (" ..." if len(faltas) > 8 else ""))
    usados = {i["conversor"] for i in p.ler("plano")["itens"] if i.get("conversor") and i["estado"] == "concluido"}
    if not a.sem_testes and any(not u.startswith("projeto:") for u in usados):
        t = subprocess.run([sys.executable, "-m", "pytest", "-q", "-x", str(raiz_repositorio() / "tests" / "test_conversores.py")], capture_output=True, text=True, cwd=raiz_repositorio())
        if t.returncode != 0:
            raise Bloqueio("testes dos conversores do repositorio falharam: " + t.stdout[-600:])
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
    arqs = reconstrucao.gerar(p, m, dry_run=a.dry_run, modelo_marcos=a.modelo_marcos)
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


def _pasta(a: argparse.Namespace) -> Path | None:
    return Projeto.abrir(a.projeto, criar=False).pasta if getattr(a, "projeto", None) else None


def cmd_conversores(a: argparse.Namespace) -> int:
    from .conversores import config_cew, listar

    print("fontes ativas (config/cew.json): " + " -> ".join(config_cew()["fontes_conversores"]))
    for i in listar(_pasta(a)):
        extra = f"  ERRO: {i['erro']}" if i.get("erro") else ""
        print(f"[{i['fonte']:<8}] {i['arquivo']:<54} {', '.join(i['formatos_entrada'])} -> {i['destino']}{extra}")
    return 0


def cmd_novo_conversor(a: argparse.Namespace) -> int:
    from .kit import novo_conversor

    p = Projeto.abrir(a.projeto)
    arq = novo_conversor(p, a.formato, a.tipo, a.destino, a.nome)
    ref = "projeto:" + arq.relative_to(p.pasta).as_posix()
    print(f"criado: {arq}\nreferencia: {ref}\nproximo: implemente, ponha amostras sinteticas em {arq.parent / 'amostras'} e rode:\n"
          f"  cew conversor-testar {ref} --projeto {p.nome}\n  cew formato-registrar {a.formato} --projeto {p.nome} --conversor {ref}")
    return 0


def cmd_conversor_testar(a: argparse.Namespace) -> int:
    from .kit import testar

    p = Projeto.abrir(a.projeto, criar=False)
    doc = testar(p, a.conversor, [Path(e) for e in a.entrada] if a.entrada else None)
    for v in doc["verificacoes"]:
        print(f"  [{'ok' if v['aprovado'] else 'FALHOU'}] {v['id']:<14} {v['detalhes'][:150]}")
    for am in doc["amostras"]:
        print(f"    {'ok ' if am['ok'] else 'ERR'} {am['origem']:<9} {Path(am['caminho']).name}  {am.get('erro') or ''}"[:200])
    print("APROVADO" if doc["aprovado"] else "REPROVADO")
    return 0 if doc["aprovado"] else 1


def cmd_formato_registrar(a: argparse.Namespace) -> int:
    from .kit import registrar_formato

    p = Projeto.abrir(a.projeto, criar=False)
    f = registrar_formato(p, a.formato, empresa_ou_motor=a.empresa, extensoes=a.extensao, assinatura_hex=a.assinatura, assinatura_offset=a.offset,
                          ordem_de_bytes=a.ordem, tipo=a.tipo, destino=a.destino, conversor=a.conversor, decisao=a.decisao, motivo=a.motivo,
                          documentacao=a.documentacao, confianca=a.confianca)
    print(json.dumps(f, ensure_ascii=False, indent=2))
    return 0


def cmd_conversor_copiar(a: argparse.Namespace) -> int:
    from .kit import copiar_do_cookbook

    p = Projeto.abrir(a.projeto, criar=False)
    arq = copiar_do_cookbook(p, a.conversor)
    print(f"copiado para {arq}\nreferencia: projeto:{arq.relative_to(p.pasta).as_posix()}")
    return 0


def cmd_log_conversor(a: argparse.Namespace) -> int:
    from .kit import registrar_log

    p = Projeto.abrir(a.projeto, criar=False)
    print(json.dumps(registrar_log(p, a.formato, a.passo, a.resultado, a.conversor, a.detalhes or "", a.evidencia), ensure_ascii=False))
    return 0


def _vetor(texto: str | None) -> list[float] | None:
    return [float(x) for x in texto.replace(";", ",").split(",")] if texto else None


def cmd_cena(a: argparse.Namespace) -> int:
    from . import conversao
    from .cenas import cenas_publicadas, registrar_ajuste, registrar_regra

    p = Projeto.abrir(a.projeto, criar=False)
    if a.acao == "listar":
        for ent, c in cenas_publicadas(p):
            est = c.get("estatisticas", {})
            print(f"{c['id_cena']:<24} {c['dimensao']}  {est.get('entidades', 0):>5} elementos  sem asset {est.get('sem_asset', 0):>4}  {ent['caminho_web']}")
            print("    " + ", ".join(f"{k}: {v}" for k, v in est.get("por_categoria", {}).items()))
        return 0
    if a.acao == "mostrar":
        alvo = next((c for _, c in cenas_publicadas(p) if c["id_cena"] == a.cena), None)
        if alvo is None:
            print(f"cena {a.cena} nao publicada (rode a etapa conversao)")
            return 1
        for e in alvo["entidades"]:
            if a.categoria and e["categoria"] != a.categoria:
                continue
            pos = ", ".join(f"{c:g}" for c in e["posicao"])
            print(f"{e['id']}  {e['categoria']:<10} {e['tipo_original'][:28]:<28} ({pos})  rot {e.get('guinada_graus', 0):g}  asset {e.get('asset_id') or '-'}{'  [ajustado]' if e.get('ajustado') else ''}")
        return 0
    if a.acao == "regra":
        quando = {k: v for k, v in (("tipo_original", a.tipo_original), ("nome", a.nome), ("camada", a.camada)) if v}
        regra: dict = {"quando": quando}
        if a.categoria:
            regra["categoria"] = a.categoria
        if a.asset_glob:
            regra["asset"] = {"origem_glob": a.asset_glob}
        if a.fator:
            regra["escala"] = a.fator
        if a.delta:
            regra["deslocamento_m"] = (_vetor(a.delta) + [0, 0, 0])[:3]
        if a.remover:
            regra["remover"] = True
        print(json.dumps(registrar_regra(p.pasta, regra), ensure_ascii=False))
    else:  # ajustar
        aj: dict = {"op": a.op, "cena": a.cena or "*"}
        if a.entidade:
            aj["entidade"] = a.entidade
        filtro = {k: v for k, v in (("categoria", a.categoria), ("tipo_original", a.tipo_original), ("camada", a.camada)) if v}
        if filtro:
            aj["filtro"] = filtro
        for campo, valor in (("para", _vetor(a.para)), ("delta", _vetor(a.delta))):
            if valor:
                aj[campo] = valor
        for campo, valor in (("graus", a.graus), ("fator", a.fator), ("passo", a.passo)):
            if valor is not None:
                aj[campo] = valor
        if a.valores:
            aj["valores"] = json.loads(a.valores)
        if a.nova:
            aj["nova"] = json.loads(a.nova)
        if a.motivo:
            aj["motivo"] = a.motivo
        print(json.dumps(registrar_ajuste(p.pasta, aj), ensure_ascii=False))
    if p.existe("plano") and p.existe("inventario"):
        conversao.publicar(p, p.ler("plano"), p.ler("inventario"))  # reaplica regras e ajustes nas cenas publicadas
        print("cenas republicadas em web/dados/cenas/")
    return 0


def cmd_marcos(a: argparse.Namespace) -> int:
    from . import marcos

    p = Projeto.abrir(a.projeto, criar=False)
    if a.acao == "iniciar":
        doc = marcos.iniciar(p, a.modelo, a.sobrescrever)
    else:
        doc = marcos.ler(p)
        if doc is None:
            print("sem marcos.json: rode 'cew marcos iniciar'")
            return 1
    for m in doc["marcos"]:
        print(f"  {m['estado']:<9} {'*' if m['obrigatorio'] else ' '} {m['id']:<28} {m['titulo']}  ({m['teste']})")
    print("* = obrigatorio para o 'aprovado' geral")
    return 0


def cmd_converter(a: argparse.Namespace) -> int:
    from .conversores import rodar

    saida = Path(a.saida) if a.saida else Path(a.entrada).with_name(Path(a.entrada).name + ".cew")
    r = rodar(a.conversor, Path(a.entrada), saida, json.loads(a.opcoes), a.dry_run, projeto_pasta=_pasta(a))
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
        s.add_argument("--modelo-marcos", choices=["jogo", "app"], default="jogo", help="modelo de marcos criado na reconstrucao")

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
    s.add_argument("conversor", help="ex.: cookbook/nintendo/tpl_to_png.py")
    s.add_argument("entrada")
    s.add_argument("-o", "--saida")
    s.add_argument("--opcoes", default="{}")
    s.set_defaults(func=cmd_converter)
    s = sub.add_parser("novo-conversor", help="cria o esqueleto de um conversor no projeto (Python ou comando externo)")
    s.add_argument("formato", help="id do formato, ex.: microsoft.xna.xnb")
    s.add_argument("--tipo", choices=["python", "comando"], default="python")
    s.add_argument("--destino", default="png", help="png, glb, ogg, wav, json, pasta...")
    s.add_argument("--nome", help="nome do arquivo sem extensao")
    s.set_defaults(func=cmd_novo_conversor)
    s = sub.add_parser("conversor-testar", help="harness: executa, determinismo, robustez, dry-run, ajuda, tempo/memoria")
    s.add_argument("conversor", help="referencia: projeto:conversores/..., cookbook/... ou converters/...")
    s.add_argument("--entrada", action="append", help="amostra (repita); padrao: amostras do inventario + conversores/**/amostras/")
    s.set_defaults(func=cmd_conversor_testar)
    s = sub.add_parser("formato-registrar", help="registra formato, conversor ou decisao no registro do projeto")
    s.add_argument("formato")
    s.add_argument("--empresa")
    s.add_argument("--extensao", action="append")
    s.add_argument("--assinatura", help="bytes em hex, ex.: 584e42")
    s.add_argument("--offset", type=int, default=0)
    s.add_argument("--ordem", choices=["big", "little", "nenhuma", "desconhecida"])
    s.add_argument("--tipo", choices=["conteiner", "compressao", "modelo", "textura", "animacao", "audio", "video", "mapa", "dados", "codigo", "fonte", "imagem"])
    s.add_argument("--destino")
    s.add_argument("--conversor")
    s.add_argument("--decisao", choices=["converter", "ignorar", "substituir", "bloqueado"])
    s.add_argument("--motivo")
    s.add_argument("--documentacao", action="append")
    s.add_argument("--confianca", choices=["documentado", "engenharia_reversa", "hipotese"])
    s.set_defaults(func=cmd_formato_registrar)
    s = sub.add_parser("conversor-copiar", help="copia uma receita do cookbook para o projeto, para adaptar")
    s.add_argument("conversor")
    s.set_defaults(func=cmd_conversor_copiar)
    s = sub.add_parser("log-conversor", help="registra um passo do ciclo (pesquisar, amostrar, conferir...) em log_conversores.jsonl")
    s.add_argument("formato")
    s.add_argument("passo", choices=["pesquisar", "amostrar", "escrever", "testar", "conferir", "registrar", "decidir"])
    s.add_argument("--resultado", choices=["ok", "falhou", "info"], default="info")
    s.add_argument("--conversor")
    s.add_argument("--detalhes")
    s.add_argument("--evidencia", action="append")
    s.set_defaults(func=cmd_log_conversor)
    s = sub.add_parser("marcos", help="marcos de utilizacao/jogabilidade (marcos.json)")
    s.add_argument("acao", choices=["iniciar", "status"])
    s.add_argument("--modelo", choices=["jogo", "app"], default="jogo")
    s.add_argument("--sobrescrever", action="store_true")
    s.set_defaults(func=cmd_marcos)
    s = sub.add_parser("cena", help="elementos dos mapas: listar, mostrar, ajustar posicoes, regras de categoria/asset")
    s.add_argument("acao", choices=["listar", "mostrar", "ajustar", "regra"])
    s.add_argument("cena", nargs="?", help="id da cena (mostrar/ajustar; glob permitido em ajustar)")
    s.add_argument("--op", choices=["mover", "deslocar", "girar", "escalar", "grade", "remover", "definir", "adicionar"], default="mover")
    s.add_argument("--entidade", help="id e_<hex> (veja 'cew cena mostrar')")
    s.add_argument("--categoria")
    s.add_argument("--tipo-original")
    s.add_argument("--nome")
    s.add_argument("--camada")
    s.add_argument("--para", help="x,y,z (3D, metros) ou x,y (2D, pixels)")
    s.add_argument("--delta", help="dx,dy,dz")
    s.add_argument("--graus", type=float)
    s.add_argument("--fator", type=float)
    s.add_argument("--passo", type=float, help="grade: tamanho do passo")
    s.add_argument("--valores", help="definir: JSON com categoria, asset_id, nome, camada, propriedades")
    s.add_argument("--nova", help="adicionar: JSON da entidade nova (coordenadas ja normalizadas)")
    s.add_argument("--asset-glob", help="regra: glob sobre origem.caminho dos assets (ex.: '*ogre*')")
    s.add_argument("--remover", action="store_true", help="regra: tira estes elementos da cena")
    s.add_argument("--motivo")
    s.set_defaults(func=cmd_cena)
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
