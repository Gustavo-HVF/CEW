from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from cew.sandbox import executar_rascunho

RAIZ = Path(__file__).resolve().parents[1]

RASCUNHO = '''
from converters.comum.cli import executar
INFO = {"arquivo": "rascunho.py", "descricao": "teste", "formatos_entrada": ["x.y.z"], "destino": "json", "papel": "conversor"}
def converter(dados, esc, opcoes):
    import socket
    try:
        socket.socket()
        rede = "aberta"
    except OSError:
        rede = "bloqueada"
    esc.gravar("saida.json", ('{"rede": "%s", "magic": "%s"}' % (rede, dados[:4].decode())).encode(), "dados", "json")
if __name__ == "__main__":
    raise SystemExit(executar(INFO, converter))
'''


def test_sandbox_sem_rede_e_dry_run(tmp_path, amostras):
    r = executar_rascunho(RASCUNHO, tmp_path / "sb", amostras / "desconhecido/misterio.xyz", tempo_s=60)
    assert r.codigo_saida == 0, r.stderr
    saida = json.loads(r.stdout)
    assert saida["dry_run"] and saida["saidas"][0]["caminho"] == "saida.json"
    assert not (tmp_path / "sb" / "saida").exists()


def test_sandbox_tempo_limite(tmp_path):
    r = executar_rascunho("import time\ntime.sleep(30)\n", tmp_path / "sb2", None, tempo_s=2)
    assert r.tempo_esgotado


def test_sandbox_bloqueia_socket(tmp_path):
    codigo = "import socket\ntry:\n    socket.create_connection(('example.com', 80), 2)\n    print('ABERTA')\nexcept OSError:\n    print('BLOQUEADA')\n"
    r = executar_rascunho(codigo, tmp_path / "sb3", None, tempo_s=30)
    assert "BLOQUEADA" in r.stdout


def _mcp(msgs, env):
    p = subprocess.run([sys.executable, str(RAIZ / "scripts" / "mcp_server.py")], input="\n".join(json.dumps(m) for m in msgs) + "\n",
                       capture_output=True, text=True, env=env, timeout=120)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


def test_mcp_ferramentas(tmp_path, amostras):
    import os

    env = {**os.environ, "CEW_PROJETOS": str(tmp_path / "projects")}
    r = _mcp([
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "rodar_conversor", "arguments": {"conversor": "converters/sony/tim_to_png.py", "entrada": str(amostras / "sony/imagem4.tim")}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "rodar_conversor", "arguments": {"conversor": "converters/sony/tim_to_png.py", "entrada": str(amostras / "sony/imagem4.tim"), "saida": str(tmp_path / "fora")}}},
        {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "listar_projetos", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 6, "method": "nao/existe"},
    ], env)
    assert [x["id"] for x in r] == [1, 2, 3, 4, 5, 6]
    assert r[0]["result"]["serverInfo"]["name"] == "cew-mcp"
    assert {t["name"] for t in r[1]["result"]["tools"]} == {"listar_projetos", "estado_da_etapa", "rodar_conversor", "ver_manifesto"}
    assert r[2]["result"]["isError"] is False and json.loads(r[2]["result"]["content"][0]["text"])["ok"]
    assert (tmp_path / "projects" / "_mcp" / "imagem4.tim" / "imagem.png").is_file()
    assert r[3]["result"]["isError"] is True and not (tmp_path / "fora").exists()
    assert r[5]["error"]["code"] == -32601
