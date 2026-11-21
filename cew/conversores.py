"""Conversores: resolucao em tres fontes, dois tipos e execucao isolada.

Referencias aceitas (schemas/comum.schema.json#/$defs/ref_conversor):
- "converters/<familia>/<nome>.py"            fonte "generico" (nucleo do CEW, sempre disponivel)
- "cookbook/<familia>/<nome>.py"              fonte "cookbook" (receitas opcionais e testadas)
- "projeto:conversores/<...>/<nome>.py|.json" fonte "projeto" (escrito pelo agente da pessoa)

Tipos: modulo Python (INFO + converter) ou comando externo declarado em JSON
(schemas/conversor_comando.schema.json). Os dois devolvem o mesmo resultado
(schemas/conversor_resultado.schema.json).

Conversores do repositorio rodam no proprio processo; os do projeto rodam em subprocesso com tempo e
memoria limitados (config/cew.json), para que codigo novo nunca derrube o orquestrador.
"""

from __future__ import annotations

import fnmatch
import hashlib
import importlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from .caminhos import raiz_repositorio
from .esquemas import ler_json, validar

PREFIXO_PROJETO = "projeto:"


class ErroConversor(ValueError):
    pass


@lru_cache(maxsize=1)
def config_cew() -> dict:
    return ler_json(raiz_repositorio() / "config" / "cew.json", "config_cew")


@dataclass(frozen=True)
class Ref:
    texto: str
    fonte: str  # projeto | cookbook | generico
    tipo: str  # python | comando
    caminho: Path

    @property
    def do_projeto(self) -> bool:
        return self.fonte == "projeto"


def resolver(ref: str, projeto_pasta: Path | None = None) -> Ref:
    r = ref.replace("\\", "/")
    if ".." in r.split("/"):
        raise ErroConversor(f"referencia de conversor insegura: {ref}")
    if r.startswith(PREFIXO_PROJETO):
        if projeto_pasta is None:
            raise ErroConversor(f"{ref} e um conversor de projeto: informe o projeto")
        rel = r[len(PREFIXO_PROJETO):]
        if not rel.startswith("conversores/"):
            raise ErroConversor(f"conversor de projeto fica em conversores/: {ref}")
        caminho = Path(projeto_pasta) / rel
        tipo = "comando" if rel.endswith(".json") else "python"
        return Ref(r, "projeto", tipo, caminho)
    if r.startswith("converters/") and r.endswith(".py"):
        return Ref(r, "generico", "python", raiz_repositorio() / r)
    if r.startswith("cookbook/") and r.endswith(".py"):
        return Ref(r, "cookbook", "python", raiz_repositorio() / r)
    raise ErroConversor(f"referencia de conversor invalida: {ref}")


def hash_codigo(ref: Ref) -> str:
    if not ref.caminho.is_file():
        raise ErroConversor(f"conversor nao encontrado: {ref.caminho}")
    return hashlib.sha256(ref.caminho.read_bytes()).hexdigest()


def _modulo_repo(ref: Ref):
    mod = importlib.import_module(ref.texto[:-3].replace("/", "."))
    if not hasattr(mod, "INFO") or not hasattr(mod, "converter"):
        raise ErroConversor(f"{ref.texto} nao define INFO e converter()")
    return mod


