"""Craft Anything: localizar o craft-anything-cli e chamar os comandos reais.

Comandos conferidos em apps/craft-anything-cli/src/main.rs (commit 44c89ba, versao 0.6.1) e
executados de verdade em 2026-11-20:
- `doctor` -> JSON {"checks": [{name, status, message, remediation?}], "healthy": bool}
- `triage <caminho>` -> registro de evidencia (operation core_target_triage)
- `commands` -> lista de ferramentas; `<ferramenta-com-hifens> [caminho] [--chave valor]`
- `settings-set --key engines.ghidra.install_dir --value '"<pasta>"'` (o Craft Anything acha o
  Ghidra pela configuracao, nao por GHIDRA_INSTALL_DIR)
- opcoes globais: --format json (padrao), --project <pasta .cany>, --deep | --clean-room, --allow-run
- `mcp` serve as ferramentas por stdio (usado em .vscode/mcp.json)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .caminhos import raiz_repositorio
from .config import carregar_env


class ErroCraft(RuntimeError):
    pass


def localizar_cli() -> str | None:
    carregar_env()
    env = os.environ.get("CEW_CRAFT_ANYTHING_CLI")
    if env and Path(env).is_file():
        return env
    exe = "craft-anything-cli.exe" if os.name == "nt" else "craft-anything-cli"
    for cand in (raiz_repositorio() / "ferramentas" / "craft-anything" / "target" / "release" / exe,
                 raiz_repositorio() / "ferramentas" / "bin" / exe):
        if cand.is_file():
            return str(cand)
    return shutil.which("craft-anything-cli")


def rodar(args: list[str], projeto_cany: Path | None = None, deep: bool | None = True, tempo_s: int = 600, cli: str | None = None) -> Any:
    cli = cli or localizar_cli()
    if not cli:
        raise ErroCraft("craft-anything-cli nao encontrado (rode 'cew setup' ou defina CEW_CRAFT_ANYTHING_CLI)")
    cmd = [cli, "--format", "json"]
    if projeto_cany:
        cmd += ["--project", str(projeto_cany)]
    if deep is True:
        cmd.append("--deep")
    elif deep is False:
        cmd.append("--clean-room")
    cmd += args
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=tempo_s)
    saida = p.stdout.strip()
    try:
        dados = json.loads(saida) if saida else None
    except ValueError:
        dados = {"texto": saida}
    if p.returncode != 0:
        raise ErroCraft(f"{' '.join(args[:2])} falhou ({p.returncode}): {json.dumps(dados, ensure_ascii=False)[:800] if dados else p.stderr[-800:]}")
    return dados


def doctor(cli: str | None = None) -> dict:
    return rodar(["doctor"], deep=None, tempo_s=180, cli=cli)


def versao(cli: str | None = None) -> str | None:
    cli = cli or localizar_cli()
    if not cli:
        return None
    p = subprocess.run([cli, "--version"], capture_output=True, text=True, timeout=60)
    return p.stdout.strip().split()[-1] if p.returncode == 0 and p.stdout.strip() else None


def triage(caminho: Path, projeto_cany: Path | None = None) -> dict:
    return rodar(["triage", str(caminho)], projeto_cany=projeto_cany, deep=True)


def ferramenta(nome: str, caminho: Path | None = None, projeto_cany: Path | None = None, **opcoes: Any) -> Any:
    args = [nome.replace("_", "-")]
    if caminho is not None:
        args.append(str(caminho))
    for k, v in opcoes.items():
        args += [f"--{k.replace('_', '-')}", v if isinstance(v, str) else json.dumps(v)]
    return rodar(args, projeto_cany=projeto_cany, deep=True)


def definir_ghidra(pasta: Path, dry_run: bool = False) -> list[str]:
    args = ["settings-set", "--key", "engines.ghidra.install_dir", "--value", json.dumps(str(pasta))]
    if not dry_run:
        rodar(args, deep=None)
    return args
