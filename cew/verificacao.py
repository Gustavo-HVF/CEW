"""Etapa Verificar (cew check), item 8. Grava relatorio_verificacao.json com "aprovado" por item.

Itens obrigatorios: esquemas, determinismo dos conversores, modelos (glTF Validator), texturas,
audio, build web e testes de navegador; comparacao com capturas do original so e obrigatoria
quando a pessoa fornece referencias/<cena>.png. A visao do Gemini e apenas segunda opiniao
(nunca obrigatoria) e so roda com --gemini.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from converters.comum.audio import ler_wav
from converters.comum.gltf import ler_glb
from converters.comum.imagem import comparar, ler_png, redimensionar, reduzir

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import raiz_repositorio
from .conversores import rodar
from .esquemas import erros as erros_esquema
from .logs import Log, agora_iso
from .projeto import ARQUIVOS, Projeto, validar_craft_json

LIMIAR_SSIM_TEXTURA = 0.98
LIMIAR_SSIM_CENA = 0.60


class Relatorio:
    def __init__(self) -> None:
        self.itens: list[dict[str, Any]] = []
        self.marco_atingido: str | None = None

    def add(self, id_: str, categoria: str, alvo: str, aprovado: bool, detalhes: str, obrigatorio: bool = True, metricas: dict | None = None, pulado: bool = False) -> None:
        item: dict[str, Any] = {"id": id_, "categoria": categoria, "alvo": alvo, "obrigatorio": obrigatorio, "aprovado": bool(aprovado), "detalhes": detalhes}
        if metricas:
            item["metricas"] = metricas
        if pulado:
            item["pulado"] = True
        self.itens.append(item)


def _esquema_dados(doc: Any) -> str | None:
    if not isinstance(doc, dict) or doc.get("gerado_por") != "cew":
        return None
    if "linhas" in doc:
        return "dados/dialogos"
    if "fases" in doc:
        return "dados/fases"
    if "valores" in doc:
        return "dados/configuracoes"
    return None


def verificar_esquemas(p: Projeto, r: Relatorio) -> None:
    for chave, (rel, esquema) in ARQUIVOS.items():
        arq = p.pasta / rel
        if not arq.is_file():
            if chave in ("estado", "inventario", "plano", "manifesto"):
                r.add(f"esquema:{rel}", "esquema", rel, False, "arquivo obrigatorio ausente")
            continue
        e = erros_esquema(json.loads(arq.read_text(encoding="utf-8")), esquema)
        r.add(f"esquema:{rel}", "esquema", rel, not e, "valido" if not e else "; ".join(e[:3]))
    for rel, esq in (("cew.json", "cew_projeto"),):
        e = erros_esquema(json.loads((p.pasta / rel).read_text(encoding="utf-8")), esq)
        r.add(f"esquema:{rel}", "esquema", rel, not e, "valido" if not e else "; ".join(e[:3]))
    try:
        validar_craft_json(json.loads((p.pasta / "craft.json").read_text(encoding="utf-8")))
        r.add("esquema:craft.json", "esquema", "craft.json", True, "valido para docs/schemas/craft.schema.json do Craft Anything")
    except (ValueError, OSError) as e:
        r.add("esquema:craft.json", "esquema", "craft.json", False, str(e))
    node, ajv = shutil.which("node"), raiz_repositorio() / "node_modules" / "ajv"
    if node and ajv.is_dir():
        for chave in ("manifesto", "inventario", "plano"):
            rel, esq = ARQUIVOS[chave]
            if (p.pasta / rel).is_file():
                pr = subprocess.run([node, str(raiz_repositorio() / "tests" / "js" / "validar_esquemas.mjs"), str(p.pasta / rel), esq],
                                    capture_output=True, text=True, timeout=300, cwd=raiz_repositorio())
                r.add(f"ajv:{rel}", "esquema", rel, pr.returncode == 0, "valido tambem no ajv (Node)" if pr.returncode == 0 else pr.stderr[-400:])
    for arq in sorted(p.caminho("tarefas_gemini").glob("*.json")):
        esq = "gemini/tarefa_formato" if arq.name.endswith(".tarefa.json") else "gemini/resposta_formato"
        e = erros_esquema(json.loads(arq.read_text(encoding="utf-8")), esq)
        r.add(f"esquema:{arq.name}", "esquema", f"tarefas_gemini/{arq.name}", not e, "valido" if not e else "; ".join(e[:3]))
    for arq in sorted(p.caminho("dados").rglob("*.json")):
        doc = json.loads(arq.read_text(encoding="utf-8"))
        esq = _esquema_dados(doc)
        if esq:
            e = erros_esquema(doc, esq)
            r.add(f"esquema:{arq.name}", "esquema", arq.relative_to(p.pasta).as_posix(), not e, "valido" if not e else "; ".join(e[:3]))


def verificar_determinismo(p: Projeto, r: Relatorio, limite: int = 200) -> None:
    """Roda de novo cada conversor e compara o SHA-256 das saidas com o que foi publicado."""
    plano = p.ler("plano")
    inv = {i["id"]: i for i in p.ler("inventario")["itens"]}
    alvo = Path(p.ler("inventario")["alvo"]["caminho"])
    feitos = 0
    for item in plano["itens"]:
        if item["estado"] != "concluido" or not item.get("conversor") or not item.get("saidas") or feitos >= limite:
            continue
        it = inv[item["item_inventario"]]
        entrada = (alvo if alvo.is_file() else alvo / it["caminho_no_disco"]) if it["origem"] == "alvo" else p.pasta / it["caminho_no_disco"]
        with tempfile.TemporaryDirectory(prefix="cew-det-") as tmp:
            res = rodar(item["conversor"], entrada, Path(tmp), item.get("opcoes") or {}, projeto_pasta=p.pasta)
            novos = {s["caminho"]: s["sha256"] for s in res["saidas"]}
        prefixo = f"build/convertido/{item['id']}/"
        difs = []
        for s in item["saidas"]:
            rel = s[len(prefixo):]
            if rel.startswith("cadeia/"):
                continue  # saidas encadeadas sao conferidas pela saida intermediaria
            antigo = hashlib.sha256((p.pasta / s).read_bytes()).hexdigest() if (p.pasta / s).is_file() else None
            if novos.get(rel) != antigo:
                difs.append(rel)
        r.add(f"determinismo:{item['id']}", "determinismo", item.get("caminho", item["id"]), res["ok"] and not difs,
              "mesmo SHA-256 nas saidas" if res["ok"] and not difs else f"saidas diferentes: {difs or res['erro']}")
        feitos += 1


def verificar_assets(p: Projeto, r: Relatorio) -> None:
    man = p.ler("manifesto")
    web = p.caminho("web")
    glbs = [a for a in man["assets"] if a["caminho_web"].endswith(".glb")]
    if glbs:
        node = shutil.which("node")
        val = raiz_repositorio() / "node_modules" / "gltf-validator"
        if not node or not val.is_dir():
            for a in glbs:
                r.add(f"modelo:{a['id']}", "modelo", a["caminho_web"], False, "glTF Validator indisponivel: rode 'npm install' na raiz do CEW")
        else:
            proc = subprocess.run([node, str(raiz_repositorio() / "tests" / "js" / "validar_gltf.mjs"), *[str(web / a["caminho_web"]) for a in glbs]],
                                  capture_output=True, text=True, timeout=600, cwd=raiz_repositorio())
            try:
                res = {Path(x["arquivo"]).name: x for x in json.loads(proc.stdout)["resultados"]}
            except (ValueError, KeyError):
                res = {}
            for a in glbs:
                x = res.get(Path(a["caminho_web"]).name)
                if x is None:
                    r.add(f"modelo:{a['id']}", "modelo", a["caminho_web"], False, f"validador nao respondeu: {proc.stderr[-300:]}")
                    continue
                doc, _ = ler_glb((web / a["caminho_web"]).read_bytes())
                verts = sum(doc["accessors"][pr["attributes"]["POSITION"]]["count"] for m in doc.get("meshes", []) for pr in m["primitives"])
                esperado = a["metadados"].get("vertices")
                ok = x["erros"] == 0 and (esperado is None or esperado == verts)
                r.add(f"modelo:{a['id']}", "modelo", a["caminho_web"], ok,
                      f"glTF Validator {x['versao_validador']}: {x['erros']} erros, {x['avisos']} avisos; vertices {verts} (esperado {esperado})",
                      metricas={"erros": x["erros"], "avisos": x["avisos"], "vertices": verts, "ossos": len(doc.get("skins", []))})
    pasta_ref = p.caminho("referencias") / "texturas"
    for a in man["assets"]:
        arq = web / a["caminho_web"]
        if a["caminho_web"].endswith(".png"):
            try:
                img = ler_png(arq.read_bytes())
            except Exception as e:  # noqa: BLE001
                r.add(f"textura:{a['id']}", "textura", a["caminho_web"], False, f"PNG ilegivel: {e}")
                continue
            m = a["metadados"]
            ok = img.largura == m.get("largura_px", img.largura) and img.altura == m.get("altura_px", img.altura) and img.tem_alfa == m.get("tem_alfa", img.tem_alfa)
            r.add(f"textura:{a['id']}", "textura", a["caminho_web"], ok, f"{img.largura}x{img.altura}, alfa={img.tem_alfa} (manifesto {m.get('largura_px')}x{m.get('altura_px')}, alfa={m.get('tem_alfa')})")
            ref = pasta_ref / Path(a["caminho_web"]).name
            if ref.is_file():
                c = comparar(img, ler_png(ref.read_bytes()))
                r.add(f"textura_ref:{a['id']}", "textura", a["caminho_web"], c["mesmo_tamanho"] and c["ssim"] >= LIMIAR_SSIM_TEXTURA,
                      f"SSIM {c['ssim']:.4f} contra a decodificacao de referencia (limiar {LIMIAR_SSIM_TEXTURA})", metricas=c)
        elif a["caminho_web"].endswith(".wav"):
            pcm = ler_wav(arq.read_bytes())
            m = a["metadados"]
            loop_ok = m.get("loop") is None or (pcm.loop is not None and [pcm.loop[0], pcm.loop[1]] == [m["loop"]["inicio_amostra"], m["loop"]["fim_amostra"]] and pcm.loop[1] <= pcm.quantidade)
            ok = pcm.taxa_hz == m.get("taxa_amostragem_hz", pcm.taxa_hz) and abs(pcm.duracao_s - m.get("duracao_s", pcm.duracao_s)) < 0.01 and loop_ok
            r.add(f"audio:{a['id']}", "audio", a["caminho_web"], ok, f"{pcm.taxa_hz} Hz, {pcm.duracao_s:.3f} s, loop {pcm.loop} (manifesto {m.get('loop')})")
        elif a["caminho_web"].endswith(".ogg"):
            ffprobe = shutil.which("ffprobe")
            m = a["metadados"]
            if not ffprobe:
                r.add(f"audio:{a['id']}", "audio", a["caminho_web"], False, "ffprobe indisponivel para conferir o OGG")
                continue
            pr = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=sample_rate,channels,duration", "-of", "json", str(arq)], capture_output=True, text=True, timeout=120)
            st = (json.loads(pr.stdout or "{}").get("streams") or [{}])[0]
            dur = float(st.get("duration", 0) or 0)
            loop = m.get("loop")
            ok = abs(dur - m.get("duracao_s", dur)) < 0.05 and (loop is None or loop["fim_amostra"] <= m.get("amostras", loop["fim_amostra"]))
            r.add(f"audio:{a['id']}", "audio", a["caminho_web"], ok, f"ffprobe: {st.get('sample_rate')} Hz, {st.get('channels')} canais, {dur:.3f} s (manifesto {m.get('duracao_s')} s, loop {loop})")


def verificar_cenas(p: Projeto, r: Relatorio) -> None:
    """Cada cena publicada: esquema, links de asset validos, ids unicos e posicoes finitas."""
    import math

    from .cenas import cenas_publicadas

    ids_manifesto = {a["id"] for a in p.ler("manifesto")["assets"]} if p.existe("manifesto") else set()
    for a, cena in cenas_publicadas(p):
        problemas = erros_esquema(cena, "dados/cena")
        if cena.get("estado") != "normalizada":
            problemas.append("cena publicada sem normalizar")
        ents = cena.get("entidades", [])
        ids = [e["id"] for e in ents]
        if len(ids) != len(set(ids)):
            problemas.append("ids de entidade repetidos")
        quebrados = sorted({e["asset_id"] for e in ents if e.get("asset_id") and e["asset_id"] not in ids_manifesto})
        if quebrados:
            problemas.append(f"assets inexistentes no manifesto: {quebrados[:5]}")
        if cena.get("geometria_asset_id") and cena["geometria_asset_id"] not in ids_manifesto:
            problemas.append("geometria_asset_id fora do manifesto")
        if any(not all(math.isfinite(c) for c in e["posicao"]) for e in ents):
            problemas.append("posicao nao finita")
        est = cena.get("estatisticas", {})
        if est.get("entidades") != len(ents):
            problemas.append("estatisticas.entidades nao confere com a lista")
        cats = ", ".join(f"{k} {v}" for k, v in est.get("por_categoria", {}).items())
        r.add(f"cena:{cena['id_cena']}", "cena", a["caminho_web"], not problemas,
              "; ".join(problemas[:4]) if problemas else f"{len(ents)} elementos ({cats}); {est.get('sem_asset', 0)} sem asset (placeholder no jogo); "
              f"{sum(1 for e in ents if e.get('ajustado'))} ajustados; {sum(1 for e in ents if e.get('posicao_estimada'))} com posicao estimada",
              metricas={"entidades": len(ents), "sem_asset": est.get("sem_asset", 0), "removidas_por_regra": est.get("removidas_por_regra", 0)})


def verificar_traducao(p: Projeto, r: Relatorio) -> None:
    """Plano de traducao valido; casos de equivalencia rodados de novo (obrigatorios onde existem)."""
    arq = p.pasta / "codigo" / "plano_traducao.json"
    if not arq.is_file():
        return
    from . import codigo

    e = erros_esquema(json.loads(arq.read_text(encoding="utf-8")), "plano_traducao")
    r.add("esquema:codigo/plano_traducao.json", "esquema", "codigo/plano_traducao.json", not e, "valido" if not e else "; ".join(e[:3]))
    if e:
        return
    for res in codigo.testar(p):
        r.add(f"traducao:{res['nome']}", "traducao", res["nome"], res["aprovado"], res["detalhes"], obrigatorio=not res.get("manual"),
              metricas={"casos": res.get("casos", 0), "aprovados": res.get("aprovados", 0)})
    pl = codigo.ler_plano(p)
    vivas = [u for u in pl["unidades"] if u["estado"] != "descartada"]
    alta = [u for u in vivas if u["prioridade"] == "alta"]
    feitas = [u for u in alta if u["estado"] in ("traduzida", "testada")]
    r.add("traducao:cobertura", "traducao", "codigo/plano_traducao.json", True,
          f"{len(feitas)}/{len(alta)} unidades de prioridade alta traduzidas ({sum(1 for u in alta if u['estado'] == 'testada')} testadas); "
          f"{len(vivas)} unidades no total, {pl['resumo'].get('descartada', 0)} descartadas (runtime)", obrigatorio=False,
          metricas={"alta": len(alta), "alta_traduzidas": len(feitas), "total": len(vivas)})


def _npm(app: Path, args: list[str], tempo: int = 900) -> subprocess.CompletedProcess:
    npx = shutil.which("npm")
    if not npx:
        raise FileNotFoundError("npm nao encontrado")
    return subprocess.run([npx, *args], cwd=app, capture_output=True, text=True, timeout=tempo)


def verificar_web(p: Projeto, r: Relatorio, instalar: bool = False, chromium: str | None = None) -> None:
    app = p.pasta / "app"
    if not (app / "package.json").is_file():
        r.add("build_web", "build_web", "app/", False, "projeto web ainda nao gerado (etapa reconstrucao)")
        return
    if not (app / "node_modules").is_dir():
        if not instalar:
            r.add("build_web", "build_web", "app/", False, "dependencias nao instaladas: rode 'npm install' em app/ (ou cew check --instalar-dependencias)")
            return
        pr = _npm(app, ["install", "--no-audit", "--no-fund"])
        if pr.returncode != 0:
            r.add("build_web", "build_web", "app/", False, f"npm install falhou: {pr.stderr[-500:]}")
            return
    pr = _npm(app, ["run", "build"])
    r.add("build_web", "build_web", "app/", pr.returncode == 0, "build sem erros" if pr.returncode == 0 else f"build falhou: {(pr.stderr or pr.stdout)[-800:]}")
    if pr.returncode != 0:
        return
    import os

    env = dict(os.environ)
    if chromium:
        env["CEW_CHROMIUM"] = chromium
    npx = shutil.which("npx") or "npx"
    shutil.rmtree(p.pasta / "checks" / "assets_carregados", ignore_errors=True)
    pw = subprocess.run([npx, "playwright", "test", "--trace", "off", "--reporter=json"], cwd=app, capture_output=True, text=True, timeout=1800, env=env)
    try:
        rep = json.loads(pw.stdout)
    except ValueError:
        r.add("navegador", "navegador", "app/tests", False, f"playwright nao rodou: {(pw.stderr or pw.stdout)[-600:]} (instale com 'npx playwright install chromium')")
        return
    specs = list(_specs(rep))
    marcos_res: dict[str, dict] = {}
    for arquivo, s in specs:
        estados = [res.get("status") for t in s.get("tests", []) for res in t.get("results", [])] or [t.get("status") for t in s.get("tests", [])]
        pendente = any(t.get("status") == "skipped" or t.get("expectedStatus") == "skipped" for t in s.get("tests", [])) or not estados
        ok = bool(s.get("ok")) and not pendente and all(e in ("passed", "expected") for e in estados)
        erro = next((re.sub(r"\x1b\[[0-9;]*m", "", res["error"].get("message", ""))[:600] for t in s.get("tests", []) for res in t.get("results", []) if res.get("error")), "")
        f = arquivo.replace("\\", "/")
        rel = "tests/" + (f.split("tests/")[-1] if "tests/" in f else f.lstrip("./"))  # o reporter usa caminho relativo ao testDir
        if rel.startswith("tests/marcos/"):
            atual = marcos_res.get(rel, {"aprovado": True, "pendente": False, "detalhes": ""})
            atual["aprovado"] = atual["aprovado"] and ok
            atual["pendente"] = atual["pendente"] or pendente
            atual["detalhes"] = "pendente (test.fixme)" if atual["pendente"] else ("aprovado" if atual["aprovado"] else erro or "falhou")
            marcos_res[rel] = atual
        else:
            r.add(f"navegador:{s['title']}", "navegador", s["title"], ok, "abriu sem erros no console" if ok else erro or ("pendente" if pendente else "falhou"))
    if not specs:
        r.add("navegador", "navegador", "app/tests", False, "nenhum teste de navegador encontrado")
    from . import marcos as _marcos

    doc, atingido = _marcos.atualizar(p, marcos_res)
    r.marco_atingido = atingido
    for m in (doc or {}).get("marcos", []):
        r.add(f"marco:{m['id']}", "marco", m["titulo"], m["estado"] == "aprovado", f"{m['criterio']} -> {m.get('detalhes', '')}", obrigatorio=m["obrigatorio"])
    cobertura(p, r)


def _specs(no: dict, arquivo: str = ""):
    for suite in no.get("suites", []):
        arq = suite.get("file") or arquivo
        for s in suite.get("specs", []):
            yield s.get("file") or arq, s
        yield from _specs(suite, arq)


def cobertura(p: Projeto, r: Relatorio) -> dict | None:
    """Assets do manifesto que o app requisitou nos testes (checks/assets_carregados/*.json)."""
    from .esquemas import gravar_json as _gravar

    pasta = p.pasta / "checks" / "assets_carregados"
    if not p.existe("manifesto") or not pasta.is_dir():
        return None
    usados, cenas = set(), []
    for arq in sorted(pasta.glob("*.json")):
        d = json.loads(arq.read_text(encoding="utf-8"))
        cenas.append(d.get("nome", arq.stem))
        usados |= set(d.get("assets", []))
    man = p.ler("manifesto")["assets"]
    por_tipo: dict[str, dict] = {}
    nao = []
    for a in man:
        t = por_tipo.setdefault(a["tipo"], {"total": 0, "usados": 0})
        t["total"] += 1
        if a["caminho_web"] in usados:
            t["usados"] += 1
        else:
            nao.append({"id": a["id"], "caminho_web": a["caminho_web"], "tipo": a["tipo"]})
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": p.nome, "gerado_em": agora_iso(), "total": len(man),
           "usados": len(man) - len(nao), "por_tipo": dict(sorted(por_tipo.items())), "nao_usados": nao, "cenas": cenas}
    _gravar(p.pasta / "cobertura_conteudo.json", doc, "cobertura_conteudo")
    pct = 100 * doc["usados"] / doc["total"] if doc["total"] else 100.0
    r.add("cobertura", "cobertura", "cobertura_conteudo.json", True, f"{doc['usados']}/{doc['total']} assets do manifesto usados nos testes ({pct:.0f}%)",
          obrigatorio=False, metricas={"usados": doc["usados"], "total": doc["total"]})
    return doc


def verificar_capturas(p: Projeto, r: Relatorio, gemini: bool = False) -> None:
    refs = sorted(p.caminho("referencias").glob("*.png"))
    capt = p.pasta / "checks" / "capturas"
    for ref in refs:
        cap = capt / ref.name
        if not cap.is_file():
            r.add(f"comparacao:{ref.stem}", "comparacao_visual", ref.name, False, "captura da versao web ausente (rode os testes de navegador)")
            continue
        a = reduzir(ler_png(ref.read_bytes()), 256)
        b = ler_png(cap.read_bytes())
        b = redimensionar(b, a.largura, a.altura)
        c = comparar(a, b)
        r.add(f"comparacao:{ref.stem}", "comparacao_visual", ref.name, c["ssim"] >= LIMIAR_SSIM_CENA,
              f"SSIM {c['ssim']:.3f} (limiar {LIMIAR_SSIM_CENA}), diferenca media {c['diferenca_media']:.3f}", metricas=c)
        if gemini:
            _segunda_opiniao(p, r, ref, cap, c)


def _segunda_opiniao(p: Projeto, r: Relatorio, ref: Path, cap: Path, metricas: dict) -> None:
    from .gemini import ClienteGemini, ErroGemini, Parte
    from .esquemas import validar

    tarefa = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "tarefa": "comparacao_visual", "id": f"cv_{ref.stem}", "cena": ref.stem,
              "imagem_original": {"caminho": f"referencias/{ref.name}", "sha256": hashlib.sha256(ref.read_bytes()).hexdigest()},
              "imagem_web": {"caminho": f"checks/capturas/{cap.name}", "sha256": hashlib.sha256(cap.read_bytes()).hexdigest()},
              "metricas": {"ssim": metricas["ssim"], "diferenca_media": metricas["diferenca_media"]}}
    validar(tarefa, "gemini/tarefa_comparacao_visual")
    try:
        resp = ClienteGemini().gerar("comparacao_visual", [
            Parte(texto="Compare a primeira imagem (jogo original) com a segunda (versao web). Tarefa: " + json.dumps(tarefa, ensure_ascii=False)),
            Parte(mime="image/png", dados=ref.read_bytes()), Parte(mime="image/png", dados=cap.read_bytes())], "gemini/resposta_comparacao_visual")
        (p.pasta / "checks" / f"gemini_{ref.stem}.json").write_text(json.dumps(resp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        r.add(f"gemini:{ref.stem}", "segunda_opiniao_gemini", ref.name, bool(resp["parecido"]), f"nota {resp['nota_similaridade']:.2f}; {len(resp['diferencas'])} diferencas", obrigatorio=False)
    except ErroGemini as e:
        r.add(f"gemini:{ref.stem}", "segunda_opiniao_gemini", ref.name, False, str(e), obrigatorio=False)


def executar(p: Projeto, web: bool = True, instalar: bool = False, gemini: bool = False, chromium: str | None = None, dry_run: bool = False, log: Log | None = None) -> dict:
    log = log or Log("verificacao")
    r = Relatorio()
    verificar_esquemas(p, r)
    if p.existe("plano") and p.existe("inventario"):
        verificar_determinismo(p, r)
    if p.existe("manifesto"):
        verificar_assets(p, r)
        verificar_cenas(p, r)
    verificar_traducao(p, r)
    if web:
        verificar_web(p, r, instalar, chromium)
        verificar_capturas(p, r, gemini)
    obrig = [i for i in r.itens if i["obrigatorio"]]
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": p.nome, "gerado_em": agora_iso(),
           "aprovado": bool(obrig) and all(i["aprovado"] for i in obrig), "marco_atingido": r.marco_atingido,
           "resumo": dict(Counter(("aprovado" if i["aprovado"] else "reprovado") + ("_obrigatorio" if i["obrigatorio"] else "_opcional") for i in r.itens)),
           "itens": r.itens}
    if not dry_run:
        p.gravar("verificacao", doc)
    for i in r.itens:
        if i["obrigatorio"] and not i["aprovado"]:
            log.aviso(f"{i['id']}: {i['detalhes']}", etapa="verificacao")
    return doc
