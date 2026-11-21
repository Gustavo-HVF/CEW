"""Tabela de textos (Shift-JIS, UTF-16, Latin-1...) -> dados/dialogos.json (UTF-8, com esquema).

Entrada: strings separadas por zero (padrao) ou por linha. Codigos de controle viram marcacoes
"{nome}" listadas em "marcacoes" (schemas/dados/dialogos.schema.json).
"""

from __future__ import annotations

if __package__ in (None, ""):
    import pathlib, sys
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

import json

from converters.comum.binario import ErroFormato
from converters.comum.cli import Escritor, executar
from converters.comum.texto import decodificar, separar_por_zero

INFO = {
    "arquivo": "converters/dados/texto_to_json.py",
    "descricao": "Converte tabelas de texto (Shift-JIS e outras) para JSON UTF-8 com marcacoes documentadas.",
    "formatos_entrada": ["generico.tabela_texto"],
    "destino": "json (dados/dialogos)",
    "versao": "1.0",
    "papel": "conversor",
    "epilogo": "Opcoes: {\"codificacao\": \"shift_jis\", \"separador\": \"zero\"|\"linha\", \"controles\": {\"0x01\": [\"{cor_vermelha}\", \"troca a cor\"]}, \"prefixo_id\": \"fala\"}.",
}


def converter(dados: bytes, esc: Escritor, opcoes: dict) -> dict:
    cod = opcoes.get("codificacao", "shift_jis")
    passo = 2 if cod.lower().startswith("utf-16") else 1
    controles = {int(k, 16): (v[0], v[1]) for k, v in (opcoes.get("controles") or {}).items()}
    if opcoes.get("separador", "zero") == "linha":
        partes, pos = [], 0
        for linha in dados.split(b"\n"):
            if linha.strip(b"\r"):
                partes.append((pos, linha.rstrip(b"\r")))
            pos += len(linha) + 1
    else:
        partes = separar_por_zero(dados, passo)
    if not partes:
        raise ErroFormato("nenhum texto encontrado")
    prefixo = opcoes.get("prefixo_id", "linha")
    marcacoes: dict[str, str] = {}
    linhas = []
    for i, (off, b) in enumerate(partes):
        texto, usadas = decodificar(b, cod, controles)
        marcacoes.update(usadas)
        linhas.append({"id": f"{prefixo}_{i:05d}", "falante_id": None, "texto": texto, "offset_original": off})
    doc = {"schema_version": "1.0", "gerado_por": "cew", "origem": opcoes.get("origem", "tabela de texto"),
           "codificacao_original": cod, "marcacoes": dict(sorted(marcacoes.items())), "linhas": linhas}
    try:
        from cew.esquemas import validar
        validar(doc, "dados/dialogos")
    except ImportError:  # pragma: no cover
        pass
    esc.gravar("dialogos.json", (json.dumps(doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8"), "dados", "json", {"extras": {"linhas": len(linhas)}})
    return {"linhas": len(linhas), "marcacoes": len(marcacoes)}


if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
