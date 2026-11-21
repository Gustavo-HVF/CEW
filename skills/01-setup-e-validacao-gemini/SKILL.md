---
name: cew-setup-gemini
description: Use ao preparar ou consertar o ambiente do CEW - "cew setup", instalar/compilar o Craft Anything, configurar Ghidra/Java, GEMINI_API_KEY, testar o Gemini, reports/ambiente.json, "o menu do CEW nao abre".
---

# 01 - Setup e validacao do Gemini

## Gatilho
- Primeiro uso do repositorio, `cew` recusando abrir o menu, `reports/ambiente.json` com itens
  faltando, troca de maquina, erro "GEMINI_API_KEY nao definida" ou "teste do Gemini falhou".

## Entradas
- `config/versoes.json` (`schemas/config_versoes.schema.json`): ref do Craft Anything, versao e
  SHA-256 do Ghidra, minimos de Rust/Python/Node/Java.
- `config/gemini.json` (`schemas/config_gemini.schema.json`): modelo, temperatura, tokens,
  tentativas, espera, limites da sessao, cache.
- `.env` (copiado de `.env.example`): `GEMINI_API_KEY` (obrigatoria), `GHIDRA_INSTALL_DIR` (opcional),
  `CEW_CRAFT_ANYTHING_CLI` (opcional).

## Passos com comandos
1. Ambiente Python (uma vez):
   ```bash
   python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -e ".[dev]"
   npm install --ignore-scripts                    # ajv, glTF Validator, glTF-Transform
   ```
2. Chave: `cp .env.example .env` e preencha `GEMINI_API_KEY`. Nunca cole a chave em issue, log ou commit.
3. Ver o que seria feito: `cew setup --dry-run`.
4. Setup real: `cew setup` (HTTPS por padrao; `--ssh` forca SSH; `--com-app` compila tambem o app desktop).
   Ele clona `ferramentas/craft-anything` na ref fixada, roda `cargo build --release -p craft-anything-cli`
   (Rust >= 1.97), executa `craft-anything-cli doctor`, repassa o Ghidra ao Craft Anything
   (`settings-set --key engines.ghidra.install_dir`) e faz o teste real do Gemini.
5. Modo Deep com Ghidra: baixe a versao de `config/versoes.json` (12.1.4, Java 21), confira o SHA-256,
   extraia e defina `GHIDRA_INSTALL_DIR` no `.env`. A 12.2 exige Java 25.
6. Conferir o modelo: `cew gemini modelos` (lista os que suportam generateContent) e `cew gemini testar`.
7. Ler `reports/ambiente.json`: `pronto: true` e `obrigatorios_faltando: []`.

## Delegacao
- Gemini: apenas o teste curto `{"ok": true}` (`schemas/gemini/tarefa_teste_conexao.schema.json` ->
  `resposta_teste_conexao.schema.json`), sem cache.
- IA principal: decide versoes, edita `config/*.json`, interpreta o `doctor` e corrige o ambiente.

## Padroes de conversao
- Nao se aplica a esta etapa; o que importa e fixar versoes (reprodutibilidade das conversoes).

## Saidas
- `reports/ambiente.json` (`schemas/ambiente.schema.json`) com a saida real do `doctor` do Craft Anything.
- `ferramentas/craft-anything/target/release/craft-anything-cli`.
- `logs/setup/<data>.jsonl`, `logs/gemini/<data>.jsonl` (sem a chave).

## Criterios para avancar
- `reports/ambiente.json` sem obrigatorios faltando (python, git, node, npm, ffmpeg, craft-anything-cli
  ou Rust+cargo para compila-lo, Java se o Ghidra estiver configurado) e teste do Gemini ok.

## Erros comuns e o que fazer
| Sintoma | Causa | Acao |
|---|---|---|
| `chave_invalida` | chave errada/revogada | gere outra em https://aistudio.google.com/apikey |
| `modelo` (404) | nome do modelo nao existe para a chave | `cew gemini modelos`, ajuste `config/gemini.json` |
| `cota` | limite da API ou de `limite_sessao` | espere ou ajuste os limites |
| `rede` | proxy/firewall | libere `generativelanguage.googleapis.com` |
| `cargo build` falha no Linux | bibliotecas do app desktop | compile so o CLI (padrao) ou instale as libs do README do Craft Anything |
| Ghidra nao encontrado | `GHIDRA_INSTALL_DIR` sem `support/analyzeHeadless` | aponte para a pasta extraida (`ghidra_12.1.4_PUBLIC`) |
| Java errado | Ghidra 12.1.x pede 21; 12.2 pede 25 | ajuste `JAVA_HOME` |
