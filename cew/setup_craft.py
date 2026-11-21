"""`cew setup`: clona e compila o Craft Anything, roda o doctor, liga o Ghidra e testa o Gemini.

Passos (cada um com --dry-run):
1. clona https://github.com/storytold/craft-anything (ou git@github.com:... com --ssh / chave SSH
   detectada) em ferramentas/craft-anything, na ref fixada em config/versoes.json;
2. confere rustc >= rust.minimo (o README do Craft Anything pede Rust 1.97+) e compila
   `cargo build --release -p craft-anything-cli` (o app desktop, `-p craft-anything`, so com --com-app);
3. roda `craft-anything-cli doctor` e salva a saida real em reports/ambiente.json;
4. com GHIDRA_INSTALL_DIR definido: `craft-anything-cli settings-set --key engines.ghidra.install_dir`;
5. teste real do Gemini (item 1.2).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from . import ambiente, craft, ghidra
from .caminhos import raiz_repositorio
from .config import config_versoes
from .logs import Log


def _rodar(cmd: list[str], cwd: Path | None, dry_run: bool, log: Log, tempo: int = 7200) -> int:
    texto = " ".join(cmd)
    print(("[dry-run] " if dry_run else "$ ") + texto)
    log.info(texto, etapa="ambiente", dry_run=dry_run)
    if dry_run:
        return 0
    return subprocess.run(cmd, cwd=cwd, timeout=tempo).returncode


def _ssh_disponivel() -> bool:
    home = Path.home() / ".ssh"
    if not any((home / n).is_file() for n in ("id_ed25519", "id_rsa", "id_ecdsa")):
        return False
    try:
        p = subprocess.run(["git", "ls-remote", config_versoes()["craft_anything"]["repositorio_ssh"], "HEAD"], capture_output=True, timeout=30,
                           env={**os.environ, "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"})
        return p.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def instalar(ssh: bool | None = None, com_app: bool = False, dry_run: bool = False, pular_compilacao: bool = False, log: Log | None = None) -> Path | None:
    log = log or Log("setup")
    v = config_versoes()["craft_anything"]
    destino = raiz_repositorio() / "ferramentas" / "craft-anything"
    usar_ssh = _ssh_disponivel() if ssh is None else ssh
    url = v["repositorio_ssh"] if usar_ssh else v["repositorio_https"]
    if not (destino / ".git").is_dir():
        destino.parent.mkdir(parents=True, exist_ok=True)
        if _rodar(["git", "clone", "--filter=blob:none", url, str(destino)], None, dry_run, log) != 0:
            raise RuntimeError(f"git clone falhou ({url})")
    if _rodar(["git", "-C", str(destino), "fetch", "--depth", "1", "origin", v["ref"]], None, dry_run, log) != 0:
        log.aviso("fetch da ref fixada falhou; tentando checkout direto", etapa="ambiente")
    if _rodar(["git", "-C", str(destino), "checkout", "--detach", v["ref"]], None, dry_run, log) != 0:
        raise RuntimeError(f"checkout de {v['ref']} falhou")
    if pular_compilacao:
        return None
    exe, ver = ambiente._versao(["rustc", "--version"])
    minimo = config_versoes()["rust"]["minimo"]
    if not dry_run and not ambiente._maior_ou_igual(ver, minimo):
        raise RuntimeError(f"Rust {minimo}+ necessario (encontrado: {ver or 'nenhum'}); rode 'rustup update'")
    if not shutil.which("cargo") and not dry_run:
        raise RuntimeError("cargo nao encontrado (instale o Rust com rustup)")
    pacotes = ["-p", "craft-anything-cli"] + (["-p", "craft-anything"] if com_app else [])
    if _rodar(["cargo", "build", "--release", *pacotes], destino, dry_run, log) != 0:
        raise RuntimeError("cargo build falhou; veja a saida acima (no Linux o app desktop precisa das bibliotecas listadas no README do Craft Anything)")
    exe_nome = "craft-anything-cli.exe" if os.name == "nt" else "craft-anything-cli"
    return destino / "target" / "release" / exe_nome


def executar(ssh: bool | None = None, com_app: bool = False, sem_craft: bool = False, dry_run: bool = False, testar_gemini: bool = True) -> dict:
    log = Log("setup", eco=False)
    if not sem_craft and not (craft.localizar_cli() and not dry_run):
        instalar(ssh=ssh, com_app=com_app, dry_run=dry_run, log=log)
    inst = ghidra.localizar()
    cli = craft.localizar_cli()
    if inst and cli:
        args = craft.definir_ghidra(inst.pasta, dry_run=dry_run)
        print(("[dry-run] " if dry_run else "$ ") + f"{cli} " + " ".join(args))
    rel = ambiente.verificar(testar_gemini=testar_gemini and not dry_run)
    if not dry_run:
        ambiente.gravar(rel)
    return rel
