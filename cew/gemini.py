"""Cliente da API do Gemini (IA secundaria) com saida estruturada, cache e logs (itens 1.1-1.6).

Contrato REST conferido no SDK oficial google-genai 3.6.1 (pacote baixado do PyPI em 2026-11-20):
- POST {url_base}/{versao_api}/models/{modelo}:generateContent, chave no cabecalho x-goog-api-key;
- generationConfig: responseMimeType "application/json" + responseJsonSchema (JSON Schema, so as
  palavras-chave $id $defs $ref $anchor type format title description enum items prefixItems
  minItems maxItems minimum maximum anyOf oneOf properties additionalProperties required) ou
  responseSchema (subconjunto OpenAPI); temperature, maxOutputTokens, thinkingConfig.thinkingLevel;
- resposta: candidates[0].content.parts[].text, candidates[0].finishReason, usageMetadata
  (promptTokenCount, candidatesTokenCount, thoughtsTokenCount, totalTokenCount);
- GET {url_base}/{versao_api}/models lista modelos (supportedGenerationMethods).

Regras: a chave so vai no cabecalho e nunca e gravada; toda resposta e validada contra
schemas/gemini/resposta_*.schema.json e refeita ate `tentativas` vezes; respostas validas ficam
em cache por hash da entrada; tudo o que e enviado vai para logs/gemini/<data>.jsonl.
"""

from __future__ import annotations

import base64
import datetime as _dt
import hashlib
import json
import os
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .caminhos import raiz_repositorio
from .config import carregar_env, config_gemini
from .esquemas import erros as erros_esquema
from .esquemas import esquema, validar
from .logs import agora_iso, pasta_logs, redigir, redigir_obj

PALAVRAS_RESPONSE_JSON_SCHEMA = {
    "$id", "$defs", "$ref", "$anchor", "type", "format", "title", "description", "enum", "items", "prefixItems",
    "minItems", "maxItems", "minimum", "maximum", "anyOf", "oneOf", "properties", "additionalProperties", "required", "propertyOrdering",
}
INSTRUCAO_SISTEMA = (
    "Voce e o cew-gemini-worker, IA secundaria do CEW (Convert Everything for the Web). "
    "Responda SOMENTE com JSON valido no esquema pedido. Nao invente: quando algo nao estiver sustentado pelos bytes, "
    "pseudocodigo ou imagens enviados, diga em 'duvidas' e baixe a confianca. Toda afirmacao sobre um campo deve citar "
    "a evidencia (offset e bytes, ou funcao/endereco)."
)


class ErroGemini(RuntimeError):
    def __init__(self, tipo: str, mensagem: str):
        self.tipo = tipo
        super().__init__(redigir(mensagem))


@dataclass
class Uso:
    chamadas: int = 0
    tokens_entrada: int = 0
    tokens_saida: int = 0
    custo_usd: float = 0.0


# Uso acumulado na sessao (processo): o limite de gasto vale para a sessao inteira.
USO_SESSAO = Uso()

Transporte = Callable[[str, str, dict[str, str], bytes | None, float], tuple[int, bytes]]


def transporte_urllib(metodo: str, url: str, cabecalhos: dict[str, str], corpo: bytes | None, tempo: float) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=corpo, method=metodo, headers=cabecalhos)
    try:
        with urllib.request.urlopen(req, timeout=tempo) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
        raise ErroGemini("rede", f"falha de rede ao falar com a API do Gemini: {getattr(e, 'reason', e)}") from e


def para_response_json_schema(doc: dict) -> dict:
    """Remove o que a API nao aceita ($schema, pattern, const...) mantendo a estrutura."""

    def limpar(n: Any) -> Any:
        if isinstance(n, dict):
            saida = {}
            for k, v in n.items():
                if k == "const":
                    saida["enum"] = [v]
                elif k in PALAVRAS_RESPONSE_JSON_SCHEMA:
                    if k in ("properties", "$defs"):
                        saida[k] = {nome: limpar(sub) for nome, sub in v.items()}
                    else:
                        saida[k] = limpar(v)
            return saida
        if isinstance(n, list):
            return [limpar(x) for x in n]
        return n

    s = limpar(doc)
    s.pop("$id", None)
    return s


