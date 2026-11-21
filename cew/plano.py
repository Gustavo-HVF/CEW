"""Etapa 5: plano de conversao e delegacao de formatos desconhecidos ao Gemini.

- formato conhecido com conversor no registro -> item "pendente";
- conteiner/compressao ja aberto no inventario -> "concluido" (os filhos entram no plano);
- formato conhecido sem conversor -> "aguardando_conversor";
- desconhecido -> tarefa para o Gemini (schemas/gemini/tarefa_formato.schema.json), estado
  "aguardando_gemini"; a resposta (hipotese + rascunho) fica em tarefas_gemini/ para a IA
  principal revisar. Nada gerado pelo Gemini entra em converters/ automaticamente.
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
from .registro import Registro, registro_padrao

PRIORIDADE_TIPO = {"compressao": 1, "conteiner": 1, "textura": 2, "imagem": 2, "audio": 2, "modelo": 3, "animacao": 3, "mapa": 4, "dados": 4, "video": 5, "fonte": 5, "codigo": 5}
TIPOS_SO_ANALISE = {"codigo"}


def _destino(fmt: dict) -> str | None:
    d = fmt.get("destino_web") or {}
    if not d:
        return None
    valor = next(iter(d.values()))
    return re.split(r"[ |(]", valor)[0] or None


def montar(projeto: Projeto, registro: Registro | None = None) -> dict:
    reg = registro or registro_padrao()
    inv = projeto.ler("inventario")
    antigo = {i["id"]: i for i in projeto.ler("plano")["itens"]} if projeto.existe("plano") else {}
    por_id = {i["id"]: i for i in inv["itens"]}
    itens: list[dict[str, Any]] = []
    for it in inv["itens"]:
        pid = id_estavel("p", it["caminho"])
        fmt = reg.get(it["formato"]["id"])
        base: dict[str, Any] = {
            "id": pid, "item_inventario": it["id"], "caminho": it["caminho"], "formato_origem": it["formato"]["id"],
            "conversor": None, "formato_destino": None, "opcoes": {}, "dependencias": [], "prioridade": 3, "estado": "pendente",
            "tarefa_gemini": None, "hash_entrada": it["sha256"], "saidas": [], "erro": None,
        }
        if it["pai"]:
            base["dependencias"] = [id_estavel("p", por_id[it["pai"]]["caminho"])] if it["pai"] in por_id else []
        if it.get("extraido") or (it.get("compressao") or {}).get("descompactado_em"):
            base.update(estado="concluido", motivo="aberto na etapa de inventario; os arquivos internos estao no plano", prioridade=1, formato_destino="pasta")
        elif fmt is None:
            base.update(estado="aguardando_gemini", motivo="formato desconhecido: tarefa de analise para o Gemini", prioridade=4)
        elif fmt["tipo"] in TIPOS_SO_ANALISE:
            base.update(estado="ignorado", motivo="codigo executavel: vai para a etapa de engenharia reversa (Ghidra/Craft Anything)", prioridade=5)
        elif fmt["id"] == "generico.tabela_texto" and it["formato"]["camada"] not in ("contexto", "gemini"):
            base.update(estado="ignorado", motivo="texto generico identificado so pela extensao: confirme por contexto (analise/contexto.json) para converter", prioridade=5)
        elif fmt.get("conversor"):
            base.update(conversor=fmt["conversor"], formato_destino=_destino(fmt), prioridade=PRIORIDADE_TIPO.get(fmt["tipo"], 3))
            if fmt["tipo"] in ("conteiner", "compressao"):
                base.update(estado="erro", erro="conteiner nao pode ser aberto no inventario", motivo="; ".join(it.get("observacoes", [])) or "falha ao abrir")
        else:
            base.update(estado="aguardando_conversor", motivo=f"{fmt['id']} conhecido, mas sem conversor em converters/ (ferramentas de referencia no registro)", formato_destino=_destino(fmt), prioridade=PRIORIDADE_TIPO.get(fmt["tipo"], 3))
        ant = antigo.get(pid)
        if ant and ant.get("hash_entrada") == it["sha256"] and ant["estado"] == "concluido" and base["estado"] == "pendente":
            base.update(estado="concluido", saidas=ant.get("saidas", []))  # idempotencia: nada mudou
        if ant and ant.get("tarefa_gemini") and base["estado"] == "aguardando_gemini":
            base["tarefa_gemini"] = ant["tarefa_gemini"]
        itens.append(base)
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "gerado_em": agora_iso(), "projeto": projeto.nome,
           "resumo": dict(Counter(i["estado"] for i in itens)), "itens": itens}
    projeto.gravar("plano", doc)
    return doc


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
    reg = registro_padrao()
    inv = projeto.ler("inventario")
    plano = projeto.ler("plano")
    por_item = {i["id"]: i for i in inv["itens"]}
    pasta = projeto.caminho("tarefas_gemini")
    vistos: set[str] = set()
    relatorio = []
    for p in plano["itens"]:
        if p["estado"] != "aguardando_gemini" or len(relatorio) >= limite:
            continue
        item = por_item[p["item_inventario"]]
        if item["sha256"] in vistos or item["tamanho_bytes"] == 0:
            continue
        vistos.add(item["sha256"])
        tarefa = tarefa_formato(projeto, item, inv, reg)
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
