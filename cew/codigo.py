"""Descompilacao do codigo do jogo (Craft Anything) e traducao para a linguagem do motor escolhido.

O Craft Anything DESCOMPILA (nao traduz entre linguagens):
- nativo (ELF, PE, Mach-O, ROMs): `native-source-folder-write` -> um arquivo .c de pseudo-C por funcao
  e o estado `craft-pseudocode-export.json` (motor: lifter proprio, ou Ghidra no modo Deep quando
  configurado). Sem o Craft Anything, usa a exportacao do Ghidra feita pelo CEW (analise/*.json);
- .NET (Mono/Unity/XNA/FNA): `managed-ilspy-decompile` (ilspycmd) -> C#, tipo a tipo (list_types);
- Java/JAR: `java-vineflower-decompile` -> Java;
- JavaScript empacotado (Electron, web): `js-sources-restore` -> modulos legiveis;
- Python compilado: `formats-bytecode-show` (estrutura e instrucoes, nao fonte);
- scripts em texto (Lua, GDScript, Python, JS sem empacotar): copiados como estao.
Saida: projects/<p>/codigo/original/<programa>/ + indice.json (schemas/codigo_original.schema.json).

A TRADUCAO e trabalho da IA principal, uma unidade (funcao/tipo/modulo) por vez: o CEW monta o
plano (codigo/plano_traducao.json), descarta runtime/biblioteca, ordena pelo que o jogo alcanca a
partir das entradas (main, Update...), entrega um pacote de contexto por unidade com as equivalencias
de API para o motor, opcionalmente um rascunho do Gemini, e roda testes de equivalencia
(codigo/testes/<unidade>.json) contra o codigo traduzido.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Any

from . import GERADO_POR, SCHEMA_VERSION, craft
from .caminhos import id_estavel, raiz_repositorio, slug
from .esquemas import gravar_json, ler_json, validar
from .logs import Log, agora_iso
from .projeto import Projeto

MOTOR_LINGUAGEM = {"threejs": "javascript", "babylonjs": "javascript", "phaser": "javascript", "pixijs": "javascript", "playcanvas": "javascript",
                   "godot": "gdscript", "unity_webgl": "csharp", "construct3": "eventos", "gdevelop": "eventos"}
EXTENSAO = {"javascript": ".js", "typescript": ".ts", "gdscript": ".gd", "csharp": ".cs", "eventos": ".md"}
PASTA_DESTINO = {"javascript": "app/src/logica", "typescript": "app/src/logica", "gdscript": "app/scripts/logica", "csharp": "app/Assets/Scripts/Logica", "eventos": "codigo/eventos"}
EXT_FONTE = {".lua": "lua", ".gd": "gdscript", ".py": "python", ".cs": "csharp", ".java": "java", ".js": "javascript", ".mjs": "javascript", ".ts": "typescript", ".hx": "haxe", ".rb": "ruby"}
ENTRADAS = {"main", "_main", "winmain", "wwinmain", "sdl_main", "update", "draw", "initialize", "loadcontent", "start", "awake", "fixedupdate", "tick", "game_loop", "gameloop", "frame", "run"}
RUNTIME = {"_init", "_fini", "_start", "start", "frame_dummy", "register_tm_clones", "deregister_tm_clones", "__do_global_dtors_aux", "do_global_dtors_aux",
           "__libc_csu_init", "__libc_csu_fini", "_dl_relocate_static_pie", "__cxa_finalize", "__stack_chk_fail", "mainCRTStartup", "WinMainCRTStartup",
           "__security_init_cookie", "__security_check_cookie", "_initterm", "_initterm_e", "pre_c_init", "pre_cpp_init", "__tmainCRTStartup"}
PAPEIS = [
    ("entrada", ("input", "key", "mouse", "joy", "pad", "button", "pollevent", "getkeyboard", "getasynckeystate", "touch")),
    ("audio", ("sound", "audio", "music", "mix_", "wave", "sfx", "xaudio", "openal", "playsound")),
    ("renderizacao", ("draw", "render", "sprite", "blit", "texture", "shader", "glbind", "gldraw", "d3d", "present", "paint", "camera")),
    ("fisica", ("physics", "collid", "collision", "velocity", "gravity", "rigidbody", "raycast", "friction", "move")),
    ("ia", ("ai_", "_ai", "enemy", "monster", "think", "behav", "pathfind", "path", "npc", "target")),
    ("salvamento", ("save", "fwrite", "savegame", "persist", "prefs")),
    ("carregador", ("load", "fread", "fopen", "parse", "readfile", "decompress", "inflate", "unpack", "content")),
    ("rede", ("socket", "send", "recv", "network", "net_", "connect")),
    ("interface", ("menu", "hud", "gui", "ui_", "dialog", "text", "font", "button")),
    ("plataforma", ("window", "createwindow", "sdl_init", "thread", "mutex", "registry", "init_video", "device")),
]


def linguagem_do_motor(motor: str | None) -> str:
    return MOTOR_LINGUAGEM.get(motor or "", "javascript")


def _sha(dados: bytes) -> str:
    return hashlib.sha256(dados).hexdigest()


def _disco(projeto: Projeto, item: dict, inv: dict) -> Path:
    if item["origem"] == "alvo":
        base = Path(inv["alvo"]["caminho"])
        return base if base.is_file() else base / item["caminho_no_disco"]
    return projeto.pasta / item["caminho_no_disco"]


# ------------------------------------------------------------------------------- deteccao
def detectar_programas(projeto: Projeto, inv: dict) -> list[dict]:
    """Itens do inventario com codigo: (item, tipo_codigo, linguagem_origem)."""
    from .registro import registro_do_projeto

    reg = registro_do_projeto(projeto.pasta)
    saida = []
    for it in inv["itens"]:
        fid = it["formato"]["id"] or ""
        tipo = (reg.get(fid) or {}).get("tipo")
        ext = PurePosixPath(it["caminho"].split("!/")[-1]).suffix.lower()
        disco = _disco(projeto, it, inv)
        if not disco.is_file():
            continue
        if fid == "microsoft.pe":
            with open(disco, "rb") as f:
                cab = f.read(8 * 1024 * 1024)
            # cabecalho de metadados da CLI ("BSJB") => assembly .NET
            saida.append((it, "dotnet", "csharp") if b"BSJB" in cab else (it, "nativo", "pseudo_c"))
        elif tipo == "codigo" and fid in ("oracle.java.class",):
            saida.append((it, "java", "java"))
        elif tipo == "codigo" and fid not in ("w3c.wasm",):
            saida.append((it, "nativo", "pseudo_c"))
        elif fid == "generico.zip" and ext == ".jar":
            saida.append((it, "java", "java"))
        elif ext == ".pyc":
            saida.append((it, "python_bytecode", "python_bytecode"))
        elif ext in (".js", ".mjs") and it["tamanho_bytes"] > 0:
            saida.append((it, "javascript", "javascript"))
        elif ext in EXT_FONTE and it["tamanho_bytes"] < 8 * 1024 * 1024:
            saida.append((it, "fonte", EXT_FONTE[ext]))
    return [{"item": i, "tipo_codigo": t, "linguagem_origem": l} for i, t, l in saida]


# --------------------------------------------------------------------------- descompilar
def _id_programa(item: dict) -> str:
    return f"{slug(PurePosixPath(item['caminho'].split('!/')[-1]).stem)}-{item['id'][2:8]}"


def _unidades_da_pasta(pasta: Path, projeto: Projeto, padrao: str = "*") -> list[dict]:
    us = []
    for arq in sorted(pasta.rglob(padrao)):
        if arq.is_file() and not arq.name.startswith("craft-") and arq.name != "indice.json":
            texto = arq.read_bytes()
            us.append({"nome": arq.stem, "endereco": None, "arquivo": arq.relative_to(projeto.pasta).as_posix(),
                       "linhas": texto.count(b"\n"), "sha256": _sha(texto), "estruturado": None})
    return us


def _nativo_craft(projeto: Projeto, disco: Path, pasta: Path, log: Log) -> tuple[dict, list[dict], str]:
    ultimo: dict = {}
    for _ in range(50):  # o tool continua de onde parou a cada chamada
        r = craft.rodar(["native-source-folder-write", str(disco), "--folder", str(pasta.resolve()), "--max-functions", "5000", "--max-seconds", "300"],
                        projeto_cany=projeto.pasta / "investigation.cany", deep=True, tempo_s=900)
        ultimo = r.get("result", {}) if isinstance(r, dict) else {}
        if ultimo.get("finished") or not ultimo.get("functions_done"):
            break
    estado_arq = pasta / ultimo.get("state_file", "craft-pseudocode-export.json")
    estado = json.loads(estado_arq.read_text(encoding="utf-8")) if estado_arq.is_file() else {"functions": {}}
    us = []
    for end, f in sorted(estado.get("functions", {}).items(), key=lambda kv: int(kv[0], 16) if kv[0].startswith("0x") else 0):
        arq = pasta / f["file"]
        if not arq.is_file():
            continue
        dados = arq.read_bytes()
        us.append({"nome": f.get("name") or arq.stem, "endereco": end, "arquivo": arq.relative_to(projeto.pasta).as_posix(),
                   "linhas": int(f.get("lines", dados.count(b"\n"))), "sha256": _sha(dados), "estruturado": f.get("structured")})
    ferramenta = {"nome": "Craft Anything", "versao": craft.versao(), "operacao": "native_source_folder_write", "motor": estado.get("engine"), "evidencia_id": (r or {}).get("id") if isinstance(r, dict) else None}
    return ferramenta, us, "completo" if ultimo.get("finished") else "parcial"


def _nativo_ghidra(projeto: Projeto, item: dict, pasta: Path) -> tuple[dict, list[dict], str] | None:
    """Sem o Craft Anything: reaproveita a exportacao do Ghidra (scripts/ghidra/ExportarCEW.java)."""
    for arq in sorted(projeto.caminho("analise").glob("*.json")):
        try:
            a = ler_json(arq, "analise_programa")
        except Exception:  # noqa: BLE001
            continue
        if a["programa"].get("sha256") != item["sha256"]:
            continue
        pasta.mkdir(parents=True, exist_ok=True)
        us = []
        for f in a["funcoes"]:
            if not f.get("pseudo_c"):
                continue
            nome_arq = f"{f['endereco'].removeprefix('0x').zfill(16)}_{re.sub(r'[^A-Za-z0-9_]', '_', f['nome'])[:60]}.c"
            texto = f"// {f['nome']} em {f['endereco']}, de {a['programa']['nome']}. Pseudo-C do Ghidra {a['ferramenta']['versao']}.\n{f['pseudo_c']}"
            (pasta / nome_arq).write_text(texto, encoding="utf-8")
            us.append({"nome": f["nome"], "endereco": f["endereco"], "arquivo": (pasta / nome_arq).relative_to(projeto.pasta).as_posix(),
                       "linhas": texto.count("\n"), "sha256": _sha(texto.encode()), "estruturado": True})
        return {"nome": "Ghidra (ExportarCEW)", "versao": a["ferramenta"]["versao"], "operacao": "analyzeHeadless + ExportarCEW.java", "motor": "ghidra", "evidencia_id": None}, us, "completo"
    return None


def _paginar_texto(args_base: list[str], projeto: Projeto, campo: str = "output", limite: int = 20000) -> str:
    partes, offset = [], 0
    while True:
        r = craft.rodar(args_base + ["--offset", str(offset), "--limit", str(limite)], projeto_cany=projeto.pasta / "investigation.cany", deep=True, tempo_s=900)
        res = r.get("result", {})
        partes.append(res.get(campo) or res.get("source") or "")
        total = int(res.get("total_lines", 0))
        offset += limite
        if offset >= total:
            return "\n".join(partes)


def _dotnet(projeto: Projeto, disco: Path, pasta: Path) -> tuple[dict, list[dict], str]:
    lista = _paginar_texto(["managed-ilspy-decompile", "--path", str(disco.resolve()), "--operation", "list_types"], projeto)
    # "ilspycmd -l cisde" lista um tipo por linha; o formato exato da linha nao foi conferido aqui
    # (ilspycmd ausente no ambiente de construcao): pega o ultimo token que parece nome de tipo.
    tipos = []
    for linha in lista.splitlines():
        tokens = [t.strip(":,") for t in linha.split()]
        nome = next((t for t in reversed(tokens) if re.fullmatch(r"[A-Za-z_][\w.`+<>]*", t) and t not in ("Class", "Interface", "Struct", "Delegate", "Enum")), None)
        if nome:
            tipos.append(nome)
    pasta.mkdir(parents=True, exist_ok=True)
    us = []
    for t in sorted(set(tipos)):
        if t.startswith("<") or "<PrivateImplementationDetails>" in t:
            continue
        try:
            texto = _paginar_texto(["managed-ilspy-decompile", "--path", str(disco.resolve()), "--type-name", t], projeto)
        except craft.ErroCraft:
            continue
        arq = pasta / (re.sub(r"[^A-Za-z0-9_.+-]", "_", t) + ".cs")
        arq.write_text(texto, encoding="utf-8")
        us.append({"nome": t, "endereco": None, "arquivo": arq.relative_to(projeto.pasta).as_posix(), "linhas": texto.count("\n"), "sha256": _sha(texto.encode()), "estruturado": True})
    return {"nome": "Craft Anything", "versao": craft.versao(), "operacao": "managed_ilspy_decompile", "motor": "ilspycmd", "evidencia_id": None}, us, "completo" if us else "falhou"


def _java(projeto: Projeto, disco: Path, pasta: Path) -> tuple[dict, list[dict], str]:
    nomes, offset = [], 0
    while True:
        r = craft.rodar(["java-vineflower-decompile", "--path", str(disco.resolve()), "--offset", str(offset), "--limit", "2000"], projeto_cany=projeto.pasta / "investigation.cany", deep=True, tempo_s=900)
        res = r.get("result", {})
        if res.get("source") and res.get("file") and not res.get("sources"):
            nomes = [(res["file"], res["source"])]
            break
        pagina = res.get("sources") or []
        nomes += [(s["file"], None) for s in pagina]
        offset += len(pagina)
        if not pagina or offset >= int(res.get("files", 0)):
            break
    pasta.mkdir(parents=True, exist_ok=True)
    us = []
    for arquivo, texto in nomes:
        if texto is None:
            classe = re.sub(r"\.java$", "", arquivo)
            texto = _paginar_texto(["java-vineflower-decompile", "--path", str(disco.resolve()), "--class", classe], projeto, campo="source")
        destino = pasta / arquivo
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(texto, encoding="utf-8")
        us.append({"nome": PurePosixPath(arquivo).stem, "endereco": None, "arquivo": destino.relative_to(projeto.pasta).as_posix(), "linhas": texto.count("\n"), "sha256": _sha(texto.encode()), "estruturado": True})
    return {"nome": "Craft Anything", "versao": craft.versao(), "operacao": "java_vineflower_decompile", "motor": "vineflower", "evidencia_id": None}, us, "completo" if us else "falhou"


def _javascript(projeto: Projeto, disco: Path, pasta: Path) -> tuple[dict, list[dict], str]:
    if pasta.exists():
        shutil.rmtree(pasta)
    craft.rodar(["js-sources-restore", "--path", str(disco.resolve()), "--output-directory", str(pasta.resolve())], projeto_cany=projeto.pasta / "investigation.cany", deep=True, tempo_s=900)
    us = _unidades_da_pasta(pasta, projeto)
    us = [u for u in us if u["arquivo"].endswith((".js", ".mjs", ".ts", ".jsx", ".tsx"))]
    return {"nome": "Craft Anything", "versao": craft.versao(), "operacao": "js_sources_restore", "motor": None, "evidencia_id": None}, us, "completo" if us else "falhou"


def _bytecode(projeto: Projeto, disco: Path, pasta: Path) -> tuple[dict, list[dict], str]:
    r = craft.rodar(["formats-bytecode-show", "--path", str(disco.resolve())], projeto_cany=projeto.pasta / "investigation.cany", deep=True, tempo_s=600)
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / (disco.stem + ".bytecode.json")
    texto = json.dumps(r.get("result", r), ensure_ascii=False, indent=2)
    arq.write_text(texto, encoding="utf-8")
    return ({"nome": "Craft Anything", "versao": craft.versao(), "operacao": "formats_bytecode_show", "motor": None, "evidencia_id": r.get("id")},
            [{"nome": disco.stem, "endereco": None, "arquivo": arq.relative_to(projeto.pasta).as_posix(), "linhas": texto.count("\n"), "sha256": _sha(texto.encode()), "estruturado": None}], "parcial")


def descompilar(projeto: Projeto, dry_run: bool = False, limite_programas: int = 10, log: Log | None = None) -> dict:
    log = log or Log("codigo")
    inv = projeto.ler("inventario")
    pasta_base = projeto.pasta / "codigo" / "original"
    antigo = {p["sha256"]: p for p in ler_json(pasta_base / "indice.json", "codigo_original")["programas"]} if (pasta_base / "indice.json").is_file() else {}
    tem_craft = craft.localizar_cli() is not None
    programas = []
    detectados = detectar_programas(projeto, inv)
    for d in detectados[:limite_programas] if limite_programas else detectados:
        it, tipo = d["item"], d["tipo_codigo"]
        pid = _id_programa(it)
        pasta = pasta_base / pid
        base: dict[str, Any] = {"id": pid, "item_inventario": it["id"], "caminho": it["caminho"], "sha256": it["sha256"], "tipo_codigo": tipo,
                                "linguagem_origem": d["linguagem_origem"], "pasta": pasta.relative_to(projeto.pasta).as_posix()}
        velho = antigo.get(it["sha256"])
        if velho and velho["estado"] == "completo" and all((projeto.pasta / u["arquivo"]).is_file() for u in velho["unidades"]):
            programas.append(velho)  # idempotente: mesmo binario, nada a refazer
            continue
        if dry_run:
            log.info(f"[dry-run] descompilaria {it['caminho']} ({tipo})", etapa="engenharia")
            continue
        disco = _disco(projeto, it, inv)
        try:
            if tipo == "fonte":
                pasta.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(disco, pasta / disco.name)
                res = ({"nome": "copia", "versao": None, "operacao": "copiar (ja e codigo-fonte)", "motor": None, "evidencia_id": None}, _unidades_da_pasta(pasta, projeto), "completo")
            elif tipo == "nativo":
                res = _nativo_craft(projeto, disco, pasta, log) if tem_craft else None
                if res is None or not res[1]:
                    res = _nativo_ghidra(projeto, it, pasta) or res
            elif not tem_craft:
                res = None
            elif tipo == "dotnet":
                res = _dotnet(projeto, disco, pasta)
            elif tipo == "java":
                res = _java(projeto, disco, pasta)
            elif tipo == "javascript":
                res = _javascript(projeto, disco, pasta)
            elif tipo == "python_bytecode":
                res = _bytecode(projeto, disco, pasta)
            else:
                res = None
            if res is None:
                programas.append({**base, "ferramenta": {"nome": "Craft Anything", "versao": None, "operacao": "-", "motor": None, "evidencia_id": None},
                                  "estado": "indisponivel", "mensagem": "craft-anything-cli nao encontrado (cew setup) e sem exportacao do Ghidra para este programa", "unidades": []})
                continue
            ferramenta, us, estado = res
            programas.append({**base, "ferramenta": ferramenta, "estado": estado if us else "falhou", "unidades": us,
                              **({"mensagem": "nenhuma unidade produzida"} if not us else {})})
        except (craft.ErroCraft, OSError, subprocess.TimeoutExpired, ValueError) as e:
            log.aviso(f"descompilacao de {it['caminho']} falhou: {e}", etapa="engenharia")
            programas.append({**base, "ferramenta": {"nome": "Craft Anything", "versao": None, "operacao": tipo, "motor": None, "evidencia_id": None},
                              "estado": "falhou", "mensagem": str(e)[:1000], "unidades": []})
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "gerado_em": agora_iso(), "programas": programas}
    if not dry_run:
        gravar_json(pasta_base / "indice.json", doc, "codigo_original")
    return doc


# ------------------------------------------------------------------------------- planejar
def _limpo(nome: str) -> str:
    return re.sub(r"@plt$|_plt$", "", nome)


def nome_destino(nome: str, usados: set[str]) -> str:
    base = re.sub(r"[^A-Za-z0-9_]", "_", _limpo(nome).split(".")[-1].split("::")[-1]) or "funcao"
    if base[0].isdigit():
        base = "f_" + base
    if base in {"function", "class", "default", "delete", "new", "var", "let", "const", "import", "export", "return", "switch", "case", "this", "super", "in", "of"}:
        base += "_"
    candidato, n = base, 2
    while candidato in usados:
        candidato, n = f"{base}_{n}", n + 1
    usados.add(candidato)
    return candidato


def _papel(nome: str, corpo: str) -> str:
    alvo = (nome + " " + corpo[:4000]).lower()
    for papel, palavras in PAPEIS:
        if any(p in alvo for p in palavras):
            return papel
    return "logica"


def ler_equivalencias(projeto: Projeto) -> list[dict]:
    eq = ler_json(raiz_repositorio() / "config" / "equivalencias_api.json", "equivalencias_api")["equivalencias"]
    arq = projeto.pasta / "codigo" / "equivalencias.json"
    if arq.is_file():
        eq = ler_json(arq, "equivalencias_api")["equivalencias"] + eq  # as do projeto vem primeiro
    return eq


def _casa_eq(chamada: str, eq: dict) -> bool:
    c = chamada.lower()
    for o in eq["origem"]:
        o = o.lower()
        if (o.endswith("*") and c.startswith(o[:-1])) or c == o or c.endswith("." + o) or c.endswith(o) and len(o) > 5:
            return True
    return False


def _destino_eq(eq: dict, motor: str, ling: str) -> str:
    d = eq["destino"]
    return d.get(motor) or d.get(ling) or next(iter(d.values()))


def planejar(projeto: Projeto, motor: str | None = None, linguagem: str | None = None) -> dict:
    """Plano de traducao a partir do indice de codigo descompilado, preservando o andamento anterior."""
    indice = ler_json(projeto.pasta / "codigo" / "original" / "indice.json", "codigo_original")
    motor = motor or projeto.estado().get("motor_escolhido") or "threejs"
    ling = linguagem or linguagem_do_motor(motor)
    ext = EXTENSAO[ling]
    arq_plano = projeto.pasta / "codigo" / "plano_traducao.json"
    antigo = {u["id"]: u for u in ler_json(arq_plano, "plano_traducao")["unidades"]} if arq_plano.is_file() else {}
    eqs = ler_equivalencias(projeto)
    unidades: list[dict] = []
    for prog in indice["programas"]:
        if not prog["unidades"]:
            continue
        nomes = {_limpo(u["nome"]): u for u in prog["unidades"]}
        corpos = {u["nome"]: (projeto.pasta / u["arquivo"]).read_text(encoding="utf-8", errors="replace") if (projeto.pasta / u["arquivo"]).is_file() else "" for u in prog["unidades"]}
        # grafo de chamadas a partir do proprio codigo descompilado
        chama: dict[str, list[str]] = {}
        externas: dict[str, set[str]] = {}
        for u in prog["unidades"]:
            ids = set(re.findall(r"([A-Za-z_][\w@:.]*)\s*\(", corpos[u["nome"]]))
            chama[u["nome"]] = sorted({nomes[_limpo(i)]["nome"] for i in ids if _limpo(i) in nomes and nomes[_limpo(i)]["nome"] != u["nome"]})
            externas[u["nome"]] = {_limpo(i) for i in ids}
        chamada_por: dict[str, list[str]] = {u["nome"]: [] for u in prog["unidades"]}
        for a, bs in chama.items():
            for b in bs:
                chamada_por[b].append(a)
        dist: dict[str, int] = {}
        fila = deque((u["nome"], 0) for u in prog["unidades"] if _limpo(u["nome"]).lower().split(".")[-1] in ENTRADAS)
        while fila:
            n, d = fila.popleft()
            if n in dist:
                continue
            dist[n] = d
            fila.extend((c, d + 1) for c in chama.get(n, []))
        usados: set[str] = set()
        pasta_dest = f"{PASTA_DESTINO[ling]}/{prog['id']}"
        for u in prog["unidades"]:
            uid = id_estavel("u", prog["id"], u["nome"], u.get("endereco") or "")
            nome_d = nome_destino(u["nome"], usados)
            limpo = _limpo(u["nome"])
            runtime = prog["tipo_codigo"] == "nativo" and (u["nome"].endswith(("@plt", "_plt")) or limpo in RUNTIME or limpo.startswith(("__", "_crt", "__security", "_guard")))
            eq_usadas = sorted({f"{c} -> {_destino_eq(e, motor, ling)}"[:200] for c in externas[u["nome"]] for e in eqs if _casa_eq(c, e)})[:25]
            papel = "biblioteca" if runtime else _papel(limpo, corpos[u["nome"]])
            d = dist.get(u["nome"])
            if runtime:
                prio, estado, motivo = "baixa", "descartada", "runtime/biblioteca do sistema: use a API equivalente do motor (config/equivalencias_api.json)"
            else:
                if prog["tipo_codigo"] == "nativo":
                    prio = "alta" if d is not None and d <= 2 else ("media" if d is not None or papel in ("fisica", "ia", "entrada", "carregador") else "baixa")
                else:
                    prio = "alta" if papel in ("logica", "fisica", "entrada", "ia", "carregador") else "media"
                if papel in ("renderizacao", "plataforma") and prio == "alta":
                    prio = "media"  # desenho/janela sao reconstruidos no motor; a logica vem antes
                estado, motivo = "pendente", ""
            item: dict[str, Any] = {"id": uid, "programa": prog["id"], "nome": u["nome"], "nome_destino": nome_d,
                                    "origem": {"arquivo": u["arquivo"], "endereco": u.get("endereco"), "linhas": u["linhas"]},
                                    "linguagem_origem": prog["linguagem_origem"], "papel": papel, "prioridade": prio, "estado": estado,
                                    "chama": chama[u["nome"]][:50], "chamada_por": chamada_por[u["nome"]][:50], "distancia_entrada": d,
                                    "equivalencias": eq_usadas, "destino": f"{pasta_dest}/{nome_d}{ext}", "hash_origem": u["sha256"], "hash_destino": None}
            if motivo:
                item["motivo"] = motivo
            velho = antigo.get(uid)
            if velho:
                for campo in ("estado", "motivo", "testes", "rascunho_gemini", "destino", "nome_destino"):
                    if campo in velho and velho.get(campo) is not None and not (campo == "estado" and velho["estado"] == "pendente"):
                        item[campo] = velho[campo]
                if velho.get("hash_origem") != u["sha256"] and item["estado"] in ("traduzida", "testada"):
                    item["estado"], item["motivo"] = "traduzida", "o codigo original mudou: revise a traducao"
            arq = projeto.pasta / item["destino"]
            item["hash_destino"] = _sha(arq.read_bytes()) if arq.is_file() else None
            if item["estado"] == "testada" and velho and velho.get("hash_destino") != item["hash_destino"]:
                item["estado"], item["motivo"] = "traduzida", "a traducao mudou depois do ultimo teste: rode 'cew codigo testar'"
            unidades.append(item)
    from collections import Counter

    resumo = dict(Counter(u["estado"] for u in unidades))
    resumo.update({f"prioridade_{k}": v for k, v in Counter(u["prioridade"] for u in unidades if u["estado"] != "descartada").items()})
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "motor": motor, "linguagem_destino": ling,
           "pasta_destino": PASTA_DESTINO[ling], "gerado_em": agora_iso(), "resumo": resumo, "unidades": unidades}
    gravar_json(arq_plano, doc, "plano_traducao")
    return doc


def ler_plano(projeto: Projeto) -> dict:
    return ler_json(projeto.pasta / "codigo" / "plano_traducao.json", "plano_traducao")


def _unidade(plano: dict, chave: str) -> dict:
    u = next((u for u in plano["unidades"] if chave in (u["id"], u["nome"], u.get("nome_destino"))), None)
    if u is None:
        raise ValueError(f"unidade nao encontrada no plano: {chave}")
    return u


def _gravar_plano(projeto: Projeto, plano: dict) -> None:
    from collections import Counter

    plano["resumo"] = {**dict(Counter(u["estado"] for u in plano["unidades"])),
                       **{f"prioridade_{k}": v for k, v in Counter(u["prioridade"] for u in plano["unidades"] if u["estado"] != "descartada").items()}}
    gravar_json(projeto.pasta / "codigo" / "plano_traducao.json", plano, "plano_traducao")


# ---------------------------------------------------------------------------------- pacote
ESQUELETO = {
    "javascript": "// Traducao de {origem} ({ling_origem}) - unidade {uid}.\n// Pacote de contexto: {pacote}\n// Estado: pendente. Troque o corpo pela traducao e escreva os casos em {testes}.\n\nexport function {nome}(...args) {{\n  throw new Error('CEW: {nome} ainda nao traduzida');\n}}\n",
    "typescript": "// Traducao de {origem} ({ling_origem}) - unidade {uid}.\n// Pacote: {pacote}\n\nexport function {nome}(...args: unknown[]): unknown {{\n  throw new Error('CEW: {nome} ainda nao traduzida');\n}}\n",
    "gdscript": "# Traducao de {origem} ({ling_origem}) - unidade {uid}.\n# Pacote: {pacote}\nextends RefCounted\n\nstatic func {nome}(args: Array = []):\n\tpush_error(\"CEW: {nome} ainda nao traduzida\")\n",
    "csharp": "// Traducao de {origem} ({ling_origem}) - unidade {uid}.\n// Pacote: {pacote}\npublic static partial class Logica\n{{\n    public static object {nome}(params object[] args) => throw new System.NotImplementedException(\"CEW: {nome} ainda nao traduzida\");\n}}\n",
    "eventos": "# {nome} (eventos)\n\nTraducao de {origem} ({ling_origem}) para eventos do motor sem codigo.\nPacote: {pacote}\n\n| Condicao | Acao | Origem no codigo |\n|---|---|---|\n",
}


def pacote(projeto: Projeto, chave: str, gemini: bool = False, criar_esqueleto: bool = True) -> dict:
    """Contexto de traducao de uma unidade para a IA principal (e, opcional, um rascunho do Gemini)."""
    plano = ler_plano(projeto)
    u = _unidade(plano, chave)
    ling = plano["linguagem_destino"]
    codigo = (projeto.pasta / u["origem"]["arquivo"]).read_text(encoding="utf-8", errors="replace")
    por_nome = {x["nome"]: x for x in plano["unidades"] if x["programa"] == u["programa"]}
    pasta = projeto.pasta / "codigo" / "pacotes"
    pasta.mkdir(parents=True, exist_ok=True)
    arq_pac = pasta / f"{u['id']}.md"
    arq_testes = f"codigo/testes/{u['id']}.json"
    strings = sorted(set(re.findall(r'"([^"\n]{2,120})"', codigo)))[:40]
    linhas = [f"# Traducao: {u['nome']} -> {ling} ({plano['motor']})", "",
              f"- Unidade: `{u['id']}`  programa `{u['programa']}`  endereco `{u['origem'].get('endereco')}`",
              f"- Papel provavel: **{u['papel']}**; prioridade **{u['prioridade']}**; distancia da entrada: {u.get('distancia_entrada')}",
              f"- Destino: `{u['destino']}` exportando `{u.get('nome_destino')}`", f"- Testes de equivalencia: `{arq_testes}` (schemas/testes_traducao.schema.json)", "",
              "## Regras", "",
              "1. Traduza o COMPORTAMENTO, nao a mecanica do compilador: registradores, pilha, ponteiros e checagens de canario somem.",
              "2. Nada de API do sistema operacional: use as equivalencias abaixo e os assets do `asset_manifest.json` (ids estaveis).",
              "3. Funcao pura sempre que der (entrada -> saida), para poder testar; efeitos (desenho, som) ficam no codigo do motor.",
              "4. Numeros: inteiros de 32 bits com `| 0`/`>>> 0`, `Math.fround` para float de 32 bits quando o resultado precisar bater.",
              "5. Exponha em `window.__CEW_ESTADO` o que os testes de marco precisam observar (skill 07).", "",
              "## Codigo original (descompilado)", "", f"```{u['linguagem_origem'].replace('pseudo_c', 'c')}", codigo.rstrip()[:20000], "```", ""]
    if u["chama"]:
        linhas += ["## Chama", ""] + [f"- `{c}` -> {por_nome[c]['estado'] if c in por_nome else '?'} em `{por_nome[c]['destino'] if c in por_nome else '?'}` ({por_nome[c]['papel'] if c in por_nome else ''})" for c in u["chama"]] + [""]
    if u["chamada_por"]:
        linhas += ["## Chamada por", ""] + [f"- `{c}`" for c in u["chamada_por"]] + [""]
    if u["equivalencias"]:
        linhas += ["## Equivalencias de API (config/equivalencias_api.json)", ""] + [f"- {e}" for e in u["equivalencias"]] + [""]
    if strings:
        linhas += ["## Strings citadas", ""] + [f"- `{s}`" for s in strings] + [""]
    linhas += ["## Modelo de casos de teste", "", "```json", json.dumps({"schema_version": "1.0", "gerado_por": "cew", "unidade": u["id"], "funcao": u.get("nome_destino"), "tolerancia": 0,
              "casos": [{"nome": "exemplo", "entrada": [{"$bytes": "515a5831"}], "saida": 0, "origem": "pseudo_c", "nota": "de onde veio o valor esperado"}]}, ensure_ascii=False, indent=2), "```", ""]
    arq_pac.write_text("\n".join(linhas), encoding="utf-8")
    resultado: dict[str, Any] = {"unidade": u["id"], "pacote": arq_pac.relative_to(projeto.pasta).as_posix(), "destino": u["destino"]}
    destino = projeto.pasta / u["destino"]
    if criar_esqueleto and not destino.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(ESQUELETO[ling].format(origem=f"{u['programa']}::{u['nome']}", ling_origem=u["linguagem_origem"], uid=u["id"], nome=u.get("nome_destino"),
                                                  pacote=resultado["pacote"], testes=arq_testes), encoding="utf-8")
        resultado["esqueleto"] = u["destino"]
    if gemini:
        resultado["rascunho_gemini"] = _rascunho_gemini(projeto, plano, u, codigo)
        u["rascunho_gemini"] = resultado["rascunho_gemini"]
        _gravar_plano(projeto, plano)
    return resultado


def _rascunho_gemini(projeto: Projeto, plano: dict, u: dict, codigo: str) -> str:
    from .gemini import ClienteGemini, Parte

    tarefa = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "tarefa": "traducao", "unidade": u["id"], "nome": u["nome"], "nome_destino": u.get("nome_destino", u["nome"]),
              "linguagem_origem": u["linguagem_origem"], "linguagem_destino": plano["linguagem_destino"], "motor": plano["motor"], "codigo": codigo[:16000],
              "chamadas": u["chama"][:60], "equivalencias": u["equivalencias"][:40],
              "instrucoes": ("Traduza o comportamento desta funcao para um modulo completo na linguagem de destino, exportando a funcao com nome_destino. "
                             "Sem APIs do sistema operacional; use as equivalencias. Diga em 'duvidas' o que o pseudo-C nao deixa claro. "
                             "Sugira casos de teste (entrada -> saida) so quando puder deduzi-los do codigo.")}
    validar(tarefa, "gemini/tarefa_traducao")
    resp = ClienteGemini().gerar("traducao", [Parte(texto="Tarefa do CEW (JSON):\n" + json.dumps(tarefa, ensure_ascii=False))], "gemini/resposta_traducao")
    pasta = projeto.pasta / "codigo" / "rascunhos"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / f"{u['id']}{EXTENSAO[plano['linguagem_destino']]}"
    arq.write_text(resp["codigo"], encoding="utf-8")
    (pasta / f"{u['id']}.resposta.json").write_text(json.dumps(resp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return arq.relative_to(projeto.pasta).as_posix()


# ------------------------------------------------------------------------- registrar/testar
def registrar(projeto: Projeto, chave: str, estado: str, motivo: str = "", destino: str | None = None) -> dict:
    plano = ler_plano(projeto)
    u = _unidade(plano, chave)
    if estado not in ("pendente", "traduzida", "descartada"):
        raise ValueError("estado registravel: pendente, traduzida ou descartada ('testada' vem de 'cew codigo testar')")
    if destino:
        u["destino"] = destino
    if estado == "traduzida" and not (projeto.pasta / u["destino"]).is_file():
        raise ValueError(f"arquivo traduzido nao existe: {u['destino']}")
    u["estado"] = estado
    if motivo:
        u["motivo"] = motivo
    arq = projeto.pasta / u["destino"]
    u["hash_destino"] = _sha(arq.read_bytes()) if arq.is_file() else None
    _gravar_plano(projeto, plano)
    return u


def testar(projeto: Projeto, chave: str | None = None) -> list[dict]:
    """Roda os casos de equivalencia (codigo/testes/<unidade>.json) contra a traducao (JavaScript)."""
    plano = ler_plano(projeto)
    alvos = [_unidade(plano, chave)] if chave else [u for u in plano["unidades"] if (projeto.pasta / "codigo" / "testes" / f"{u['id']}.json").is_file()]
    node = shutil.which("node")
    runner = Path(__file__).resolve().parent / "js" / "testar_traducao.mjs"
    resultados = []
    for u in alvos:
        arq_casos = projeto.pasta / "codigo" / "testes" / f"{u['id']}.json"
        if not arq_casos.is_file():
            resultados.append({"unidade": u["id"], "nome": u["nome"], "aprovado": False, "detalhes": f"sem casos em {arq_casos.relative_to(projeto.pasta)}"})
            continue
        casos = ler_json(arq_casos, "testes_traducao")
        if plano["linguagem_destino"] not in ("javascript",):
            resultados.append({"unidade": u["id"], "nome": u["nome"], "aprovado": False, "manual": True,
                               "detalhes": f"testes automaticos so para javascript; rode os casos no {plano['linguagem_destino']} do motor"})
            continue
        if not node:
            resultados.append({"unidade": u["id"], "nome": u["nome"], "aprovado": False, "detalhes": "node nao encontrado"})
            continue
        destino = projeto.pasta / u["destino"]
        p = subprocess.run([node, str(runner), str(destino.resolve()), str(arq_casos.resolve())], capture_output=True, text=True, timeout=120)
        try:
            r = json.loads(p.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            r = {"casos": len(casos["casos"]), "aprovados": 0, "falhas": [p.stderr[-600:] or "o modulo nao carregou"]}
        aprovado = r["aprovados"] == r["casos"] and r["casos"] > 0
        u["testes"] = {"arquivo": arq_casos.relative_to(projeto.pasta).as_posix(), "casos": r["casos"], "aprovados": r["aprovados"], "aprovado": aprovado, "em": agora_iso()}
        u["hash_destino"] = _sha(destino.read_bytes()) if destino.is_file() else None
        if aprovado:
            u["estado"] = "testada"
            u.pop("motivo", None)
        elif u["estado"] != "descartada":
            u["estado"] = "reprovada"
            u["motivo"] = "; ".join(str(f) for f in r["falhas"][:3])[:500]
        resultados.append({"unidade": u["id"], "nome": u["nome"], "aprovado": aprovado, "casos": r["casos"], "aprovados": r["aprovados"],
                           "detalhes": "todos os casos batem com o original" if aprovado else "; ".join(str(f) for f in r["falhas"][:3])[:600]})
    _gravar_plano(projeto, plano)
    return resultados
