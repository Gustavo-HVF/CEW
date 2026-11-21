"""Etapa 5: plano de conversao e delegacao de formatos desconhecidos ao Gemini.

- formato com conversor pela cadeia de fontes (projeto -> cookbook -> generico) -> "pendente";
- conteiner/compressao ja aberto no inventario -> "concluido" (os filhos entram no plano);
- sem conversor (conhecido ou desconhecido) -> "aguardando_conversor", cobertura "falta_conversor":
  o agente da pessoa cria o conversor no projeto (skill 04) ou registra uma decisao;
- decisao ignorar/substituir/bloqueado no registro do projeto -> "ignorado";
- opcional: desconhecidos viram tarefa para o Gemini (schemas/gemini/tarefa_formato.schema.json);
  a resposta (hipotese + rascunho) fica em tarefas_gemini/ para a IA principal revisar.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import id_estavel
from .esquemas import gravar_json, validar
from .gemini import ClienteGemini, ErroGemini, Parte
from .logs import Log, agora_iso
from .projeto import Projeto
from .registro import Registro, registro_do_projeto

PRIORIDADE_TIPO = {"compressao": 1, "conteiner": 1, "textura": 2, "imagem": 2, "audio": 2, "modelo": 3, "animacao": 3, "mapa": 4, "dados": 4, "video": 5, "fonte": 5, "codigo": 5}
TIPOS_SO_ANALISE = {"codigo"}


def _destino(fmt: dict) -> str | None:
    d = fmt.get("destino_web") or {}
    if not d:
        return None
    valor = next(iter(d.values()))
    return re.split(r"[ |(]", valor)[0] or None


ESSENCIAIS = {"textura", "imagem", "modelo", "animacao", "audio", "mapa", "dados", "video", "fonte"}


def caminho_teste(ref: str, projeto_pasta: Path) -> Path | None:
    """conversores/x/nome.py -> conversores/x/nome.teste.json (so para conversores do projeto)."""
    from .conversores import PREFIXO_PROJETO

    if not ref.startswith(PREFIXO_PROJETO):
        return None
    arq = projeto_pasta / ref[len(PREFIXO_PROJETO):]
    return arq.with_name(arq.stem + ".teste.json")


def montar(projeto: Projeto, registro: Registro | None = None) -> dict:
    from .conversores import ErroConversor, config_cew, hash_codigo, resolver

    reg = registro or registro_do_projeto(projeto.pasta)
    inv = projeto.ler("inventario")
    antigo = {i["id"]: i for i in projeto.ler("plano")["itens"]} if projeto.existe("plano") else {}
    por_id = {i["id"]: i for i in inv["itens"]}
    hashes: dict[str, str | None] = {}
    itens: list[dict[str, Any]] = []
    for it in inv["itens"]:
        pid = id_estavel("p", it["caminho"])
        fid = it["formato"]["id"]
        fmt = reg.get(fid)
        fmt_proj = reg.projeto_por_id.get(fid) if fid else None
        base: dict[str, Any] = {
            "id": pid, "item_inventario": it["id"], "caminho": it["caminho"], "formato_origem": fid,
            "conversor": None, "fonte_conversor": None, "formato_destino": None, "opcoes": {}, "dependencias": [], "prioridade": 3,
            "estado": "pendente", "cobertura": "coberto", "tentativas": int((fmt_proj or {}).get("tentativas", 0)),
            "hash_conversor": None, "tarefa_gemini": None, "hash_entrada": it["sha256"], "saidas": [], "erro": None,
        }
        if it["pai"]:
            base["dependencias"] = [id_estavel("p", por_id[it["pai"]]["caminho"])] if it["pai"] in por_id else []
        if it.get("extraido") or (it.get("compressao") or {}).get("descompactado_em"):
            base.update(estado="concluido", motivo="aberto na etapa de inventario; os arquivos internos estao no plano", prioridade=1, formato_destino="pasta")
        elif fmt is None:
            base.update(estado="aguardando_conversor", cobertura="falta_conversor", prioridade=4,
                        motivo="formato desconhecido: registre-o (cew formato-registrar) e crie o conversor (skill 04); Gemini opcional")
        elif fmt["tipo"] in TIPOS_SO_ANALISE:
            base.update(estado="ignorado", cobertura="ignorado", prioridade=5, motivo="codigo executavel: vai para a etapa de engenharia reversa (Ghidra/Craft Anything)")
        elif fid == "generico.tabela_texto" and it["formato"]["camada"] not in ("contexto", "gemini") and not ((fmt_proj or {}).get("decisao") or {}).get("acao") == "converter":
            base.update(estado="ignorado", cobertura="ignorado", prioridade=5,
                        motivo="texto generico identificado so pela extensao: confirme por contexto (analise/contexto.json) ou decisao 'converter' no registro do projeto")
        else:
            esc = reg.conversor(fid)
            base.update(cobertura=esc["cobertura"], formato_destino=_destino(fmt), prioridade=PRIORIDADE_TIPO.get(fmt["tipo"], 3))
            if esc["cobertura"] == "coberto":
                ref = esc["ref"]
                if ref not in hashes:
                    try:
                        hashes[ref] = hash_codigo(resolver(ref, projeto.pasta))
                    except ErroConversor:
                        hashes[ref] = None
                base.update(conversor=ref, fonte_conversor=esc["fonte"], hash_conversor=hashes[ref])
                if hashes[ref] is None:
                    base.update(estado="erro", erro=f"conversor registrado nao encontrado: {ref}")
                elif fmt["tipo"] in ("conteiner", "compressao"):
                    base.update(estado="erro", erro="conteiner nao pode ser aberto no inventario", motivo="; ".join(it.get("observacoes", [])) or "falha ao abrir")
            elif esc["cobertura"] in ("ignorado", "bloqueado"):
                d = esc["decisao"]
                base.update(estado="ignorado", motivo=f"decisao '{d['acao']}': {d['motivo']}")
            else:
                base.update(estado="aguardando_conversor", motivo=f"{fid} conhecido, sem conversor nas fontes {config_cew()['fontes_conversores']} (crie no projeto: skill 04)")
        ant = antigo.get(pid)
        if (ant and ant["estado"] == "concluido" and base["estado"] == "pendente" and ant.get("hash_entrada") == it["sha256"]
                and ant.get("hash_conversor") == base["hash_conversor"] and ant.get("conversor") == base["conversor"]):
            base.update(estado="concluido", saidas=ant.get("saidas", []))  # idempotencia: entrada e codigo iguais
        if ant and ant.get("tarefa_gemini") and base["formato_origem"] is None:
            base["tarefa_gemini"] = ant["tarefa_gemini"]
        itens.append(base)
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "gerado_em": agora_iso(), "projeto": projeto.nome,
           "resumo": dict(Counter(i["estado"] for i in itens)), "formatos": grupos(itens, inv, reg), "itens": itens}
    projeto.gravar("plano", doc)
    return doc


def _chave_grupo(item_plano: dict, item_inv: dict) -> str:
    if item_plano["formato_origem"]:
        return item_plano["formato_origem"]
    ext = PurePosixPath(item_inv["caminho"].split("!/")[-1]).suffix.lower() or "(sem extensao)"
    return f"desconhecido:{ext}"


def grupos(itens: list[dict], inv: dict, reg: Registro) -> list[dict]:
    """Resumo por formato, com prioridade pelo impacto (quantidade, bytes e tipo)."""
    from .conversores import config_cew

    minimo = int(config_cew().get("prioridade_alta_min_itens", 5))
    por_inv = {i["id"]: i for i in inv["itens"]}
    acc: dict[str, dict] = {}
    for p in itens:
        if p["estado"] == "concluido" and p.get("formato_destino") == "pasta":
            continue
        it = por_inv[p["item_inventario"]]
        g = acc.setdefault(_chave_grupo(p, it), {"itens": 0, "bytes": 0, "cobertura": set(), "conversor": p["conversor"], "formato_id": p["formato_origem"]})
        g["itens"] += 1
        g["bytes"] += it["tamanho_bytes"]
        g["cobertura"].add(p["cobertura"])
    saida = []
    for chave, g in sorted(acc.items()):
        cob = next((c for c in ("falta_conversor", "bloqueado", "coberto", "ignorado") if c in g["cobertura"]), "coberto")
        fmt = reg.get(g["formato_id"]) or {}
        essencial = fmt.get("tipo") in ESSENCIAIS or g["formato_id"] is None
        if essencial and (g["itens"] >= minimo or g["bytes"] >= 10 * 1024 * 1024):
            prio = "alta"
        elif g["itens"] >= 2 or essencial:
            prio = "media"
        else:
            prio = "baixa"
        decisao = ((reg.projeto_por_id.get(g["formato_id"]) or {}).get("decisao") or {}).get("acao") if g["formato_id"] else None
        saida.append({"formato": chave, "itens": g["itens"], "bytes": g["bytes"], "cobertura": cob, "prioridade": prio, "conversor": g["conversor"], "decisao": decisao})
    return saida


def criterio_saida(projeto: Projeto) -> tuple[bool, list[str]]:
    """Conversao -> Motor: sem erros; sem formato de prioridade alta sem conversor nem decisao;
    conversores do projeto com teste do harness aprovado para o hash atual do codigo."""
    import json as _json

    plano = projeto.ler("plano")
    faltas = [f"erro em {i.get('caminho')}: {i.get('erro')}" for i in plano["itens"] if i["estado"] == "erro"]
    for g in plano.get("formatos", []):
        if g["cobertura"] == "falta_conversor" and g["prioridade"] == "alta" and not g.get("decisao"):
            faltas.append(f"{g['formato']}: {g['itens']} arquivos sem conversor nem decisao (crie o conversor ou registre a decisao)")
    vistos = set()
    for i in plano["itens"]:
        ref = i.get("conversor")
        if not ref or ref in vistos or i["estado"] not in ("pendente", "concluido"):
            continue
        vistos.add(ref)
        arq = caminho_teste(ref, projeto.pasta)
        if arq is None:
            continue
        if not arq.is_file():
            faltas.append(f"{ref}: sem teste do harness (cew conversor-testar)")
            continue
        t = _json.loads(arq.read_text(encoding="utf-8"))
        if not t.get("aprovado") or t.get("hash_codigo") != i.get("hash_conversor"):
            faltas.append(f"{ref}: teste do harness reprovado ou desatualizado (codigo mudou)")
    return not faltas, faltas


# ------------------------------------------------------------------------------ Gemini
def _strings_ascii(dados: bytes, minimo: int = 5, maximo: int = 40) -> list[str]:
    return [m.decode("ascii")[:120] for m in re.findall(rb"[\x20-\x7e]{%d,}" % minimo, dados)][:maximo]


def tarefa_formato(projeto: Projeto, item: dict, inventario: dict, registro: Registro, contexto_programa: list[dict] | None = None) -> dict:
    """Monta a tarefa so com trechos relevantes (item 1.6): cabecalho, amostras e strings."""
    if item["origem"] == "alvo":
        base = Path(inventario["alvo"]["caminho"])
        disco = base if base.is_file() else base / item["caminho_no_disco"]
    else:
        disco = projeto.pasta / item["caminho_no_disco"]
    dados = disco.read_bytes()[: 1024 * 1024]
    amostras = [{"offset": 0, "hex": dados[:256].hex()}]
    if len(dados) > 1024:
        meio = (len(dados) // 2) & ~0xF
        amostras.append({"offset": meio, "hex": dados[meio : meio + 128].hex()})
    if len(dados) > 512:
        fim = max(0, len(dados) - 128) & ~0xF
        amostras.append({"offset": fim, "hex": dados[fim : fim + 128].hex()})
    ext = PurePosixPath(item["caminho"]).suffix.lower()
    irmaos = sum(1 for i in inventario["itens"] if PurePosixPath(i["caminho"]).suffix.lower() == ext and i["id"] != item["id"]) if ext else 0
    parecidos = [f["id"] for f in registry_parecidos(registro, item)]
    tarefa = {
        "schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "tarefa": "formato", "id": id_estavel("t", item["sha256"]),
        "item_inventario": item["id"], "caminho": item["caminho"], "extensao": ext, "tamanho_bytes": item["tamanho_bytes"], "sha256": item["sha256"],
        "entropia_bits_por_byte": item["entropia_bits_por_byte"], "ordem_de_bytes_estimada": item["ordem_de_bytes"], "amostras": amostras,
        "strings_ascii": _strings_ascii(dados), "irmaos_mesma_extensao": irmaos, "formatos_parecidos": parecidos[:10],
        "instrucoes": ("Proponha a estrutura deste formato a partir dos bytes. Para cada campo do cabecalho, cite offset e os bytes "
                       "que sustentam a leitura. Se houver um rascunho de conversor, use Python 3 so com a biblioteca padrao e com o "
                       "esqueleto de converters/comum/cli.py (INFO, converter(dados, esc, opcoes), executar). Leia de forma defensiva."),
    }
    if contexto_programa:
        tarefa["contexto_programa"] = contexto_programa[:4]
    validar(tarefa, "gemini/tarefa_formato")
    return tarefa


def registry_parecidos(registro: Registro, item: dict) -> list[dict]:
    ext = PurePosixPath(item["caminho"]).suffix.lower()
    return [f for f in registro.formatos if ext and ext in f["extensoes"]]


def _validar_resposta_formato(resp: dict) -> list[str]:
    erros = []
    if not re.match(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$", resp.get("formato_id_proposto", "")):
        erros.append("formato_id_proposto fora do padrao empresa.familia.nome")
    return erros


def delegar_desconhecidos(projeto: Projeto, cliente: ClienteGemini | None = None, limite: int = 20, dry_run: bool = False, log: Log | None = None) -> list[dict]:
    """Cria tarefas para os itens desconhecidos (um por SHA-256) e, fora do dry-run, chama o Gemini."""
    log = log or Log("plano")
    reg = registro_do_projeto(projeto.pasta)
    inv = projeto.ler("inventario")
    plano = projeto.ler("plano")
    por_item = {i["id"]: i for i in inv["itens"]}
    pasta = projeto.caminho("tarefas_gemini")
    vistos: set[str] = set()
    relatorio = []
    arq_carr = projeto.caminho("analise") / "carregadores.json"
    carregadores = __import__("json").loads(arq_carr.read_text(encoding="utf-8"))["carregadores"] if arq_carr.is_file() else []
    for p in plano["itens"]:
        if p["formato_origem"] is not None or p["estado"] != "aguardando_conversor" or len(relatorio) >= limite:
            continue
        item = por_item[p["item_inventario"]]
        if item["sha256"] in vistos or item["tamanho_bytes"] == 0:
            continue
        vistos.add(item["sha256"])
        ext = PurePosixPath(item["caminho"]).suffix.lower()
        magia = item.get("assinatura_texto", "")[:4]
        ctx = [{"funcao": c["funcao"], "endereco": c["endereco"], "pseudo_c": c["pseudo_c"]} for c in carregadores
               if c.get("pseudo_c") and (c["chave"] == ext or c["chave"] == magia)]
        tarefa = tarefa_formato(projeto, item, inv, reg, ctx or None)
        arq_tarefa = pasta / f"{item['sha256']}.tarefa.json"
        arq_resp = pasta / f"{item['sha256']}.resposta.json"
        p["tarefa_gemini"] = arq_tarefa.relative_to(projeto.pasta).as_posix()
        if dry_run:
            relatorio.append({"item": item["caminho"], "acao": "criaria tarefa e chamaria o Gemini"})
            continue
        gravar_json(arq_tarefa, tarefa, "gemini/tarefa_formato")
        if arq_resp.is_file():
            relatorio.append({"item": item["caminho"], "acao": "resposta ja existe"})
            continue
        cliente = cliente or ClienteGemini()
        texto = "Tarefa do CEW (JSON):\n" + __import__("json").dumps(tarefa, ensure_ascii=False)
        try:
            resp = cliente.gerar("formato", [Parte(texto=texto)], "gemini/resposta_formato", validacao_extra=_validar_resposta_formato)
            gravar_json(arq_resp, resp, "gemini/resposta_formato")
            relatorio.append({"item": item["caminho"], "acao": "resposta recebida", "formato_proposto": resp["formato_id_proposto"], "confianca": resp["confianca"]})
        except ErroGemini as e:
            p["erro"] = str(e)
            log.aviso(f"Gemini falhou para {item['caminho']}: {e}", etapa="conversao", item=item["id"])
            relatorio.append({"item": item["caminho"], "acao": "falha", "erro": str(e)})
    if not dry_run:
        projeto.gravar("plano", plano)
    return relatorio
