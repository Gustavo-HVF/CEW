---
name: cew-engenharia-reversa
description: Use para decodificar a logica e os formatos do alvo com Craft Anything (modo Deep) e Ghidra headless - "engenharia reversa", pseudo-C, funcao que carrega um formato, maquina de estados, fisica, controles, descompactacao, analise/hipoteses.json, especificacoes.
---

# 03 - Engenharia reversa (Craft Anything Deep + Ghidra)

## Gatilho
- Etapa `engenharia` bloqueada ("especificacoes sem evidencia"), formato desconhecido que um
  executavel carrega, necessidade de reproduzir comportamento (fisica, controles, estados).

## Entradas
- `inventario.json`, `plano_conversao.json`.
- Executaveis/ROMs do inventario (tipo `codigo` no registro).
- `analise/<programa>-<id>.json` (`schemas/analise_programa.schema.json`), `analise/craft_triage.json`,
  `analise/carregadores.json`.

## Passos com comandos
1. Rodar a etapa: `cew etapa engenharia --projeto <p>` (usa `craft-anything-cli --deep triage` e o Ghidra
   headless se `GHIDRA_INSTALL_DIR` estiver definido; `--sem-ghidra` / `--sem-craft` desligam).
2. Ghidra manual (mesmo comando que o CEW usa):
   ```bash
   "$GHIDRA_INSTALL_DIR/support/analyzeHeadless" /tmp/proj cew -import <programa> \
     -scriptPath scripts/ghidra -postScript ExportarCEW.java analise.json 200 30 -deleteProject
   ```
   Saida: funcoes (assinatura, pseudo-C), strings com `referenciado_por`, grafo de chamadas.
3. Craft Anything (ferramentas reais, nomes com hifen): `craft-anything-cli commands` lista todas;
   uteis aqui: `craft-anything-cli --deep --project projects/<p>/investigation.cany triage <alvo>`,
   `native-functions-search`, `native-function-pseudocode`, `native-xrefs-list`, `native-call-graph-show`,
   `game-archives-list`, `game-pak-list`, `game-unity-list`, `game-unity-asset-export`,
   `game-unreal-texture-export`. Ou use o servidor MCP `craft-anything` (ja em `.vscode/mcp.json`).
4. Achar o carregador de um formato: em `analise/carregadores.json` (strings com a extensao/assinatura
   e as funcoes que as usam); siga o pseudo-C ate a leitura do cabecalho (offsets, tamanhos, ordem de bytes).
5. Escrever a especificacao em `projects/<p>/especificacoes/<formato>.md` (modelo em `docs/formatos/MODELO.md`)
   e a logica em `especificacoes/logica.md` (modelo em `docs/especificacoes/README.md`).
6. Atualizar `analise/hipoteses.json`: `estado: "confirmada"` so com evidencia (endereco, funcao,
   trecho de pseudo-C ou offset em amostra). Regras "quem carrega o que" vao em `analise/contexto.json`.
7. `cew validar projects/<p>/analise/hipoteses.json` e `cew etapa engenharia --projeto <p>` de novo.

## Delegacao
- Gemini (lote, `schemas/gemini/tarefa_analise_funcao.schema.json`): resumir o papel de funcoes ja
  escolhidas, propor estruturas a partir do pseudo-C. Enviar so o pseudo-C relevante, nunca o binario.
- IA principal: escolhe as funcoes, confere cada afirmacao no pseudo-C/bytes e grava hipoteses e
  especificacoes. Hipotese do Gemini sem conferencia nao vira `confirmada`.

## Padroes de conversao
- Valores numericos com unidade no nome (`gravidade_m_s2`), coordenadas convertidas para Y para cima
  e metros quando forem para glTF/JSON de fases.
- Rotinas de descompactacao proprias viram funcao em `converters/comum/compressao.py` com teste.

## Saidas
- `analise/*.json`, `analise/hipoteses.json`, `analise/contexto.json`, `especificacoes/*.md`,
  evidencias no `investigation.cany` do Craft Anything.

## Criterios para avancar
- Cada formato com item `pendente` no plano tem hipotese `confirmada`, com evidencia e especificacao
  (`cew/engenharia.py: criterio_saida`).

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| analyzeHeadless falha com Java | versao do Java abaixo de `application.java.min` do Ghidra |
| decompilacao vazia em funcoes grandes | aumente o 3o argumento (segundos por funcao) |
| binario empacotado/cifrado | o CEW nao remove protecao; analise o que estiver legivel ou use dumps legitimos fornecidos pela pessoa |
| ROM sem formato executavel reconhecido | importe com `-processor <languageID>` e `-loader BinaryLoader` (ver analyzeHeadlessREADME) |
| Craft Anything recusa ferramenta | esta em Clean room: use `--deep` |
