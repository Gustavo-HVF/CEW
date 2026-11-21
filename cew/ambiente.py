"""Etapa 1: verificacao do ambiente -> reports/ambiente.json (schemas/ambiente.schema.json).

Obrigatorios: Python, Node.js/npm, git, ffmpeg, craft-anything-cli (ou Rust para compila-lo) e a
GEMINI_API_KEY com o teste real do modelo. Opcionais: Java + Ghidra (modo Deep), Blender.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

from . import GERADO_POR, SCHEMA_VERSION
from . import craft, ghidra
from .caminhos import raiz_repositorio
from .config import config_versoes
from .esquemas import gravar_json
from .gemini import ClienteGemini
from .logs import agora_iso


def _versao(cmd: list[str], padrao: str = r"(\d+\.\d+(?:\.\d+)?)") -> tuple[str | None, str | None]:
    exe = shutil.which(cmd[0])
    if not exe:
        return None, None
    try:
        p = subprocess.run([exe, *cmd[1:]], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return exe, None
    m = re.search(padrao, p.stdout + p.stderr)
    return exe, m.group(1) if m else None


def _maior_ou_igual(v: str | None, minimo: str | None) -> bool:
    if not minimo:
        return True
    if not v:
        return False
    def t(x: str) -> tuple[int, ...]:
        return tuple(int(p) for p in re.findall(r"\d+", x)[:3])
    return t(v) >= t(minimo)


def ferramenta(id_: str, obrigatoria: bool, caminho: str | None, versao: str | None, minimo: str | None, mensagem: str = "") -> dict:
    ok = caminho is not None and _maior_ou_igual(versao, minimo)
    if not mensagem:
        mensagem = "ok" if ok else ("nao encontrado" if caminho is None else f"versao {versao} abaixo do minimo {minimo}")
    return {"id": id_, "obrigatoria": obrigatoria, "encontrada": caminho is not None, "ok": ok, "caminho": caminho, "versao": versao, "versao_minima": minimo, "mensagem": mensagem}


def verificar(testar_gemini: bool = True, cliente: ClienteGemini | None = None, doctor: bool = True) -> dict:
    v = config_versoes()
    itens = []
    itens.append(ferramenta("python", True, sys.executable, platform.python_version(), v["python"]["minimo"]))
    itens.append(ferramenta("git", True, *_versao(["git", "--version"]), None))
    exe, ver = _versao(["node", "--version"])
    itens.append(ferramenta("node", True, exe, ver, v["node"]["minimo"]))
    itens.append(ferramenta("npm", True, *_versao(["npm", "--version"]), None))
    itens.append(ferramenta("ffmpeg", True, *_versao(["ffmpeg", "-version"], r"version (\S+)"), None))
    cli = craft.localizar_cli()
    ver_cli = craft.versao(cli) if cli else None
    exe_r, ver_r = _versao(["rustc", "--version"])
    itens.append(ferramenta("rust", cli is None, exe_r, ver_r, v["rust"]["minimo"],
                            "" if cli is None else ("ok" if exe_r else "nao encontrado (so e preciso para compilar o Craft Anything)")))
    itens.append(ferramenta("cargo", cli is None, *_versao(["cargo", "--version"]), None))
    itens.append(ferramenta("craft-anything-cli", True, cli, ver_cli, None, "" if cli else "nao encontrado: rode 'cew setup'"))
    inst = ghidra.localizar()
    jv, jexe = ghidra.versao_java()
    java_min = inst.java_minimo if inst else v["java"]["minimo"]
    itens.append(ferramenta("java", inst is not None, jexe, str(jv) if jv else None, str(java_min),
                            "" if jexe else ("nao encontrado" + (" (o Ghidra precisa)" if inst else " (opcional; so para o Ghidra)"))))
    itens.append(ferramenta("ghidra", False, str(inst.headless) if inst else None, inst.versao if inst else None, None,
                            "" if inst else "opcional (modo Deep): defina GHIDRA_INSTALL_DIR"))
    itens.append(ferramenta("blender", False, *_versao(["blender", "--version"], r"Blender (\S+)"), None))
    gem = {"chave_presente": False, "teste_ok": False, "erro": None, "tipo_erro": None, "latencia_ms": None}
    cliente = cliente or ClienteGemini()
    gem["chave_presente"] = cliente.tem_chave
    gem["modelo"] = cliente.config["modelo"]
    if testar_gemini:
        gem.update(cliente.testar())
    elif not cliente.tem_chave:
        gem.update(erro="GEMINI_API_KEY nao definida", tipo_erro="sem_chave")
    ca: dict = {"repositorio": v["craft_anything"]["repositorio_https"], "ref": v["craft_anything"]["ref"], "cli": cli, "doctor": None, "mensagem": ""}
    if cli and doctor:
        try:
            ca["doctor"] = craft.doctor(cli)
            ca["mensagem"] = "doctor executado"
        except (craft.ErroCraft, OSError, subprocess.TimeoutExpired) as e:
            ca["mensagem"] = f"doctor falhou: {e}"
    faltando = [i["id"] for i in itens if i["obrigatoria"] and not i["ok"]]
    if not gem["teste_ok"]:
        faltando.append("gemini")
    return {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "gerado_em": agora_iso(),
            "sistema": {"os": f"{platform.system()} {platform.release()}", "arquitetura": platform.machine(), "python": platform.python_version()},
            "ferramentas": itens, "craft_anything": ca, "gemini": gem, "obrigatorios_faltando": faltando, "pronto": not faltando}


def gravar(rel: dict) -> Path:
    pasta = Path(os.environ["CEW_REPORTS"]) if os.environ.get("CEW_REPORTS") else raiz_repositorio() / "reports"
    return gravar_json(pasta / "ambiente.json", rel, "ambiente")


def resumo_texto(rel: dict) -> str:
    linhas = []
    for i in rel["ferramentas"]:
        marca = "ok " if i["ok"] else ("FALTA" if i["obrigatoria"] else " -  ")
        linhas.append(f"[{marca}] {i['id']:<20} {i.get('versao') or '':<12} {i['mensagem']}")
    g = rel["gemini"]
    linhas.append(f"[{'ok ' if g['teste_ok'] else 'FALTA'}] {'gemini':<20} {g.get('modelo', ''):<12} {g.get('erro') or 'teste real ok'}")
    linhas.append("Pronto para usar o CEW." if rel["pronto"] else "Faltando: " + ", ".join(rel["obrigatorios_faltando"]))
    return "\n".join(linhas)