def _modulo_arquivo(caminho: Path):
    raiz = str(raiz_repositorio())
    if raiz not in sys.path:
        sys.path.insert(0, raiz)
    nome = "cew_conv_" + hashlib.sha256(str(caminho).encode()).hexdigest()[:12]
    spec = importlib.util.spec_from_file_location(nome, caminho)
    if spec is None or spec.loader is None:
        raise ErroConversor(f"nao foi possivel carregar {caminho}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "INFO") or not hasattr(mod, "converter"):
        raise ErroConversor(f"{caminho} nao define INFO e converter()")
    return mod


def ler_comando(caminho: Path) -> dict:
    return ler_json(caminho, "conversor_comando")


def info(ref: str | Ref, projeto_pasta: Path | None = None) -> dict:
    r = ref if isinstance(ref, Ref) else resolver(ref, projeto_pasta)
    if r.tipo == "comando":
        c = ler_comando(r.caminho)
        return {"arquivo": r.texto, "descricao": c["descricao"], "formatos_entrada": c["formatos_entrada"], "destino": c["destino"],
                "papel": c.get("papel", "conversor"), "versao": c.get("versao", "1.0"), "tipo": "comando"}
    mod = _modulo_repo(r) if not r.do_projeto else _modulo_arquivo(r.caminho)
    d = dict(mod.INFO)
    d["arquivo"] = r.texto
    d["tipo"] = "python"
    return d


def papel(ref: str, projeto_pasta: Path | None = None) -> str:
    return info(ref, projeto_pasta).get("papel", "conversor")


# ------------------------------------------------------------------------------- execucao
def _resultado_falha(ref: Ref, entrada: Path, dry_run: bool, erro: str) -> dict:
    dados = entrada.read_bytes() if entrada.is_file() else b""
    r = {"schema_version": "1.0", "gerado_por": "cew-conversor", "conversor": ref.texto, "entrada": {"caminho": entrada.name, "sha256": hashlib.sha256(dados).hexdigest(),
         "tamanho_bytes": len(dados)}, "dry_run": dry_run, "ok": False, "erro": erro[:2000], "saidas": [], "avisos": []}
    validar(r, "conversor_resultado")
    return r


def _metadados_auto(arq: Path, formato: str) -> dict:
    """Metadados de manifesto para saidas de comandos externos (PNG e WAV sao lidos de verdade)."""
    try:
        if formato == "png":
            from converters.comum.imagem import ler_png

            return ler_png(arq.read_bytes()).metadados("srgb")
        if formato == "wav":
            from converters.comum.audio import ler_wav

            return ler_wav(arq.read_bytes()).metadados()
    except Exception:  # noqa: BLE001 - metadado e opcional; a verificacao confere depois
        return {}
    return {}


def _rodar_comando(ref: Ref, entrada: Path, saida: Path, opcoes: dict, dry_run: bool, projeto_pasta: Path | None) -> dict:
    c = ler_comando(ref.caminho)
    opc = {**c.get("opcoes_padrao", {}), **opcoes}
    destino = Path(tempfile.mkdtemp(prefix="cew-cmd-")) if dry_run else Path(saida)
    destino.mkdir(parents=True, exist_ok=True)
    args = []
    for parte in c["comando"]:
        p = parte.replace("{entrada}", str(entrada)).replace("{saida}", str(destino)).replace("{python}", sys.executable)
        p = p.replace("{projeto}", str(projeto_pasta or ""))
        while "{saida_arquivo:" in p:
            i = p.index("{saida_arquivo:")
            j = p.index("}", i)
            p = p[:i] + str(destino / p[i + 15 : j]) + p[j + 1 :]
        while "{opcao:" in p:
            i = p.index("{opcao:")
            j = p.index("}", i)
            nome = p[i + 7 : j]
            if nome not in opc:
                return _resultado_falha(ref, entrada, dry_run, f"opcao '{nome}' exigida pelo comando nao informada")
            p = p[:i] + str(opc[nome]) + p[j + 1 :]
        args.append(p)
    if not shutil.which(args[0]) and not Path(args[0]).is_file():
        return _resultado_falha(ref, entrada, dry_run, f"ferramenta nao encontrada: {args[0]} (instale ou ajuste o caminho no conversor)")
    try:
        pr = subprocess.run(args, capture_output=True, text=True, timeout=float(c.get("tempo_limite_s", config_cew()["harness"]["tempo_limite_s"])),
                            cwd=str(projeto_pasta or destino))
    except subprocess.TimeoutExpired:
        return _resultado_falha(ref, entrada, dry_run, "tempo limite excedido")
    if pr.returncode not in c.get("codigos_ok", [0]):
        return _resultado_falha(ref, entrada, dry_run, f"comando saiu com {pr.returncode}: {(pr.stderr or pr.stdout)[-800:]}")
    saidas, faltas = [], []
    for s in c["saidas"]:
        achados = sorted(p for p in destino.rglob("*") if p.is_file() and fnmatch.fnmatch(p.relative_to(destino).as_posix(), s["padrao"]))
        if not achados and s.get("obrigatoria", True):
            faltas.append(s["padrao"])
        for a in achados:
            dados = a.read_bytes()
            item: dict[str, Any] = {"caminho": a.relative_to(destino).as_posix(), "tipo": s["tipo"], "formato": s["formato"],
                                    "sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados)}
            meta = _metadados_auto(a, s["formato"])
            if meta:
                item["metadados"] = meta
            saidas.append(item)
    if dry_run:
        shutil.rmtree(destino, ignore_errors=True)
    if faltas:
        return _resultado_falha(ref, entrada, dry_run, f"saidas esperadas nao apareceram: {faltas}")
    dados = entrada.read_bytes()
    r = {"schema_version": "1.0", "gerado_por": "cew-conversor", "conversor": ref.texto, "versao_conversor": c.get("versao", "1.0"),
         "entrada": {"caminho": entrada.name, "sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados)},
         "dry_run": dry_run, "ok": True, "erro": None, "saidas": saidas, "avisos": [l for l in pr.stderr.splitlines()[-5:] if l.strip()]}
    validar(r, "conversor_resultado")
    return r


def _limites(mem_mb: int, cpu_s: int):
    def aplicar() -> None:
        import resource

        mem = mem_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (mem, mem))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))

    return aplicar


