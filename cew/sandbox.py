"""Execucao isolada de rascunhos de conversor vindos do Gemini (item 11).

O rascunho roda numa pasta propria, em outro processo, com limite de tempo e (POSIX) de memoria,
CPU e tamanho de arquivo. A rede e bloqueada em duas camadas:
- Linux com `unshare` disponivel e namespaces de usuario liberados: processo sem interface de rede;
- sempre: um sitecustomize que troca socket.socket por uma funcao que falha (bloqueio no nivel
  do Python: impede o uso acidental de rede, mas nao e uma barreira de seguranca contra codigo
  hostil - por isso a IA principal le o codigo antes de rodar, ver skills/04).
Nada roda aqui sem que a pessoa/IA principal chame explicitamente; o resultado e so um relatorio.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .caminhos import raiz_repositorio

SITECUSTOMIZE = '''
import socket as _s
def _bloqueado(*a, **k):
    raise OSError("rede bloqueada na sandbox do CEW")
_s.socket = _bloqueado
_s.create_connection = _bloqueado
_s.getaddrinfo = _bloqueado
'''


@dataclass
class ResultadoSandbox:
    codigo_saida: int | None
    tempo_esgotado: bool
    stdout: str
    stderr: str
    rede_isolada_no_so: bool
    pasta: str

    def para_json(self) -> dict:
        return self.__dict__.copy()


def _limites_posix(mem_mb: int, cpu_s: int, arquivo_mb: int):
    def aplicar() -> None:  # roda no processo filho antes do exec
        import resource

        mem = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
        tam = arquivo_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_FSIZE, (tam, tam))
        os.setsid()

    return aplicar


def unshare_disponivel() -> bool:
    if not sys.platform.startswith("linux") or not shutil.which("unshare"):
        return False
    try:
        r = subprocess.run(["unshare", "--net", "--map-root-user", "true"], capture_output=True, timeout=10)
        return r.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def executar_rascunho(codigo: str, pasta: Path, entrada: Path | None, tempo_s: int = 60, mem_mb: int = 1024, arquivo_mb: int = 512) -> ResultadoSandbox:
    """Grava o rascunho em `pasta`/conversor.py e roda `python conversor.py <entrada> -o saida --dry-run`.

    `--dry-run` primeiro: o rascunho deve seguir o esqueleto converters/comum/cli.py.
    """
    pasta = Path(pasta)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / "conversor.py").write_text(codigo, encoding="utf-8")
    site = pasta / "_site"
    site.mkdir(exist_ok=True)
    (site / "sitecustomize.py").write_text(SITECUSTOMIZE, encoding="utf-8")
    # copia so a biblioteca comum, para o rascunho nao enxergar o resto do repositorio
    destino_comum = pasta / "converters" / "comum"
    if destino_comum.exists():
        shutil.rmtree(destino_comum)
    shutil.copytree(raiz_repositorio() / "converters" / "comum", destino_comum, ignore=shutil.ignore_patterns("__pycache__"))
    (pasta / "converters" / "__init__.py").write_text("", encoding="utf-8")
    args = [sys.executable, "-s", "conversor.py"]
    if entrada is not None:
        copia = pasta / ("entrada" + Path(entrada).suffix)
        shutil.copyfile(entrada, copia)
        args += [copia.name, "-o", "saida", "--dry-run"]
    else:
        args += ["--help"]
    env = {"PYTHONPATH": f"{site}{os.pathsep}{pasta}", "PYTHONNOUSERSITE": "1", "PYTHONDONTWRITEBYTECODE": "1",
           "PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
           "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9"}
    isolado = unshare_disponivel()
    if isolado:
        args = ["unshare", "--net", "--map-root-user", *args]
    kwargs: dict = {"cwd": pasta, "env": env, "capture_output": True, "text": True}
    if os.name == "posix":
        kwargs["preexec_fn"] = _limites_posix(mem_mb, tempo_s + 5, arquivo_mb)
    try:
        p = subprocess.run(args, timeout=tempo_s, **kwargs)
        return ResultadoSandbox(p.returncode, False, p.stdout[-20000:], p.stderr[-20000:], isolado, str(pasta))
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        err = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return ResultadoSandbox(None, True, out[-20000:], err[-20000:], isolado, str(pasta))
