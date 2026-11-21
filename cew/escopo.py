"""Etapa 0 do v2.3: analisar o projeto com franqueza e registrar o escopo minimo jogavel combinado.

`analisar` le inventario, plano de conversao, plano de traducao, cenas, marcos, cobertura e relatorio e
devolve numeros, limites da plataforma web e uma PROPOSTA de escopo. `definir` registra a decisao da
pessoa (marcos obrigatorios em marcos.json, escopo.json e historico em estado.json).
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from . import GERADO_POR, SCHEMA_VERSION
from .esquemas import gravar_json, ler_json
from .logs import agora_iso
from .projeto import Projeto

LIMITES = {
    "rede": ("o navegador nao abre socket TCP/UDP", "WebSocket/WebRTC com servidor proprio"),
    "plataforma": ("threads, janela, sleep e saida do processo nao existem como no desktop", "laco do motor, Web Worker, voltar ao menu"),
    "salvamento": ("sem arquivos locais", "localStorage/IndexedDB (src/adaptadores/salvamento.js)"),
}


def _ler(p: Path, esquema: str):
    return ler_json(p, esquema) if p.is_file() else None


def analisar(projeto: Projeto, gravar: bool = True) -> dict:
    pasta = projeto.pasta
    inv = projeto.ler("inventario") if projeto.existe("inventario") else {"itens": []}
    plano = projeto.ler("plano") if projeto.existe("plano") else {"itens": [], "formatos": []}
    trad = _ler(pasta / "codigo" / "plano_traducao.json", "plano_traducao")
    marcos = _ler(pasta / "marcos.json", "marcos")
    cob = _ler(pasta / "cobertura_conteudo.json", "cobertura_conteudo")
    rel = _ler(pasta / "relatorio_verificacao.json", "relatorio_verificacao")
    from .cenas import cenas_publicadas

    cenas = cenas_publicadas(projeto)
    unidades = [u for u in (trad or {}).get("unidades", []) if u["estado"] != "descartada"]
    alta = [u for u in unidades if u["prioridade"] == "alta"]
    falta = [g for g in plano.get("formatos", []) if g["cobertura"] == "falta_conversor"]
    cats = Counter(e["categoria"] for _, c in cenas for e in c["entidades"])
    numeros = {
        "arquivos_no_alvo": len(inv["itens"]),
        "assets_publicados": len(projeto.ler("manifesto")["assets"]) if projeto.existe("manifesto") else 0,
        "formatos_sem_conversor": len(falta),
        "formatos_sem_conversor_alta": sum(1 for g in falta if g["prioridade"] == "alta" and not g.get("decisao")),
        "unidades_de_codigo": len(unidades),
        "unidades_alta": len(alta),
        "unidades_alta_traduzidas": sum(1 for u in alta if u["estado"] in ("traduzida", "testada")),
        "unidades_alta_testadas": sum(1 for u in alta if u["estado"] == "testada"),
        "cenas": len(cenas),
        "elementos_de_cena": sum(cats.values()),
        "inimigos_npcs": cats.get("inimigo", 0) + cats.get("npc", 0),
        "assets_usados_nos_testes_pct": round(100 * cob["usados"] / cob["total"]) if cob and cob["total"] else None,
        "marco_atingido": (rel or {}).get("marco_atingido"),
        "linguagem_destino": (trad or {}).get("linguagem_destino"),
    }
    limites = []
    for papel, (lim, alt) in LIMITES.items():
        quem = [u["nome"] for u in unidades if u["papel"] == papel][:5]
        if quem:
            limites.append({"limite": lim, "evidencia": f"unidades com papel '{papel}': {', '.join(quem)}", "alternativa": alt})
    rede = sorted({e.split(" ->")[0] for u in unidades for e in u.get("equivalencias", []) if any(k in e for k in ("socket", "send", "recv", "connect", "WSAStartup"))})
    if rede and not any("rede" in l["evidencia"] for l in limites):
        limites.append({"limite": LIMITES["rede"][0], "evidencia": f"chamadas de rede no codigo: {', '.join(rede[:5])}", "alternativa": LIMITES["rede"][1]})
    carga = numeros["unidades_alta"] + 5 * numeros["formatos_sem_conversor_alta"] + numeros["inimigos_npcs"] // 5
    tamanho = "pequeno" if carga <= 15 else ("medio" if carga <= 80 else "grande")
    ids = [m["id"] for m in (marcos or {}).get("marcos", [])]
    preferidos = ["abre", "entrada", "colisao", "laco_central"] if (marcos or {}).get("modelo", "jogo") != "app" else ["abre", "navegacao", "acao_principal"]
    sugeridos = [m for m in preferidos if m in ids] or ids[:3]
    primeira = sorted((c["id_cena"] for _, c in cenas))[:1]
    motivos = [f"{numeros['unidades_alta']} unidades de codigo de prioridade alta ({numeros['unidades_alta_traduzidas']} ja traduzidas)",
               f"{numeros['formatos_sem_conversor_alta']} formatos de prioridade alta ainda sem conversor ou decisao",
               f"tamanho estimado: {tamanho}"]
    if tamanho == "grande":
        motivos.append("jogo grande: semanas de trabalho; comece por uma fase e o laco central")
    proposta = {"descricao": f"primeira fase jogavel{(' (' + primeira[0] + ')') if primeira else ''}: " + ", ".join(sugeridos),
                "marcos": sugeridos, "motivos": motivos}
    antigo = _ler(pasta / "escopo.json", "escopo")
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "analisado_em": agora_iso(), "numeros": numeros,
           "limites_web": limites, "tamanho_estimado": tamanho, "proposta": proposta, "decisao": (antigo or {}).get("decisao")}
    if gravar:
        gravar_json(pasta / "escopo.json", doc, "escopo")
    return doc


def definir(projeto: Projeto, marcos_ids: list[str], descricao: str, nota: str = "") -> dict:
    """Registra o escopo combinado: so os marcos escolhidos ficam obrigatorios."""
    from . import marcos as _marcos

    doc_m = _marcos.ler(projeto)
    if doc_m is None:
        raise ValueError("sem marcos.json: rode 'cew marcos iniciar' (ou a etapa reconstrucao) antes")
    ids = {m["id"] for m in doc_m["marcos"]}
    faltando = [m for m in marcos_ids if m not in ids]
    if faltando:
        raise ValueError(f"marcos inexistentes: {faltando} (existentes: {sorted(ids)})")
    for m in doc_m["marcos"]:
        m["obrigatorio"] = m["id"] in marcos_ids
    gravar_json(_marcos.caminho(projeto), doc_m, "marcos")
    esc = analisar(projeto, gravar=False)
    esc["decisao"] = {"descricao": descricao, "marcos": marcos_ids, "em": agora_iso(), **({"nota": nota} if nota else {})}
    gravar_json(projeto.pasta / "escopo.json", esc, "escopo")
    st = projeto.estado()
    st["historico"].append({"ts": agora_iso(), "etapa": "reconstrucao", "evento": f"escopo combinado: {descricao} (marcos obrigatorios: {', '.join(marcos_ids)})"})
    projeto.gravar("estado", st)
    return esc