def _rodar_subprocesso(ref: Ref, entrada: Path, saida: Path, opcoes: dict, dry_run: bool) -> dict:
    h = config_cew()["harness"]
    pedido = json.dumps({"caminho": str(ref.caminho), "ref": ref.texto, "entrada": str(entrada), "saida": str(saida), "opcoes": opcoes, "dry_run": dry_run})
    kwargs: dict[str, Any] = {"capture_output": True, "text": True, "cwd": str(raiz_repositorio())}
    if os.name == "posix":
        kwargs["preexec_fn"] = _limites(int(h["memoria_mb"]), int(h["tempo_limite_s"]) + 5)
    try:
        p = subprocess.run([sys.executable, "-m", "cew._executor"], input=pedido, timeout=float(h["tempo_limite_s"]), **kwargs)
    except subprocess.TimeoutExpired:
        return _resultado_falha(ref, entrada, dry_run, f"tempo limite de {h['tempo_limite_s']} s excedido (laco infinito ou arquivo grande demais?)")
    try:
        r = json.loads(p.stdout.strip().splitlines()[-1])
        validar(r, "conversor_resultado")
        return r
    except (ValueError, IndexError):
        motivo = "memoria esgotada" if "MemoryError" in p.stderr else f"processo saiu com {p.returncode}"
        return _resultado_falha(ref, entrada, dry_run, f"falha inesperada (bug do conversor): {motivo}: {p.stderr[-800:]}")


def rodar(ref_texto: str, entrada: Path, saida: Path, opcoes: dict | None = None, dry_run: bool = False, projeto_pasta: Path | None = None) -> dict:
    ref = resolver(ref_texto, projeto_pasta)
    if not ref.caminho.is_file():
        raise ErroConversor(f"conversor nao encontrado: {ref.caminho}")
    entrada, saida, opcoes = Path(entrada), Path(saida), opcoes or {}
    if ref.tipo == "comando":
        return _rodar_comando(ref, entrada, saida, opcoes, dry_run, projeto_pasta)
    if ref.do_projeto and config_cew()["executar_conversores_do_projeto_em"] == "subprocesso":
        return _rodar_subprocesso(ref, entrada, saida, opcoes, dry_run)
    from converters.comum.cli import rodar as _rodar

    mod = _modulo_arquivo(ref.caminho) if ref.do_projeto else _modulo_repo(ref)
    info_ = dict(mod.INFO)
    info_["arquivo"] = ref.texto
    return _rodar(info_, mod.converter, entrada, saida, opcoes, dry_run)


# --------------------------------------------------------------------------- catalogo
@lru_cache(maxsize=1)
def _catalogo_repo() -> tuple:
    raiz = raiz_repositorio()
    saida = []
    for base in ("converters", "cookbook"):
        for arq in sorted((raiz / base).glob("*/*.py")):
            if arq.parent.name == "comum" or arq.name == "__init__.py":
                continue
            saida.append(info(arq.relative_to(raiz).as_posix()))
    return tuple(saida)


def listar(projeto_pasta: Path | None = None) -> list[dict[str, Any]]:
    saida = [dict(i, fonte="cookbook" if i["arquivo"].startswith("cookbook/") else "generico") for i in _catalogo_repo()]
    if projeto_pasta and (Path(projeto_pasta) / "conversores").is_dir():
        for arq in sorted((Path(projeto_pasta) / "conversores").rglob("*")):
            if arq.suffix not in (".py", ".json") or arq.name.endswith(".teste.json") or arq.name.startswith(("test_", "_")) or "__pycache__" in arq.parts:
                continue
            ref = PREFIXO_PROJETO + arq.relative_to(projeto_pasta).as_posix()
            try:
                saida.append(dict(info(ref, projeto_pasta), fonte="projeto"))
            except Exception as e:  # noqa: BLE001 - conversor em construcao nao quebra a listagem
                saida.append({"arquivo": ref, "fonte": "projeto", "erro": str(e)[:300], "formatos_entrada": [], "destino": "?", "descricao": "(invalido)", "papel": "?"})
    return saida


def fonte_de(ref: str) -> str:
    return "projeto" if ref.startswith(PREFIXO_PROJETO) else ("cookbook" if ref.startswith("cookbook/") else "generico")


def escolher(fmt_global: dict | None, fmt_projeto: dict | None, fontes: list[str] | None = None) -> dict:
    """Decide o conversor de um formato pela cadeia de fontes. Devolve ref, fonte, cobertura e decisao."""
    fontes = fontes or config_cew()["fontes_conversores"]
    decisao = (fmt_projeto or {}).get("decisao")
    if decisao and decisao["acao"] in ("ignorar", "substituir"):
        return {"ref": None, "fonte": None, "cobertura": "ignorado", "decisao": decisao}
    if decisao and decisao["acao"] == "bloqueado":
        return {"ref": None, "fonte": None, "cobertura": "bloqueado", "decisao": decisao}
    candidatos = []
    if fmt_projeto and fmt_projeto.get("conversor"):
        candidatos.append(fmt_projeto["conversor"])
    if fmt_global and fmt_global.get("conversor"):
        candidatos.append(fmt_global["conversor"])
    for fonte in fontes:
        for c in candidatos:
            if fonte_de(c) == fonte:
                return {"ref": c, "fonte": fonte, "cobertura": "coberto", "decisao": decisao}
    return {"ref": None, "fonte": None, "cobertura": "falta_conversor", "decisao": decisao}


def limpar_caches() -> None:
    config_cew.cache_clear()
    _catalogo_repo.cache_clear()
