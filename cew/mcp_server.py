"""Servidor MCP leve "cew-mcp" (stdio, JSON-RPC 2.0, uma mensagem JSON por linha).

Implementa o minimo do Model Context Protocol para ferramentas: initialize,
notifications/initialized, ping, tools/list e tools/call. Ferramentas:
- listar_projetos         projetos em projects/ com a etapa atual
- estado_da_etapa         estado.json de um projeto (etapa atual, criterios, historico recente)
- rodar_conversor         roda um conversor de converters/ (saida sempre dentro de projects/)
- ver_manifesto           asset_manifest.json de um projeto (opcionalmente filtrado por tipo)
O Craft Anything tem o proprio servidor (`craft-anything-cli mcp`), configurado ao lado deste em
.vscode/mcp.json e .mcp.json.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path
from typing import Any

from . import __version__
from .caminhos import dentro_de, pasta_projetos
from .projeto import Projeto, listar_projetos

VERSOES_PROTOCOLO = ["2025-06-18", "2025-03-26", "2024-11-05"]

FERRAMENTAS = [
    {"name": "listar_projetos", "description": "Lista os projetos do CEW (projects/) com a etapa atual de cada um.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "estado_da_etapa", "description": "Mostra o estado.json de um projeto: etapa atual, estado e criterio de saida de cada etapa e o historico recente.",
     "inputSchema": {"type": "object", "properties": {"projeto": {"type": "string"}}, "required": ["projeto"], "additionalProperties": False}},
    {"name": "rodar_conversor", "description": "Roda um conversor de converters/ num arquivo. A saida fica dentro de projects/ (padrao: projects/_mcp/<arquivo>/). Use dry_run para so conferir.",
     "inputSchema": {"type": "object", "properties": {
         "conversor": {"type": "string", "description": "ex.: cookbook/nintendo/tpl_to_png.py"},
         "entrada": {"type": "string", "description": "caminho do arquivo de entrada"},
         "saida": {"type": "string", "description": "pasta de saida dentro de projects/ (opcional)"},
         "opcoes": {"type": "object"}, "dry_run": {"type": "boolean"}},
         "required": ["conversor", "entrada"], "additionalProperties": False}},
    {"name": "ver_manifesto", "description": "Mostra o asset_manifest.json de um projeto (o que o jogo web carrega).",
     "inputSchema": {"type": "object", "properties": {"projeto": {"type": "string"}, "tipo": {"type": "string", "description": "modelo, textura, audio, dados..."}},
                     "required": ["projeto"], "additionalProperties": False}},
]


def _listar_projetos(_: dict) -> Any:
    return listar_projetos()


def _estado(args: dict) -> Any:
    st = Projeto.abrir(args["projeto"], criar=False).estado()
    st["historico"] = st["historico"][-20:]
    return st


def _rodar_conversor(args: dict) -> Any:
    from .conversores import listar, rodar

    validos = {i["arquivo"] for i in listar()}
    if args["conversor"] not in validos:
        raise ValueError(f"conversor desconhecido; opcoes: {sorted(validos)}")
    entrada = Path(args["entrada"]).expanduser()
    if not entrada.is_file():
        raise ValueError(f"entrada nao encontrada: {entrada}")
    base = pasta_projetos()
    saida = Path(args["saida"]).expanduser() if args.get("saida") else base / "_mcp" / entrada.name
    if not saida.is_absolute():
        saida = base / saida
    if not dentro_de(saida, base):
        raise ValueError(f"a saida precisa ficar dentro de {base}")
    return rodar(args["conversor"], entrada, saida, args.get("opcoes") or {}, bool(args.get("dry_run")))


def _manifesto(args: dict) -> Any:
    p = Projeto.abrir(args["projeto"], criar=False)
    if not p.existe("manifesto"):
        raise ValueError("projeto ainda sem asset_manifest.json (etapa conversao)")
    m = p.ler("manifesto")
    if args.get("tipo"):
        m["assets"] = [a for a in m["assets"] if a["tipo"] == args["tipo"]]
    return m


ACOES = {"listar_projetos": _listar_projetos, "estado_da_etapa": _estado, "rodar_conversor": _rodar_conversor, "ver_manifesto": _manifesto}


def responder(msg: dict) -> dict | None:
    metodo = msg.get("method")
    mid = msg.get("id")
    if mid is None:  # notificacao: nunca responde
        return None
    try:
        if metodo == "initialize":
            pedida = (msg.get("params") or {}).get("protocolVersion")
            versao = pedida if pedida in VERSOES_PROTOCOLO else VERSOES_PROTOCOLO[0]
            res = {"protocolVersion": versao, "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "cew-mcp", "version": __version__}}
        elif metodo == "ping":
            res = {}
        elif metodo == "tools/list":
            res = {"tools": FERRAMENTAS}
        elif metodo == "tools/call":
            params = msg.get("params") or {}
            nome = params.get("name")
            if nome not in ACOES:
                return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": f"ferramenta desconhecida: {nome}"}}
            try:
                dados = ACOES[nome](params.get("arguments") or {})
                res = {"content": [{"type": "text", "text": json.dumps(dados, ensure_ascii=False, indent=2)}], "isError": False}
            except Exception as e:  # noqa: BLE001 - erro da ferramenta vai para o agente, nao derruba o servidor
                res = {"content": [{"type": "text", "text": f"erro: {e}"}], "isError": True}
        else:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"metodo nao suportado: {metodo}"}}
        return {"jsonrpc": "2.0", "id": mid, "result": res}
    except Exception as e:  # noqa: BLE001
        return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32603, "message": str(e), "data": traceback.format_exc()[-1000:]}}


def main() -> int:
    for linha in sys.stdin:
        linha = linha.strip()
        if not linha:
            continue
        try:
            msg = json.loads(linha)
        except ValueError:
            sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "JSON invalido"}}) + "\n")
            sys.stdout.flush()
            continue
        lote = msg if isinstance(msg, list) else [msg]
        respostas = [r for r in (responder(m) for m in lote if isinstance(m, dict)) if r is not None]
        if respostas:
            sys.stdout.write(json.dumps(respostas if isinstance(msg, list) else respostas[0], ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
