"""Kit para o agente da pessoa criar conversores no projeto (skill 04).

- novo_conversor: esqueleto Python ou declaracao de comando em projects/<p>/conversores/
- testar: harness (executa, esquema, determinismo, robustez, dry-run, ajuda, tempo/memoria) -> .teste.json
- registrar_formato: entrada no registro do projeto (projects/<p>/formatos.json), inclusive decisoes
- copiar_do_cookbook: traz uma receita para o projeto, para adaptar
- registrar_log: uma linha em log_conversores.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import raiz_repositorio, slug
from .conversores import PREFIXO_PROJETO, Ref, config_cew, hash_codigo, info, ler_comando, resolver, rodar
from .esquemas import gravar_json, ler_json, validar
from .logs import agora_iso
from .projeto import Projeto

CABECALHO_IMPORT = '''if __package__ in (None, ""):  # roda direto: acha a raiz do CEW (pasta com converters/comum) ou usa CEW_RAIZ
    import os, pathlib, sys
    _raiz = os.environ.get("CEW_RAIZ") or next((str(p) for p in pathlib.Path(__file__).resolve().parents if (p / "converters" / "comum").is_dir()), None)
    if _raiz and _raiz not in sys.path:
        sys.path.insert(0, _raiz)
'''

MODELO_PYTHON = '''"""{formato} -> {destino}. Conversor do projeto {projeto}, escrito pelo agente (skill 04).

