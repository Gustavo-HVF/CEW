"""Ghidra (modo Deep): deteccao da instalacao, da versao do Java exigida e exportacao headless.

Fatos conferidos em 2026-11-20 no repositorio oficial (NationalSecurityAgency/ghidra):
- Ghidra/application.properties traz application.version e application.java.min
  (12.1.4 -> Java 21; 12.2 -> Java 25);
- support/analyzeHeadless (Linux/macOS) e support/analyzeHeadless.bat (Windows);
- sintaxe: analyzeHeadless <pasta_projeto> <nome>[/<pasta>] -import <arquivo> -scriptPath "<p1>;<p2>"
  -postScript <Script> [args]* -deleteProject -analysisTimeoutPerFile <s> -max-cpu <n> -log <arq>;
  os argumentos do script chegam por getScriptArgs() (analyzeHeadlessREADME.md).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from .caminhos import raiz_repositorio
from .config import carregar_env


@dataclass
class Instalacao:
    pasta: Path
    versao: str
    java_minimo: int
    headless: Path


def ler_propriedades(pasta: Path) -> dict[str, str]:
    arq = Path(pasta) / "Ghidra" / "application.properties"
    props = {}
    if arq.is_file():
        for linha in arq.read_text(encoding="utf-8", errors="replace").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, _, v = linha.partition("=")
                props[k.strip()] = v.strip()
    return props


def localizar(pasta: str | Path | None = None) -> Instalacao | None:
    carregar_env()
    candidato = pasta or os.environ.get("GHIDRA_INSTALL_DIR")
    if not candidato:
        return None
    p = Path(candidato).expanduser()
    headless = p / "support" / ("analyzeHeadless.bat" if os.name == "nt" else "analyzeHeadless")
    if not headless.is_file():
        return None
    props = ler_propriedades(p)
    return Instalacao(p, props.get("application.version", "desconhecida"), int(props.get("application.java.min", "0") or 0), headless)


def versao_java() -> tuple[int | None, str | None]:
    """(versao principal, caminho) do java do JAVA_HOME ou do PATH."""
    jh = os.environ.get("JAVA_HOME")
    java = str(Path(jh) / "bin" / ("java.exe" if os.name == "nt" else "java")) if jh else shutil.which("java")
    if not java or not Path(java).exists():
        return None, None
    try:
        p = subprocess.run([java, "-version"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return None, java
    m = re.search(r'version "(\d+)(?:\.(\d+))?', p.stderr + p.stdout)
    if not m:
        return None, java
    maior = int(m.group(1))
    if maior == 1 and m.group(2):  # "1.8" -> 8
        maior = int(m.group(2))
    return maior, java


def exportar(inst: Instalacao, programa: Path, saida_json: Path, max_pseudo: int = 200, segundos_por_funcao: int = 30,
             tempo_analise_s: int = 3600, max_cpu: int | None = None, log: Path | None = None, dry_run: bool = False) -> list[str]:
    """Roda a analise headless e o ExportarCEW.java. Devolve o comando usado."""
    scripts = raiz_repositorio() / "scripts" / "ghidra"
    tmp = Path(tempfile.mkdtemp(prefix="cew-ghidra-"))
    cmd = [str(inst.headless), str(tmp), "cew", "-import", str(programa), "-scriptPath", str(scripts),
           "-postScript", "ExportarCEW.java", str(saida_json), str(max_pseudo), str(segundos_por_funcao),
           "-analysisTimeoutPerFile", str(tempo_analise_s), "-deleteProject"]
    if max_cpu:
        cmd += ["-max-cpu", str(max_cpu)]
    if log:
        cmd += ["-log", str(log)]
    if dry_run:
        shutil.rmtree(tmp, ignore_errors=True)
        return cmd
    saida_json.parent.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo_analise_s + 600)
        if p.returncode != 0 or not saida_json.is_file():
            raise RuntimeError(f"analyzeHeadless falhou ({p.returncode}): {(p.stderr or p.stdout)[-1500:]}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return cmd
