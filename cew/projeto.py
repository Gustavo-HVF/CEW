"""Projeto do CEW: pastas do Craft Anything + pastas e JSONs do CEW, e o estado (retomar).

projects/<nome>/
  craft.json, capture/, app/, checks/, investigation.cany/, inbox/   <- estrutura do Craft Anything
  cew.json                                                           <- liga as pastas do CEW (caminhos relativos)
  estado.json, inventario.json, plano_conversao.json, asset_manifest.json,
  recomendacao_motor.json, relatorio_verificacao.json
  analise/  especificacoes/  tarefas_gemini/  rascunhos/  referencias/  build/  web/
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import GERADO_POR, SCHEMA_VERSION
from .caminhos import nome_projeto_valido, pasta_projetos
from .esquemas import gravar_json, ler_json, validar
from .logs import agora_iso

ETAPAS = ["ambiente", "alvo", "inventario", "engenharia", "conversao", "motor", "reconstrucao", "verificacao", "pronto"]
FASE_CRAFT = {
    "ambiente": "estudar", "alvo": "estudar", "inventario": "estudar", "engenharia": "estudar",
    "conversao": "construir", "motor": "construir", "reconstrucao": "construir",
    "verificacao": "verificar", "pronto": "pronto",
}
CRITERIOS = {
    "ambiente": "reports/ambiente.json sem obrigatorios faltando e teste do Gemini ok",
    "alvo": "arquivo ou pasta alvo selecionado e acessivel",
    "inventario": "inventario.json valido e mapeado",
    "engenharia": "especificacao com evidencia para cada formato que sera convertido",
    "conversao": "plano_conversao.json sem itens em erro e conversores com testes passando",
    "motor": "motor escolhido e registrado em recomendacao_motor.json",
    "reconstrucao": "projeto web gerado em app/ carregando asset_manifest.json",
    "verificacao": "relatorio_verificacao.json aprovado e build web validado",
    "pronto": "tudo aprovado",
}
PASTAS_CRAFT = ["capture", "app", "checks", "investigation.cany", "inbox"]
PASTAS_CEW = {
    "analise": "analise", "especificacoes": "especificacoes", "tarefas_gemini": "tarefas_gemini", "rascunhos": "rascunhos",
    "referencias": "referencias", "extraido": "build/extraido", "convertido": "build/convertido", "web": "web",
    "dados": "web/dados", "logs_conversao": "build/logs", "conversores": "conversores",
}
ARQUIVOS = {
    "estado": ("estado.json", "estado"), "inventario": ("inventario.json", "inventario"),
    "plano": ("plano_conversao.json", "plano_conversao"), "manifesto": ("web/asset_manifest.json", "asset_manifest"),
    "motor": ("recomendacao_motor.json", "recomendacao_motor"), "verificacao": ("relatorio_verificacao.json", "relatorio_verificacao"),
    "hipoteses": ("analise/hipoteses.json", "hipoteses_formato"), "contexto": ("analise/contexto.json", "contexto_formatos"),
    "formatos": ("formatos.json", "registry"), "marcos": ("marcos.json", "marcos"), "cobertura": ("cobertura_conteudo.json", "cobertura_conteudo"),
}


@dataclass
class Projeto:
    nome: str
    pasta: Path

    # ----------------------------------------------------------------------- criacao/abertura
    @classmethod
    def abrir(cls, nome: str, criar: bool = True, base: Path | None = None) -> "Projeto":
        nome = nome_projeto_valido(nome)
        pasta = (base or pasta_projetos()) / nome
        p = cls(nome, pasta)
        if not (pasta / "estado.json").is_file():
            if not criar:
                raise FileNotFoundError(f"projeto {nome} nao existe em {pasta}")
            p._criar()
        return p

    def _criar(self) -> None:
        for d in PASTAS_CRAFT:
            (self.pasta / d).mkdir(parents=True, exist_ok=True)
        for d in PASTAS_CEW.values():
            (self.pasta / d).mkdir(parents=True, exist_ok=True)
        agora = agora_iso()
        gravar_json(self.pasta / "cew.json", {
            "schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": self.nome, "criado_em": agora,
            "craft_anything": {"manifesto": "craft.json", "pastas": PASTAS_CRAFT, "investigacao": "investigation.cany", "modo": "deep"},
            "caminhos": {**PASTAS_CEW, **{k: v[0] for k, v in ARQUIVOS.items()}},
        }, "cew_projeto")
        if not (self.pasta / "craft.json").is_file():
            self.gravar_craft_json(request="Converter os recursos para a web com o CEW", alvo=None)
        estado = {
            "schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": self.nome, "criado_em": agora, "atualizado_em": agora,
            "etapa_atual": "ambiente", "fase_craft_anything": "estudar",
            "etapas": {e: {"estado": "pendente", "criterio_saida": CRITERIOS[e]} for e in ETAPAS},
            "alvo": None, "motor_escolhido": None, "historico": [],
        }
        gravar_json(self.pasta / "estado.json", estado, "estado")

    def gravar_craft_json(self, request: str, alvo: str | None) -> None:
        """craft.json minimo no formato do Craft Anything (versao 5, validado contra o esquema publicado)."""
        agora_ms = int(time.time() * 1000)
        atual = {}
        if (self.pasta / "craft.json").is_file():
            atual = json.loads((self.pasta / "craft.json").read_text(encoding="utf-8"))
        doc = dict(atual)
        doc.update({
            "version": 5, "name": self.nome, "request": atual.get("request", request),
            "target": {"kind": "local", "path": alvo} if alvo else atual.get("target", {"kind": "none"}),
            "created_ms": atual.get("created_ms", agora_ms), "updated_ms": agora_ms, "status": atual.get("status", "new"),
        })
        validar_craft_json(doc)
        (self.pasta / "craft.json").write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # ----------------------------------------------------------------------------- JSONs
    def caminho(self, chave: str) -> Path:
        if chave in ARQUIVOS:
            return self.pasta / ARQUIVOS[chave][0]
        return self.pasta / PASTAS_CEW[chave]

    def ler(self, chave: str) -> Any:
        rel, esquema = ARQUIVOS[chave]
        return ler_json(self.pasta / rel, esquema)

    def existe(self, chave: str) -> bool:
        return self.caminho(chave).is_file()

    def gravar(self, chave: str, dados: Any) -> Path:
        rel, esquema = ARQUIVOS[chave]
        return gravar_json(self.pasta / rel, dados, esquema)

    # ----------------------------------------------------------------------------- estado
    def estado(self) -> dict:
        return self.ler("estado")

    def marcar(self, etapa: str, estado: str, mensagem: str = "", saidas: list[str] | None = None, dry_run: bool = False) -> dict:
        if etapa not in ETAPAS:
            raise ValueError(etapa)
        st = self.estado()
        agora = agora_iso()
        e = st["etapas"].setdefault(etapa, {"estado": "pendente"})
        if dry_run:
            st["historico"].append({"ts": agora, "etapa": etapa, "evento": f"[dry-run] {estado}: {mensagem}", "dry_run": True})
        else:
            e["estado"] = estado
            if estado == "em_andamento":
                e["iniciada_em"] = agora
            if estado == "concluida":
                e["concluida_em"] = agora
            if mensagem:
                e["mensagem"] = mensagem
            if saidas is not None:
                e["saidas"] = saidas
            st["historico"].append({"ts": agora, "etapa": etapa, "evento": f"{estado}: {mensagem}".strip(": ")})
            if estado == "concluida":
                proxima = ETAPAS[min(len(ETAPAS) - 1, ETAPAS.index(etapa) + 1)]
                if ETAPAS.index(proxima) > ETAPAS.index(st["etapa_atual"]):
                    st["etapa_atual"] = proxima
            elif estado in ("em_andamento", "erro", "bloqueada"):
                st["etapa_atual"] = etapa
            st["fase_craft_anything"] = FASE_CRAFT[st["etapa_atual"]]
        st["historico"] = st["historico"][-500:]
        st["atualizado_em"] = agora
        self.gravar("estado", st)
        return st

    def definir_alvo(self, caminho: Path) -> None:
        caminho = Path(caminho).resolve()
        st = self.estado()
        st["alvo"] = {"caminho": str(caminho), "tipo": "pasta" if caminho.is_dir() else "arquivo", "selecionado_em": agora_iso()}
        self.gravar("estado", st)
        self.gravar_craft_json("Converter os recursos para a web com o CEW", str(caminho))

    def definir_motor(self, motor: str) -> None:
        st = self.estado()
        st["motor_escolhido"] = motor
        self.gravar("estado", st)


def validar_craft_json(doc: dict) -> None:
    """Valida contra docs/schemas/craft.schema.json do Craft Anything (copiado em schemas/externos/)."""
    from jsonschema import Draft202012Validator

    from .caminhos import raiz_repositorio

    esquema = json.loads((raiz_repositorio() / "schemas" / "externos" / "craft-anything-craft.json").read_text(encoding="utf-8"))
    erros = sorted(Draft202012Validator(esquema).iter_errors(doc), key=str)
    if erros:
        raise ValueError(f"craft.json invalido para o esquema do Craft Anything: {erros[0].message}")


def listar_projetos(base: Path | None = None) -> list[dict]:
    base = base or pasta_projetos()
    saida = []
    if not base.is_dir():
        return saida
    for d in sorted(base.iterdir()):
        if (d / "estado.json").is_file():
            try:
                st = ler_json(d / "estado.json", "estado")
                saida.append({"projeto": st["projeto"], "etapa_atual": st["etapa_atual"], "fase": st.get("fase_craft_anything"), "alvo": (st.get("alvo") or {}).get("caminho")})
            except Exception as e:  # noqa: BLE001 - listar nao pode cair por um projeto quebrado
                saida.append({"projeto": d.name, "erro": str(e)})
    return saida


__all__ = ["Projeto", "ETAPAS", "CRITERIOS", "listar_projetos", "validar", "validar_craft_json"]