def para_response_schema(doc: dict) -> dict:
    """Subconjunto OpenAPI (responseSchema): tipos em maiusculas, sem additionalProperties/$defs."""

    def conv(n: Any) -> Any:
        if isinstance(n, dict):
            saida: dict[str, Any] = {}
            for k, v in n.items():
                if k == "type":
                    saida["type"] = v.upper() if isinstance(v, str) else v
                elif k == "properties":
                    saida["properties"] = {a: conv(b) for a, b in v.items()}
                elif k in ("items",):
                    saida[k] = conv(v)
                elif k == "anyOf":
                    saida["anyOf"] = [conv(x) for x in v]
                elif k in ("enum", "required", "description", "format", "minimum", "maximum", "minItems", "maxItems", "nullable", "title"):
                    saida[k] = v
            return saida
        return n

    return conv(doc)


def hash_canonico(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass
class Parte:
    """Parte de uma mensagem: texto ou binario (imagem). Binarios entram no log so como hash."""

    texto: str | None = None
    mime: str | None = None
    dados: bytes | None = None

    def rest(self) -> dict:
        if self.texto is not None:
            return {"text": self.texto}
        return {"inlineData": {"mimeType": self.mime, "data": base64.b64encode(self.dados or b"").decode("ascii")}}

    def para_log(self) -> dict:
        if self.texto is not None:
            return {"text": self.texto}
        return {"inlineData": {"mimeType": self.mime, "sha256": hashlib.sha256(self.dados or b"").hexdigest(), "bytes": len(self.dados or b"")}}


@dataclass
class ClienteGemini:
    config: dict = field(default_factory=dict)
    transporte: Transporte = transporte_urllib
    chave: str | None = None
    raiz: Path = field(default_factory=raiz_repositorio)

    def __post_init__(self) -> None:
        if not self.config:
            self.config = config_gemini()
        if self.chave is None:
            carregar_env(self.raiz / ".env")
            self.chave = os.environ.get("GEMINI_API_KEY", "").strip() or None

    # ----------------------------------------------------------------------------- basico
    @property
    def tem_chave(self) -> bool:
        return bool(self.chave)

    def _url(self, sufixo: str) -> str:
        c = self.config
        return f"{c['url_base'].rstrip('/')}/{c['versao_api']}/{sufixo}"

    def _cabecalhos(self) -> dict[str, str]:
        if not self.chave:
            raise ErroGemini("sem_chave", "GEMINI_API_KEY nao definida (ambiente ou .env)")
        return {"Content-Type": "application/json", "x-goog-api-key": self.chave}

    @staticmethod
    def classificar(status: int, corpo: bytes) -> ErroGemini:
        try:
            err = json.loads(corpo.decode("utf-8")).get("error", {})
        except (ValueError, UnicodeDecodeError, AttributeError):
            err = {}
        msg = err.get("message") or corpo[:300].decode("utf-8", "replace")
        razoes = " ".join(str(d.get("reason", "")) for d in err.get("details", []) if isinstance(d, dict))
        st = err.get("status", "")
        if "API_KEY_INVALID" in razoes or (status == 400 and "API key" in msg):
            return ErroGemini("chave_invalida", f"chave do Gemini invalida: {msg}")
        if status == 403 or st == "PERMISSION_DENIED":
            return ErroGemini("permissao", f"chave sem permissao para este modelo/projeto: {msg}")
        if status == 429 or st == "RESOURCE_EXHAUSTED":
            return ErroGemini("cota", f"cota ou limite de taxa do Gemini esgotado: {msg}")
        if status == 404 or st == "NOT_FOUND":
            return ErroGemini("modelo", f"modelo nao encontrado (confira config/gemini.json): {msg}")
        if status >= 500:
            return ErroGemini("servico", f"erro do servico Gemini ({status}): {msg}")
        return ErroGemini("desconhecido", f"erro {status} do Gemini: {msg}")

    def _registrar(self, linha: dict) -> None:
        dia = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        arq = pasta_logs() / "gemini" / f"{dia}.jsonl"
        arq.parent.mkdir(parents=True, exist_ok=True)
        linha = redigir_obj(linha)
        if erros_esquema(linha, "log_gemini"):
            linha = {k: linha.get(k) for k in ("ts", "tarefa", "modelo", "hash_entrada", "cache", "resultado")}
        with open(arq, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(linha, ensure_ascii=False) + "\n")

    def _pasta_cache(self) -> Path:
        p = Path(self.config["cache"]["pasta"])
        return p if p.is_absolute() else self.raiz / p

    def _conferir_limites(self) -> None:
        lim = self.config["limite_sessao"]
        if USO_SESSAO.chamadas >= lim["max_chamadas"]:
            raise ErroGemini("cota", f"limite de {lim['max_chamadas']} chamadas por sessao atingido (config/gemini.json)")
        if USO_SESSAO.tokens_entrada + USO_SESSAO.tokens_saida >= lim["max_tokens_totais"]:
            raise ErroGemini("cota", "limite de tokens por sessao atingido (config/gemini.json)")
        if lim["custo_maximo_usd"] and USO_SESSAO.custo_usd >= lim["custo_maximo_usd"]:
            raise ErroGemini("cota", f"limite de gasto de US$ {lim['custo_maximo_usd']} por sessao atingido")

    def _somar_uso(self, uso: dict) -> dict:
        ent = int(uso.get("promptTokenCount", 0))
        sai = int(uso.get("candidatesTokenCount", 0)) + int(uso.get("thoughtsTokenCount", 0))
        preco = self.config["limite_sessao"]["preco_por_milhao_tokens_usd"]
        USO_SESSAO.chamadas += 1
        USO_SESSAO.tokens_entrada += ent
        USO_SESSAO.tokens_saida += sai
        USO_SESSAO.custo_usd += ent / 1e6 * preco["entrada"] + sai / 1e6 * preco["saida"]
        return {"entrada": ent, "saida": sai, "total": int(uso.get("totalTokenCount", ent + sai))}

    # ------------------------------------------------------------------------- chamadas
    def corpo_requisicao(self, partes: list[Parte], esquema_resposta: dict, max_tokens: int | None = None) -> dict:
        c = self.config
        gen: dict[str, Any] = {"responseMimeType": "application/json", "temperature": c["temperatura"], "maxOutputTokens": max_tokens or c["max_tokens_saida"]}
        if c["modo_esquema"] == "responseJsonSchema":
            gen["responseJsonSchema"] = para_response_json_schema(esquema_resposta)
        else:
            gen["responseSchema"] = para_response_schema(esquema_resposta)
        if c.get("nivel_raciocinio"):
            gen["thinkingConfig"] = {"thinkingLevel": c["nivel_raciocinio"]}
        return {
            "systemInstruction": {"parts": [{"text": INSTRUCAO_SISTEMA}]},
            "contents": [{"role": "user", "parts": [p.rest() for p in partes]}],
            "generationConfig": gen,
        }

    def gerar(self, tarefa: str, partes: list[Parte], nome_esquema_resposta: str, usar_cache: bool = True, max_tokens: int | None = None, validacao_extra: Callable[[dict], list[str]] | None = None) -> dict:
        """Chama o modelo e devolve o JSON validado. Lanca ErroGemini depois de esgotar as tentativas."""
        esq = esquema(nome_esquema_resposta)
        corpo = self.corpo_requisicao(partes, esq, max_tokens)
        chave_cache = hash_canonico({"modelo": self.config["modelo"], "versao_api": self.config["versao_api"], "corpo": corpo})
        log_base = {"tarefa": tarefa, "modelo": self.config["modelo"], "hash_entrada": chave_cache, "enviado": {"partes": [p.para_log() for p in partes], "esquema": nome_esquema_resposta}}
        arq_cache = self._pasta_cache() / f"{chave_cache}.json"
        if usar_cache and self.config["cache"]["ativo"] and arq_cache.is_file():
            resp = json.loads(arq_cache.read_text(encoding="utf-8"))["resposta"]
            if not erros_esquema(resp, nome_esquema_resposta):
                self._registrar({"ts": agora_iso(), **log_base, "cache": True, "resultado": "ok"})
                return resp
        url = self._url(f"models/{self.config['modelo']}:generateContent")
        ultimo: ErroGemini | None = None
        for tentativa in range(1, int(self.config["tentativas"]) + 1):
            self._conferir_limites()
            status, bruto = self.transporte("POST", url, self._cabecalhos(), json.dumps(corpo).encode("utf-8"), float(self.config["tempo_limite_requisicao_s"]))
            if status != 200:
                ultimo = self.classificar(status, bruto)
                self._registrar({"ts": agora_iso(), **log_base, "cache": False, "tentativa": tentativa, "resultado": "erro_http", "erro": str(ultimo)})
                if ultimo.tipo in ("chave_invalida", "permissao", "modelo"):
                    raise ultimo
                time.sleep(float(self.config["espera_entre_tentativas_s"]) * tentativa)
                continue
            try:
                dados = json.loads(bruto.decode("utf-8"))
            except ValueError:
                dados = {}
            uso = self._somar_uso(dados.get("usageMetadata", {}))
            cand = (dados.get("candidates") or [{}])[0]
            texto = "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", []) if not p.get("thought"))
            problemas: list[str]
            try:
                resp = json.loads(texto)
                problemas = erros_esquema(resp, nome_esquema_resposta)
                if not problemas and validacao_extra:
                    problemas = validacao_extra(resp)
            except ValueError as e:
                resp, problemas = None, [f"JSON invalido: {e}; finishReason={cand.get('finishReason')}"]
            if not problemas:
                if self.config["cache"]["ativo"]:
                    arq_cache.parent.mkdir(parents=True, exist_ok=True)
                    arq_cache.write_text(json.dumps({"tarefa": tarefa, "modelo": self.config["modelo"], "resposta": resp}, ensure_ascii=False, indent=2), encoding="utf-8")
                self._registrar({"ts": agora_iso(), **log_base, "cache": False, "tentativa": tentativa, "resultado": "ok", "tokens": uso})
                return resp  # type: ignore[return-value]
            ultimo = ErroGemini("resposta_invalida", "resposta fora do esquema: " + "; ".join(problemas[:3]))
            self._registrar({"ts": agora_iso(), **log_base, "cache": False, "tentativa": tentativa, "resultado": "resposta_invalida", "erro": str(ultimo), "tokens": uso})
            time.sleep(float(self.config["espera_entre_tentativas_s"]))
        self._registrar({"ts": agora_iso(), **log_base, "cache": False, "resultado": "falha", "erro": str(ultimo)})
        raise ultimo or ErroGemini("desconhecido", "falha sem detalhes")

    def testar(self) -> dict:
        """Teste real e curto (item 1.2): pede {"ok": true} em JSON. Nunca usa cache."""
        inicio = time.monotonic()
        resultado = {"chave_presente": self.tem_chave, "teste_ok": False, "modelo": self.config["modelo"], "erro": None, "tipo_erro": None, "latencia_ms": None}
        if not self.tem_chave:
            resultado.update(erro="GEMINI_API_KEY nao definida (ambiente ou .env)", tipo_erro="sem_chave")
            return resultado
        tarefa = {"schema_version": "1.0", "gerado_por": "cew", "tarefa": "teste_conexao"}
        validar(tarefa, "gemini/tarefa_teste_conexao")
        try:
            resp = self.gerar("teste_conexao", [Parte(texto='Teste de conexao do CEW. Responda exatamente {"ok": true}.')], "gemini/resposta_teste_conexao", usar_cache=False, max_tokens=256)
            resultado["teste_ok"] = resp.get("ok") is True
        except ErroGemini as e:
            resultado.update(erro=str(e), tipo_erro=e.tipo if e.tipo in ("sem_chave", "chave_invalida", "permissao", "cota", "modelo", "rede", "servico", "resposta_invalida") else "desconhecido")
        resultado["latencia_ms"] = int((time.monotonic() - inicio) * 1000)
        return resultado

    def modelos(self) -> list[dict]:
        status, bruto = self.transporte("GET", self._url("models?pageSize=1000"), self._cabecalhos(), None, float(self.config["tempo_limite_requisicao_s"]))
        if status != 200:
            raise self.classificar(status, bruto)
        dados = json.loads(bruto.decode("utf-8"))
        return [{"nome": m.get("name", "").removeprefix("models/"), "metodos": m.get("supportedGenerationMethods", []), "descricao": m.get("displayName", "")}
                for m in dados.get("models", [])]


def mensagem_amigavel(tipo: str | None) -> str:
    return {
        "sem_chave": "Defina GEMINI_API_KEY no ambiente ou no arquivo .env (copie .env.example). Crie a chave em https://aistudio.google.com/apikey.",
        "chave_invalida": "A chave do Gemini foi recusada. Confira se copiou a chave inteira e se ela nao foi revogada.",
        "permissao": "A chave nao tem permissao para este modelo ou projeto. Troque o modelo em config/gemini.json ou habilite a API no projeto da chave.",
        "cota": "Cota ou limite de taxa esgotado (ou o limite de gasto da sessao em config/gemini.json). Espere ou ajuste os limites.",
        "modelo": "O modelo configurado nao existe para esta chave. Rode 'cew gemini modelos' e ajuste config/gemini.json.",
        "rede": "Nao foi possivel conectar a generativelanguage.googleapis.com. Confira a internet, proxy ou firewall.",
        "servico": "O servico do Gemini respondeu com erro. Tente de novo em alguns minutos.",
        "resposta_invalida": "O modelo respondeu fora do esquema JSON. Tente outro modelo ou aumente max_tokens_saida.",
    }.get(tipo or "", "Erro desconhecido ao testar o Gemini; veja logs/gemini/.")
