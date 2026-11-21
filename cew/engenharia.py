"""Etapa 4: engenharia reversa com Craft Anything (modo Deep) + Ghidra.

Saidas:
- analise/craft_triage.json        resultado real de `craft-anything-cli --deep triage <alvo>`
- analise/<programa>-<id8>.json    exportacao do Ghidra (schemas/analise_programa.schema.json)
- analise/carregadores.json        funcoes que referenciam extensoes/assinaturas vistas no inventario
- analise/hipoteses.json           hipoteses de formato com evidencia (schemas/hipoteses_formato.schema.json)
- especificacoes/<formato>.md      uma especificacao por formato que sera convertido

A logica do jogo (maquina de estados, fisica, controles) e decodificada pela IA principal a
partir destes arquivos (skills/03); aqui o CEW produz a evidencia e o esqueleto.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path, PurePosixPath

from . import GERADO_POR, SCHEMA_VERSION
from . import craft, ghidra
from .caminhos import slug
from .esquemas import gravar_json, ler_json
from .logs import Log
from .projeto import Projeto
from .registro import registro_padrao

TIPOS_PROGRAMA = {"codigo"}


def _disco(projeto: Projeto, item: dict, inv: dict) -> Path:
    if item["origem"] == "alvo":
        base = Path(inv["alvo"]["caminho"])
        return base if base.is_file() else base / item["caminho_no_disco"]
    return projeto.pasta / item["caminho_no_disco"]


def programas(projeto: Projeto, inv: dict, limite: int = 5) -> list[dict]:
    reg = registro_padrao()
    progs = [i for i in inv["itens"] if (reg.get(i["formato"]["id"]) or {}).get("tipo") in TIPOS_PROGRAMA]
    return sorted(progs, key=lambda i: -i["tamanho_bytes"])[:limite]


def carregadores(analises: list[dict], inv: dict) -> list[dict]:
    """Strings do programa que citam extensoes ou assinaturas do inventario -> funcoes candidatas."""
    exts = {PurePosixPath(i["caminho"]).suffix.lower() for i in inv["itens"] if PurePosixPath(i["caminho"]).suffix}
    magias = {i.get("assinatura_texto", "")[:4] for i in inv["itens"] if i.get("assinatura_texto", "")[:4].isalnum()}
    achados = []
    for a in analises:
        funcs = {f["endereco"]: f for f in a["funcoes"]}
        for s in a["strings"]:
            v = s["valor"]
            alvo = next((e for e in exts if e and v.lower().endswith(e)), None) or next((m for m in magias if m and m == v[:4]), None)
            if not alvo:
                continue
            for end in s.get("referenciado_por", []):
                f = funcs.get(end, {})
                achados.append({"programa": a["programa"]["nome"], "string": v, "chave": alvo, "funcao": f.get("nome", end), "endereco": end,
                                "pseudo_c": (f.get("pseudo_c") or "")[:6000]})
    return achados


def hipoteses_e_specs(projeto: Projeto, inv: dict, plano: dict | None, achados: list[dict]) -> dict:
    reg = registro_padrao()
    por_formato: dict[str, list[dict]] = defaultdict(list)
    for i in inv["itens"]:
        if i["formato"]["id"]:
            por_formato[i["formato"]["id"]].append(i)
    convertidos = {p["formato_origem"] for p in (plano or {}).get("itens", []) if p["estado"] in ("pendente", "concluido") and p.get("conversor")}
    antigas = {h["formato_id"]: h for h in projeto.ler("hipoteses")["hipoteses"]} if projeto.existe("hipoteses") else {}
    hipoteses = []
    pasta_spec = projeto.caminho("especificacoes")
    for fid, itens in sorted(por_formato.items()):
        f = reg.get(fid)
        if not f:
            continue
        if fid in antigas and antigas[fid]["estado"] in ("confirmada", "refutada") and antigas[fid].get("evidencias"):
            hipoteses.append(antigas[fid])  # decisao da IA principal prevalece
            continue
        ev = []
        ex = itens[0]
        if f.get("assinatura") and ex["formato"]["camada"] in ("assinatura", "estrutura", "extensao"):
            ev.append({"fonte": "arquivo", "arquivo": ex["caminho"], "offset": max(0, f["assinatura"]["offset"]),
                       "nota": f"assinatura {f['assinatura']['bytes_hex']} encontrada; camada {ex['formato']['camada']}, confianca {ex['formato']['confianca']}"})
        for url in f.get("documentacao", [])[:2]:
            ev.append({"fonte": "documentacao", "url": url})
        for a in achados:
            if PurePosixPath(ex["caminho"]).suffix.lower() == a["chave"] or ex.get("assinatura_texto", "")[:4] == a["chave"]:
                ev.append({"fonte": "ghidra", "funcao": a["funcao"], "endereco": a["endereco"], "trecho_pseudocodigo": a["pseudo_c"][:1500], "nota": f"referencia a {a['string']!r}"})
        if not ev:
            ev.append({"fonte": "arquivo", "arquivo": ex["caminho"], "nota": f"identificado pela camada {ex['formato']['camada']}"})
        documentado = f["confianca"] == "documentado" and any(e["fonte"] == "documentacao" for e in ev) and any(e["fonte"] == "arquivo" and "assinatura" in e.get("nota", "") for e in ev)
        teste = f["verificacao"]["estado"] != "a_verificar"
        # confirmada: conversor testado E (documentacao publica + assinatura) ou identificacao forte no arquivo
        estado = "confirmada" if teste and (documentado or ex["formato"]["confianca"] >= 0.75) else "hipotese"
        spec = f"especificacoes/{fid}.md"
        hipoteses.append({"formato_id": fid, "itens_inventario": [i["id"] for i in itens][:50], "descricao": f.get("nome") or f["observacoes"] or fid,
                          "estado": estado, "especificacao": spec, "evidencias": ev})
        arq = projeto.pasta / spec
        if not arq.is_file() and (fid in convertidos or estado == "hipotese"):
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_text(_spec_md(f, itens, ev, estado), encoding="utf-8")
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "hipoteses": hipoteses}
    projeto.gravar("hipoteses", doc)
    return doc


def _spec_md(f: dict, itens: list[dict], ev: list[dict], estado: str) -> str:
    sig = f.get("assinatura")
    linhas = [f"# {f['id']}", "", f"- Empresa/motor: {f['empresa_ou_motor']}", f"- Tipo: {f['tipo']}", f"- Ordem de bytes: {f['ordem_de_bytes']}",
              f"- Estado da hipotese: **{estado}**", f"- Conversor: `{f.get('conversor') or 'nenhum ainda'}`",
              f"- Exemplos no alvo: {len(itens)} (ex.: `{itens[0]['caminho']}`)", "", "## Cabecalho", "",
              "| Offset | Tipo | Tamanho | Campo | Evidencia |", "|---|---|---|---|---|"]
    if sig:
        n = len(sig["bytes_hex"]) // 2
        linhas.append(f"| 0x{max(0, sig['offset']):X} | char[{n}] | {n} | magic `{sig.get('texto') or sig['bytes_hex']}` | assinatura no arquivo |")
    linhas += ["| ... | ... | ... | (preencher a partir do pseudo-C/documentacao) | ... |", "", "## Exemplo em hex (primeiros 16 bytes)", "", "```", itens[0]["assinatura_hex"], "```", "",
               "## Evidencias", ""]
    for e in ev:
        linhas.append(f"- {e['fonte']}: " + ", ".join(f"{k}={v}" for k, v in e.items() if k not in ("fonte", "trecho_pseudocodigo")))
    linhas += ["", "## Duvidas", "", "- (o que ainda precisa de evidencia)", ""]
    return "\n".join(linhas)


def executar(projeto: Projeto, dry_run: bool = False, usar_ghidra: bool = True, usar_craft: bool = True, log: Log | None = None) -> dict:
    log = log or Log("engenharia")
    inv = projeto.ler("inventario")
    plano = projeto.ler("plano") if projeto.existe("plano") else None
    rel: dict = {"craft_anything": None, "ghidra": [], "avisos": []}
    pasta = projeto.caminho("analise")
    alvo = Path(inv["alvo"]["caminho"])
    if usar_craft:
        cli = craft.localizar_cli()
        if not cli:
            rel["avisos"].append("craft-anything-cli nao encontrado: triage pulado (rode 'cew setup')")
        elif dry_run:
            rel["craft_anything"] = f"[dry-run] {cli} --deep --project {projeto.pasta / 'investigation.cany'} triage {alvo}"
        else:
            try:
                t = craft.triage(alvo, projeto.pasta / "investigation.cany")
                (pasta / "craft_triage.json").write_text(json.dumps(t, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                rel["craft_anything"] = "analise/craft_triage.json"
            except (craft.ErroCraft, OSError) as e:
                rel["avisos"].append(f"triage do Craft Anything falhou: {e}")
    analises = []
    for arq in sorted(pasta.glob("*.json")):
        if arq.name not in ("hipoteses.json", "contexto.json", "craft_triage.json", "carregadores.json"):
            try:
                analises.append(ler_json(arq, "analise_programa"))
            except Exception:  # noqa: BLE001
                continue
    if usar_ghidra:
        inst = ghidra.localizar()
        progs = programas(projeto, inv)
        if not progs:
            rel["avisos"].append("nenhum executavel/ROM no inventario: Ghidra nao foi necessario")
        elif not inst:
            rel["avisos"].append("Ghidra nao encontrado (defina GHIDRA_INSTALL_DIR): analise de codigo pulada")
        else:
            jv, _ = ghidra.versao_java()
            if jv is not None and inst.java_minimo and jv < inst.java_minimo:
                rel["avisos"].append(f"Ghidra {inst.versao} exige Java {inst.java_minimo}, encontrado {jv}")
            for it in progs:
                saida = pasta / f"{slug(PurePosixPath(it['caminho']).stem)}-{it['id'][2:10]}.json"
                if saida.is_file() and not dry_run:
                    try:
                        if ler_json(saida, "analise_programa")["programa"].get("sha256") == it["sha256"]:
                            rel["ghidra"].append(saida.name + " (reaproveitado)")
                            continue
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    cmd = ghidra.exportar(inst, _disco(projeto, it, inv), saida, dry_run=dry_run)
                    if dry_run:
                        rel["ghidra"].append("[dry-run] " + " ".join(cmd))
                    else:
                        analises.append(ler_json(saida, "analise_programa"))
                        rel["ghidra"].append(saida.name)
                except Exception as e:  # noqa: BLE001
                    rel["avisos"].append(f"Ghidra falhou em {it['caminho']}: {e}")
    if dry_run:
        return rel
    achados = carregadores(analises, inv)
    gravar_json(pasta / "carregadores.json", {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "carregadores": achados}, None)
    h = hipoteses_e_specs(projeto, inv, plano, achados)
    rel["hipoteses"] = len(h["hipoteses"])
    rel["carregadores_candidatos"] = len(achados)
    for a in rel["avisos"]:
        log.aviso(a, etapa="engenharia")
    return rel


def criterio_saida(projeto: Projeto) -> tuple[bool, list[str]]:
    """Engenharia -> Conversao: especificacao com evidencia para cada formato que sera convertido."""
    if not projeto.existe("plano") or not projeto.existe("hipoteses"):
        return False, ["plano_conversao.json ou analise/hipoteses.json ausente"]
    plano = projeto.ler("plano")
    hips = {h["formato_id"]: h for h in projeto.ler("hipoteses")["hipoteses"]}
    faltas = []
    for fid in sorted({p["formato_origem"] for p in plano["itens"] if p["estado"] == "pendente" and p.get("conversor") and not p["conversor"].endswith("copiar_web.py")}):
        h = hips.get(fid)
        if not h or h["estado"] != "confirmada" or not h["evidencias"]:
            faltas.append(f"{fid}: hipotese nao confirmada")
        elif not (projeto.pasta / h.get("especificacao", "")).is_file():
            faltas.append(f"{fid}: especificacao ausente")
    return not faltas, faltas
