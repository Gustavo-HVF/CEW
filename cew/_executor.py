"""Executa UM conversor de projeto em processo separado (chamado por cew.conversores._rodar_subprocesso).

Le o pedido em JSON pela entrada padrao e imprime o resultado (schemas/conversor_resultado.schema.json)
na ultima linha da saida padrao. Excecoes viram resultado com ok=false.
"""

from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path


def main() -> int:
    pedido = json.loads(sys.stdin.read())
    from converters.comum.cli import rodar

    from .conversores import _modulo_arquivo

    try:
        mod = _modulo_arquivo(Path(pedido["caminho"]))
        info = dict(mod.INFO)
        info["arquivo"] = pedido["ref"]
        r = rodar(info, mod.converter, Path(pedido["entrada"]), Path(pedido["saida"]), pedido["opcoes"], pedido["dry_run"])
    except Exception as e:  # noqa: BLE001 - qualquer erro do codigo do agente vira resultado
        import hashlib

        dados = Path(pedido["entrada"]).read_bytes() if Path(pedido["entrada"]).is_file() else b""
        r = {"schema_version": "1.0", "gerado_por": "cew-conversor", "conversor": pedido["ref"],
             "entrada": {"caminho": Path(pedido["entrada"]).name, "sha256": hashlib.sha256(dados).hexdigest(), "tamanho_bytes": len(dados)},
             "dry_run": pedido["dry_run"], "ok": False, "erro": f"falha inesperada (bug do conversor): {type(e).__name__}: {e} | {traceback.format_exc()[-600:]}",
             "saidas": [], "avisos": []}
    sys.stdout.write("\n" + json.dumps(r, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