Fontes consultadas (preencha; a regra de ouro exige fonte real):
- ...
Estrutura (offset, tipo, campo) em especificacoes/{formato}.md.
"""

from __future__ import annotations

{cabecalho}
from converters.comum.binario import ErroFormato, LeitorBinario, contagem_plausivel, exigir, limitar_tamanho
from converters.comum.cli import Escritor, executar

INFO = {{
    "arquivo": "{ref}",
    "descricao": "Converte {formato} em {destino}.",
    "formatos_entrada": ["{formato}"],
    "destino": "{destino}",
    "versao": "0.1",
    "papel": "{papel}",
}}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    r = LeitorBinario(dados, "little")  # ou "big": confirme na especificacao
    # 1) confira a assinatura e os tamanhos ANTES de ler (leitura defensiva):
    # exigir(r.bytes_em(0, 4) == b"MAGC", "assinatura ausente")
    # n = contagem_plausivel(r.u32_em(4), 16, len(dados) - 8, "entradas")
    # 2) decodifique e grave cada saida com o tipo e os metadados do manifesto:
    # esc.gravar("textura.png", png_bytes(img), "textura", "png", img.metadados("srgb"))
    raise ErroFormato("conversor ainda nao implementado")


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
'''

TIPOS_SAIDA = {"png": "textura", "webp": "textura", "ktx2": "textura", "glb": "modelo", "ogg": "audio", "wav": "audio", "mp3": "audio", "json": "dados", "pasta": "arquivo_extraido"}


def _ref_projeto(projeto: Projeto, arq: Path) -> str:
    return PREFIXO_PROJETO + arq.relative_to(projeto.pasta).as_posix()


def novo_conversor(projeto: Projeto, formato_id: str, tipo: str = "python", destino: str = "png", nome: str | None = None, papel: str | None = None) -> Path:
    if not re.match(r"^[a-z0-9_]+(\.[a-z0-9_]+)+$", formato_id):
        raise ValueError("formato_id no padrao empresa.familia.nome (minusculas)")
    partes = formato_id.split(".")
    familia = slug(partes[0]).replace("-", "_")
    base = nome or f"{'_'.join(partes[1:])}_to_{'dir' if destino == 'pasta' else destino}"
    base = re.sub(r"[^a-z0-9_]", "_", base.lower())
    pasta = projeto.pasta / "conversores" / familia
    pasta.mkdir(parents=True, exist_ok=True)
    papel = papel or ("extrator" if destino == "pasta" else "conversor")
    if tipo == "python":
        arq = pasta / f"{base}.py"
        if arq.exists():
            raise FileExistsError(arq)
        arq.write_text(MODELO_PYTHON.format(formato=formato_id, destino=destino, projeto=projeto.nome, ref=_ref_projeto(projeto, arq), papel=papel, cabecalho=CABECALHO_IMPORT), encoding="utf-8")
    elif tipo == "comando":
        arq = pasta / f"{base}.json"
        if arq.exists():
            raise FileExistsError(arq)
        doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "tipo": "comando", "descricao": f"Converte {formato_id} em {destino} com uma ferramenta externa.",
               "formatos_entrada": [formato_id], "destino": destino, "papel": papel, "versao": "0.1",
               "ferramenta": {"nome": "TROQUE-PELA-FERRAMENTA", "verificar": ["TROQUE-PELA-FERRAMENTA", "--version"]},
               "comando": ["TROQUE-PELA-FERRAMENTA", "{entrada}", "-o", "{saida_arquivo:saida." + ("bin" if destino == "pasta" else destino) + "}"],
               "tempo_limite_s": 120, "saidas": [{"padrao": "*" if destino == "pasta" else f"*.{destino}", "tipo": TIPOS_SAIDA.get(destino, "outro"), "formato": destino, "obrigatoria": True}]}
        validar(doc, "conversor_comando")
        arq.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        raise ValueError("tipo: python ou comando")
    (pasta / "amostras").mkdir(exist_ok=True)
    registrar_log(projeto, formato_id, "escrever", "info", _ref_projeto(projeto, arq), f"esqueleto {tipo} criado")
    return arq


# ------------------------------------------------------------------------------- log
def registrar_log(projeto: Projeto, formato: str, passo: str, resultado: str, conversor: str | None = None, detalhes: str = "",
                  evidencia: list[str] | None = None, tentativa: int | None = None) -> dict:
    linha: dict[str, Any] = {"ts": agora_iso(), "formato": formato, "passo": passo, "resultado": resultado, "conversor": conversor, "detalhes": detalhes}
    if evidencia:
        linha["evidencia"] = evidencia
    if tentativa is not None:
        linha["tentativa"] = tentativa
    validar(linha, "log_conversor")
    with open(projeto.pasta / "log_conversores.jsonl", "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(linha, ensure_ascii=False) + "\n")
    return linha


# --------------------------------------------------------------------- registro do projeto
def _ler_registro_projeto(projeto: Projeto) -> dict:
    arq = projeto.pasta / "formatos.json"
    if arq.is_file():
        return ler_json(arq, "registry")
    return {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "observacoes": "Registro do projeto: completa ou substitui formats/registry.json.", "formatos": []}


def registrar_formato(projeto: Projeto, formato_id: str, **campos: Any) -> dict:
    """Cria ou atualiza a entrada do formato no registro do projeto.

    Campos: empresa_ou_motor, extensoes, assinatura_hex, assinatura_offset, ordem_de_bytes, tipo,
    destino, conversor, decisao (converter|ignorar|substituir|bloqueado), motivo, documentacao,
    confianca, observacoes, verificador_estrutura.
    """
    from .registro import registro_padrao

    doc = _ler_registro_projeto(projeto)
    atual = next((f for f in doc["formatos"] if f["id"] == formato_id), None)
    if atual is None:
        g = registro_padrao().global_por_id.get(formato_id)
        atual = json.loads(json.dumps(g)) if g else {
            "id": formato_id, "empresa_ou_motor": "desconhecida", "extensoes": [], "assinatura": None, "verificador_estrutura": None,
            "ordem_de_bytes": "desconhecida", "tipo": "dados", "contem": [], "compressao_comum": [], "destino_web": {}, "ferramentas_conhecidas": [],
            "conversor": None, "documentacao": [], "confianca": "hipotese", "verificacao": {"estado": "a_verificar"}, "observacoes": "registrado pelo agente no projeto"}
        doc["formatos"].append(atual)
    mapa = {"empresa_ou_motor": "empresa_ou_motor", "ordem_de_bytes": "ordem_de_bytes", "tipo": "tipo", "conversor": "conversor",
            "confianca": "confianca", "observacoes": "observacoes", "verificador_estrutura": "verificador_estrutura"}
    for k, destino in mapa.items():
        if campos.get(k) is not None:
            atual[destino] = campos[k]
    if campos.get("extensoes"):
        atual["extensoes"] = sorted({e.lower() if e.startswith(".") else "." + e.lower() for e in campos["extensoes"]})
    if campos.get("assinatura_hex"):
        h = campos["assinatura_hex"].lower().replace(" ", "")
        txt = bytes.fromhex(h).decode("latin-1")
        atual["assinatura"] = {"offset": int(campos.get("assinatura_offset") or 0), "bytes_hex": h, "texto": txt if txt.isprintable() else None}
    if campos.get("destino"):
        atual["destino_web"] = {atual["tipo"]: campos["destino"]}
    if campos.get("documentacao"):
        atual["documentacao"] = sorted(set(atual.get("documentacao", [])) | set(campos["documentacao"]))
    if campos.get("decisao"):
        atual["decisao"] = {"acao": campos["decisao"], "motivo": campos.get("motivo") or "sem motivo informado", "em": agora_iso(), "por": "agente"}
    if campos.get("tentativas") is not None:
        atual["tentativas"] = int(campos["tentativas"])
    if atual.get("conversor"):
        resolver(atual["conversor"], projeto.pasta)  # recusa referencia invalida
    validar(doc, "registry")
    gravar_json(projeto.pasta / "formatos.json", doc, "registry")
    passo = "decidir" if campos.get("decisao") else "registrar"
    registrar_log(projeto, formato_id, passo, "ok", atual.get("conversor"), campos.get("motivo") or json.dumps({k: v for k, v in campos.items() if v is not None}, ensure_ascii=False)[:500])
    return atual


# --------------------------------------------------------------------------- cookbook
def copiar_do_cookbook(projeto: Projeto, ref_cookbook: str) -> Path:
    r = resolver(ref_cookbook)
    if r.fonte not in ("cookbook", "generico"):
        raise ValueError("copie de cookbook/... ou converters/...")
    familia, nome = PurePosixPath(r.texto).parts[1], PurePosixPath(r.texto).name
    destino = projeto.pasta / "conversores" / familia / nome
    if destino.exists():
        raise FileExistsError(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = r.caminho.read_text(encoding="utf-8")
    texto = re.sub(r'if __package__ in \(None, ""\):.*?\n(?=\n)', lambda _m: CABECALHO_IMPORT.rstrip("\n"), texto, count=1, flags=re.S)
    novo_ref = _ref_projeto(projeto, destino)
    texto = texto.replace(f'"arquivo": "{r.texto}"', f'"arquivo": "{novo_ref}"')
    destino.write_text(texto, encoding="utf-8")
    for fid in info(r.texto).get("formatos_entrada", []):
        registrar_log(projeto, fid, "escrever", "info", novo_ref, f"copiado de {r.texto} para adaptar")
    return destino


# ----------------------------------------------------------------------------- harness
def _amostras_padrao(projeto: Projeto, formatos: list[str], limite: int = 5) -> list[tuple[Path, str]]:
    """Amostras reais do inventario (menor, maior e intermediarias) + sinteticas em conversores/**/amostras/."""
    saida: list[tuple[Path, str]] = []
    if projeto.existe("inventario"):
        inv = projeto.ler("inventario")
        alvo = Path(inv["alvo"]["caminho"])
        from .registro import registro_do_projeto

        reg = registro_do_projeto(projeto.pasta)
        exts = {e for f in formatos for e in (reg.get(f) or {}).get("extensoes", [])}
        # pelo id ja identificado OU pela extensao registrada (formato recem-registrado, inventario ainda antigo)
        itens = sorted((i for i in inv["itens"] if i["formato"]["id"] in formatos or PurePosixPath(i["caminho"].split("!/")[-1]).suffix.lower() in exts),
                       key=lambda i: i["tamanho_bytes"])
        vistos = set()
        escolha = itens if len(itens) <= limite else [itens[round(k * (len(itens) - 1) / (limite - 1))] for k in range(limite)]
        for i in escolha:
            if i["sha256"] in vistos:
                continue
            vistos.add(i["sha256"])
            disco = (alvo if alvo.is_file() else alvo / i["caminho_no_disco"]) if i["origem"] == "alvo" else projeto.pasta / i["caminho_no_disco"]
            if disco.is_file():
                saida.append((disco, "real"))
    for pasta in (projeto.pasta / "referencias" / "amostras",):
        if pasta.is_dir():
            saida += [(p, "real") for p in sorted(pasta.iterdir()) if p.is_file()]
    return saida


def _amostras_sinteticas(projeto: Projeto, ref: Ref, formatos: list[str]) -> list[tuple[Path, str]]:
    """conversores/<familia>/amostras/<nome do conversor>/* e, filtrados pela extensao do formato, amostras/*."""
    from .registro import registro_do_projeto

    reg = registro_do_projeto(projeto.pasta)
    exts = {e for f in formatos for e in (reg.get(f) or {}).get("extensoes", [])}
    base = ref.caminho.parent / "amostras"
    saida: list[tuple[Path, str]] = []
    propria = base / ref.caminho.stem
    if propria.is_dir():
        saida += [(p, "sintetica") for p in sorted(propria.iterdir()) if p.is_file()]
    if base.is_dir():
        saida += [(p, "sintetica") for p in sorted(base.iterdir()) if p.is_file() and (not exts or p.suffix.lower() in exts)]
    return saida


def _variantes(dados: bytes, n: int, semente: int) -> list[bytes]:
    rnd = random.Random(semente)
    cortes = sorted({0, 1, 4, 16, len(dados) // 2, max(0, len(dados) - 1)})
    vs = [dados[:c] for c in cortes if c < len(dados)]
    for _ in range(max(0, n - len(vs))):
        b = bytearray(dados)
        if not b:
            break
        for _ in range(rnd.randint(1, 8)):
            b[rnd.randrange(len(b))] = rnd.randrange(256)
        vs.append(bytes(b))
    return vs[: max(n, len(cortes))]


def testar(projeto: Projeto, ref_texto: str, entradas: list[Path] | None = None, fontes: list[str] | None = None) -> dict:
    ref = resolver(ref_texto, projeto.pasta)
    inf = info(ref)
    h = config_cew()["harness"]
    amostras: list[tuple[Path, str]] = []
    if entradas:
        amostras += [(Path(e), "real") for e in entradas]
    else:
        amostras += _amostras_padrao(projeto, inf.get("formatos_entrada", []))
    amostras += _amostras_sinteticas(projeto, ref, inf.get("formatos_entrada", []))
    if not amostras:
        raise ValueError("nenhuma amostra: passe --entrada, rode o inventario ou ponha amostras sinteticas em conversores/<familia>/amostras/")
    verif: list[dict] = []
    res_amostras = []
    tempo_ok = True
    with tempfile.TemporaryDirectory(prefix="cew-harness-") as tmp:
        tmp = Path(tmp)
        execucoes_ok, determinismo_ok, esquema_ok = True, True, True
        detalhes_det = []
        for k, (arq, origem) in enumerate(amostras):
            import time

            t0 = time.monotonic()
            try:
                a = rodar(ref.texto, arq, tmp / f"a{k}", {}, False, projeto.pasta)
                b = rodar(ref.texto, arq, tmp / f"b{k}", {}, False, projeto.pasta)
            except Exception as e:  # noqa: BLE001 - resultado fora do esquema
                esquema_ok = False
                res_amostras.append({"caminho": str(arq), "sha256": hashlib.sha256(arq.read_bytes()).hexdigest(), "origem": origem, "ok": False, "erro": f"resultado invalido: {e}"[:500]})
                continue
            dt = time.monotonic() - t0
            if a.get("erro") and "tempo limite" in a["erro"]:
                tempo_ok = False
            execucoes_ok &= a["ok"]
            ha = [(s["caminho"], s.get("sha256")) for s in a["saidas"]]
            hb = [(s["caminho"], s.get("sha256")) for s in b["saidas"]]
            if ha != hb:
                determinismo_ok = False
                detalhes_det.append(arq.name)
            res_amostras.append({"caminho": str(arq), "sha256": a["entrada"]["sha256"], "origem": origem, "ok": a["ok"], "saidas": len(a["saidas"]), "erro": a["erro"], "tempo_s": round(dt, 3)})
        verif.append({"id": "executa", "aprovado": execucoes_ok, "detalhes": f"{sum(r['ok'] for r in res_amostras)}/{len(res_amostras)} amostras convertidas"})
        verif.append({"id": "esquema", "aprovado": esquema_ok, "detalhes": "resultado valido em schemas/conversor_resultado.schema.json" if esquema_ok else "resultado fora do esquema"})
        verif.append({"id": "determinismo", "aprovado": determinismo_ok, "detalhes": "mesmos SHA-256 em duas execucoes" if determinismo_ok else f"saidas diferentes em: {detalhes_det}"})
        base = next((a for a, _ in amostras if a.stat().st_size > 0), amostras[0][0])
        quebras = []
        for k, v in enumerate(_variantes(base.read_bytes(), int(h["variantes_corrompidas"]), int(h.get("semente", 1234)))):
            arq = tmp / f"corrompido_{k}{base.suffix}"
            arq.write_bytes(v)
            r = rodar(ref.texto, arq, tmp / f"c{k}", {}, False, projeto.pasta)
            if not r["ok"] and r["erro"] and (r["erro"].startswith("falha inesperada") or "tempo limite" in r["erro"]):
                quebras.append(f"variante {k}: {r['erro'][:160]}")
                if "tempo limite" in r["erro"]:
                    tempo_ok = False
        robustez_ok = not quebras or ref.tipo == "comando" and all("tempo limite" not in q for q in quebras)
        verif.append({"id": "robustez", "aprovado": robustez_ok, "detalhes": "arquivos truncados/corrompidos terminam com erro de formato limpo" if not quebras else "; ".join(quebras[:4])})
        destino_seco = tmp / "seco"
        r = rodar(ref.texto, amostras[0][0], destino_seco, {}, True, projeto.pasta)
        seco_ok = r["dry_run"] is True and not destino_seco.exists()
        verif.append({"id": "dry_run", "aprovado": seco_ok, "detalhes": "dry-run nao grava nada" if seco_ok else "dry-run gravou arquivos"})
    if ref.tipo == "python":
        env = {**os.environ, "CEW_RAIZ": str(raiz_repositorio())}
        p = subprocess.run([sys.executable, str(ref.caminho), "--help"], capture_output=True, text=True, timeout=60, env=env)
        ajuda_ok = p.returncode == 0 and "--dry-run" in p.stdout
        verif.append({"id": "ajuda", "aprovado": ajuda_ok, "detalhes": "--help mostra --dry-run" if ajuda_ok else (p.stderr or p.stdout)[-300:]})
    else:
        c = ler_comando(ref.caminho)
        cmd = (c.get("ferramenta") or {}).get("verificar") or [c["comando"][0], "--help"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            ajuda_ok = shutil.which(cmd[0]) is not None or Path(cmd[0]).is_file()
            det = (p.stdout or p.stderr).strip().splitlines()[0][:200] if (p.stdout or p.stderr).strip() else "ferramenta responde"
        except (OSError, subprocess.TimeoutExpired) as e:
            ajuda_ok, det = False, f"ferramenta nao executa: {e}"
        verif.append({"id": "ajuda", "aprovado": ajuda_ok, "detalhes": det})
    verif.append({"id": "tempo_memoria", "aprovado": tempo_ok, "detalhes": f"dentro de {h['tempo_limite_s']} s e {h['memoria_mb']} MB" if tempo_ok else "estourou o tempo limite"})
    aprovado = all(v["aprovado"] for v in verif)
    doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "conversor": ref.texto, "tipo": ref.tipo, "hash_codigo": hash_codigo(ref),
           "testado_em": agora_iso(), "aprovado": aprovado, "formatos_entrada": inf.get("formatos_entrada", []), "amostras": res_amostras, "verificacoes": verif}
    if ref.do_projeto:
        gravar_json(ref.caminho.with_name(ref.caminho.stem + ".teste.json"), doc, "conversor_projeto")
        for fid in inf.get("formatos_entrada", []):
            tent = _contar_tentativa(projeto, fid, aprovado)
            registrar_log(projeto, fid, "testar", "ok" if aprovado else "falhou", ref.texto,
                          "; ".join(f"{v['id']}={'ok' if v['aprovado'] else 'FALHOU'}" for v in verif), tentativa=tent)
    else:
        validar(doc, "conversor_projeto")
    return doc


def _contar_tentativa(projeto: Projeto, formato_id: str, aprovado: bool) -> int:
    """Soma tentativas reprovadas; no limite (config) o formato e marcado 'bloqueado' com o motivo."""
    from .registro import registro_padrao

    doc = _ler_registro_projeto(projeto)
    atual = next((f for f in doc["formatos"] if f["id"] == formato_id), None)
    if atual is None and formato_id not in registro_padrao().global_por_id:
        return 0
    n = int((atual or {}).get("tentativas", 0)) + (0 if aprovado else 1)
    if aprovado and atual is None:
        return n
    maximo = int(config_cew()["harness"]["max_tentativas_por_formato"])
    campos: dict[str, Any] = {"tentativas": n}
    if not aprovado and n >= maximo and not (atual or {}).get("decisao"):
        campos.update(decisao="bloqueado", motivo=f"limite de {maximo} tentativas do harness atingido; ver log_conversores.jsonl")
    registrar_formato(projeto, formato_id, **campos)
    return n


__all__ = ["novo_conversor", "testar", "registrar_formato", "copiar_do_cookbook", "registrar_log", "CABECALHO_IMPORT", "Ref"]
