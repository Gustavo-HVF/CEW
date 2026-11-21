"""Etapa 7 (parte 1): gera o projeto web no motor escolhido, em app/ (pasta do Craft Anything).

Modelos prontos em cew/modelos_web/: threejs, babylonjs, phaser, pixijs (Vite + Playwright).
Os outros motores (Godot, Unity WebGL, PlayCanvas, Construct 3, GDevelop) nao tem modelo
gerado automaticamente: skills/05 descreve como carregar o asset_manifest.json neles.
O projeto web le os assets de ../web (publicDir do Vite), sem copiar nada.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from .motor import MOTORES
from .projeto import Projeto

MODELOS = Path(__file__).resolve().parent / "modelos_web"
COM_MODELO = ("threejs", "babylonjs", "phaser", "pixijs")


def gerar(projeto: Projeto, motor: str, sobrescrever: bool = False, dry_run: bool = False) -> list[str]:
    if motor not in COM_MODELO:
        raise ValueError(f"o CEW nao gera modelo para {motor}; veja skills/05-selecao-e-arquitetura-motor-grafico/SKILL.md")
    app = projeto.pasta / "app"
    gerados: list[str] = []
    subst = {"{{PROJETO}}": projeto.nome, "{{MOTOR}}": motor, "{{MOTOR_NOME}}": MOTORES[motor]["nome"]}
    for origem_base in (MODELOS / "comum", MODELOS / motor):
        for arq in sorted(origem_base.rglob("*")):
            if arq.is_dir() or "__pycache__" in arq.parts:
                continue
            rel = arq.relative_to(origem_base)
            destino = app / rel
            gerados.append(f"app/{rel.as_posix()}")
            if dry_run:
                continue
            if destino.exists() and not sobrescrever and rel.as_posix() not in ("src/manifesto.js", "tests/cena.spec.js", "vite.config.js", "playwright.config.js"):
                continue  # o codigo do jogo e da IA principal: nao sobrescrever
            texto = arq.read_text(encoding="utf-8")
            for k, v in subst.items():
                texto = texto.replace(k, v)
            destino.parent.mkdir(parents=True, exist_ok=True)
            destino.write_text(texto, encoding="utf-8")
    if not dry_run:
        _cenas(projeto)
    return gerados


def _cenas(projeto: Projeto) -> None:
    """tests/cenas.json: uma entrada por captura de referencia em referencias/ (ou so a principal)."""
    refs = sorted(projeto.caminho("referencias").glob("*.png"))
    cenas = [{"id": r.stem, "url": f"/?cena={r.stem}"} for r in refs] or [{"id": "principal", "url": "/"}]
    (projeto.pasta / "app" / "tests" / "cenas.json").write_text(json.dumps(cenas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def limpar(projeto: Projeto) -> None:
    shutil.rmtree(projeto.pasta / "app" / "dist", ignore_errors=True)
