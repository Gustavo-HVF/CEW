"""Criterios de "jogavel" (v2.3, item 7) e a confirmacao da pessoa.

Criterios: escopo definido; marcos obrigatorios aprovados, incluindo o laco central; testes de
equivalencia das unidades de codigo que o jogo usa (alcancaveis a partir de app/src/main.js);
nenhum esqueleto "ainda nao traduzida" alcancavel; sessao curta sem erros; build estatico;
confirmacao da pessoa (registrada so por terminal interativo).
"""

from __future__ import annotations

import re
from pathlib import Path

from . import GERADO_POR, SCHEMA_VERSION
from .esquemas import gravar_json, ler_json
from .logs import agora_iso
from .projeto import Projeto

MARCADOR_ESQUELETO = "ainda nao traduzida"
CENTRAIS = ("laco_central", "acao_principal")
_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(\s*|import\s+)['"](\.{1,2}/[^'"]+)['"]""")


def alcancaveis(app: Path, entrada: str = "src/main.js") -> set[Path]:
    """Arquivos JS alcancaveis por import relativo a partir da entrada do app."""
    vistos: set[Path] = set()
    pilha = [(app / entrada).resolve()]
    while pilha:
        arq = pilha.pop()
        if arq in vistos or not arq.is_file():
            continue
        vistos.add(arq)
        for alvo in _IMPORT.findall(arq.read_text(encoding="utf-8", errors="replace")):
            destino = (arq.parent / alvo).resolve()
            if destino.suffix == "":
                destino = destino.with_suffix(".js")
            pilha.append(destino)
    return vistos


def esqueletos_alcancaveis(projeto: Projeto) -> list[str]:
    app = projeto.pasta / "app"
    return sorted(str(a.relative_to(projeto.pasta)) for a in alcancaveis(app) if MARCADOR_ESQUELETO in a.read_text(encoding="utf-8", errors="replace"))


def unidades_usadas(projeto: Projeto) -> list[dict]:
    arq = projeto.pasta / "codigo" / "plano_traducao.json"
    if not arq.is_file():
        return []
    usados = {str(a) for a in alcancaveis(projeto.pasta / "app")}
    return [u for u in ler_json(arq, "plano_traducao")["unidades"] if str((projeto.pasta / u["destino"]).resolve()) in usados]


def avaliar(projeto: Projeto, gravar: bool = True) -> dict:
    pasta = projeto.pasta
    crit = []

    def c(id_: str, ok: bool, det: str) -> None:
        crit.append({"id": id_, "aprovado": bool(ok), "detalhes": det})

    esc = ler_json(pasta / "escopo.json", "escopo") if (pasta / "escopo.json").is_file() else None
    dec = (esc or {}).get("decisao")
    c("escopo_definido", dec is not None, dec["descricao"] if dec else "escopo ainda nao combinado: cew escopo analisar / definir")
    rel = ler_json(pasta / "relatorio_verificacao.json", "relatorio_verificacao") if (pasta / "relatorio_verificacao.json").is_file() else None
    itens = (rel or {}).get("itens", [])
    marcos = ler_json(pasta / "marcos.json", "marcos") if (pasta / "marcos.json").is_file() else None
    obrig = [m for m in (marcos or {}).get("marcos", []) if m["obrigatorio"]]
    reprov = [m["id"] for m in obrig if m["estado"] != "aprovado"]
    c("marcos_obrigatorios", bool(obrig) and not reprov, f"{len(obrig) - len(reprov)}/{len(obrig)} aprovados" + (f"; faltam {reprov}" if reprov else ""))
    central = next((m for m in obrig if m["id"] in CENTRAIS), None)
    c("laco_central", central is not None and central["estado"] == "aprovado",
      "laco central aprovado" if central and central["estado"] == "aprovado" else ("laco central fora do escopo obrigatorio" if central is None else f"laco central {central['estado']}"))
    usadas = unidades_usadas(projeto)
    sem_teste = [u["nome"] for u in usadas if u["estado"] != "testada"]
    c("equivalencia", not sem_teste, f"{len(usadas) - len(sem_teste)}/{len(usadas)} unidades usadas pelo jogo com testes de equivalencia aprovados"
      + (f"; sem teste aprovado: {sem_teste[:8]}" if sem_teste else ""))
    esq = esqueletos_alcancaveis(projeto)
    c("sem_esqueleto_alcancavel", not esq, "nenhum esqueleto alcancavel a partir de src/main.js" if not esq else f"esqueletos alcancaveis: {esq[:5]}")
    sessao = next((i for i in itens if i["categoria"] == "navegador" and "sessao" in i["alvo"]), None)
    c("sessao", bool(sessao and sessao["aprovado"]), sessao["detalhes"] if sessao else "sessao curta ainda nao rodou (cew check)")
    build = next((i for i in itens if i["id"] == "build_web"), None)
    c("build_estatico", bool(build and build["aprovado"]) and (pasta / "app" / "dist" / "index.html").is_file(),
      "dist/ gerado e servido como arquivos estaticos nos testes" if build and build["aprovado"] else "build web ausente ou reprovado")
    antigo = ler_json(pasta / "jogavel.json", "jogavel") if (pasta / "jogavel.json").is_file() else None
    conf = (antigo or {}).get("confirmacao")
    c("confirmacao_pessoa", conf is not None, f"confirmado em {conf['em']}: {conf['nota']}" if conf else "a pessoa ainda nao confirmou depois de jogar (cew jogavel confirmar)")
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "avaliado_em": agora_iso(),
           "escopo": dec["descricao"] if dec else None, "jogavel": all(x["aprovado"] for x in crit), "marco_atingido": (rel or {}).get("marco_atingido"),
           "criterios": crit, "confirmacao": conf}
    if gravar:
        gravar_json(pasta / "jogavel.json", doc, "jogavel")
    return doc


def confirmar(projeto: Projeto, nota: str, interativo: bool) -> dict:
    """So a pessoa confirma: exige terminal interativo (um agente nao deve confirmar por ela)."""
    if not interativo:
        raise PermissionError("a confirmacao de 'jogavel' e da pessoa: rode 'cew jogavel confirmar' num terminal interativo, depois de jogar")
    atual = avaliar(projeto, gravar=False)
    faltas = [x["id"] for x in atual["criterios"] if not x["aprovado"] and x["id"] != "confirmacao_pessoa"]
    if faltas:
        raise ValueError(f"criterios ainda reprovados: {faltas}; confirme depois de resolve-los")
    conf = {"em": agora_iso(), "nota": nota, "como": "terminal_interativo"}
    atual["confirmacao"] = conf
    gravar_json(projeto.pasta / "jogavel.json", atual, "jogavel")
    st = projeto.estado()
    st["historico"].append({"ts": conf["em"], "etapa": "pronto", "evento": f"pessoa confirmou que esta jogavel: {nota}"})
    projeto.gravar("estado", st)
    return avaliar(projeto)
