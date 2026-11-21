---
name: cew-delegacao-conversores
description: Use para planejar e executar conversoes e para escrever conversores novos - "plano_conversao", "formato desconhecido", tarefa para o Gemini, rascunho de conversor, sandbox, converters/, asset_manifest.json, testes com fixtures.
---

# 04 - Delegacao ao Gemini e conversores

## Gatilho
- Itens `aguardando_gemini`, `aguardando_conversor` ou `erro` em `plano_conversao.json`; pedido de
  conversor novo; resposta nova em `tarefas_gemini/`.

## Entradas
- `inventario.json`, `plano_conversao.json` (`schemas/plano_conversao.schema.json`), `formats/registry.json`.
- `tarefas_gemini/<sha>.tarefa.json` (`schemas/gemini/tarefa_formato.schema.json`) e
  `<sha>.resposta.json` (`schemas/gemini/resposta_formato.schema.json`).
- `analise/carregadores.json` (pseudo-C do carregador vai junto na tarefa).

## Passos com comandos
1. `cew etapa conversao --projeto <p>`: monta o plano, cria tarefas para desconhecidos (um por SHA-256)
   e chama o Gemini, roda os conversores e publica `web/asset_manifest.json`. `--sem-delegacao` nao chama o Gemini.
2. Revisar cada resposta: os campos do `cabecalho` batem com os bytes das `amostras`? A `confianca` e honesta?
3. Rodar o rascunho isolado (sem rede, com limite de tempo/memoria, so `--dry-run`):
   `cew sandbox projects/<p>/tarefas_gemini/<sha>.resposta.json --entrada <amostra>`.
   **Leia o codigo antes**: a sandbox do Windows nao e barreira contra codigo hostil.
4. Reescrever/aceitar como conversor real em `converters/<empresa>/<formato>_to_<destino>.py` com o
   esqueleto de `converters/comum/cli.py` (`INFO`, `converter(dados, esc, opcoes)`, `executar`),
   leitura defensiva via `LeitorBinario` (`exigir`, `contagem_plausivel`, `limitar_tamanho`).
5. Criar amostra sintetica em `tests/fixtures/gerar_fixtures.py` (nunca arquivo comercial), regenerar
   (`python tests/fixtures/gerar_fixtures.py`) e escrever testes em `tests/test_conversores.py`
   (valores, determinismo, entrada corrompida, `--help`/`--dry-run`).
6. Registrar o conversor na entrada do formato em `formats/registry.json` e documentar em `docs/formatos/<id>.md`.
7. `python -m pytest` e `cew etapa conversao --projeto <p>` de novo.

## Delegacao
- Gemini: hipotese de estrutura e rascunho de conversor para formatos desconhecidos (lote), sempre em
  JSON validado; respostas ficam em cache por hash da entrada (`cache/gemini/`).
- IA principal: unica que grava em `converters/`, `formats/` e `tests/`; revisa todo codigo gerado.

## Padroes de conversao
- Modelos/animacoes -> glTF 2.0 `.glb` (Y para cima, mao direita, metros; <= 4 pesos por vertice;
  materiais PBR metallic-roughness, o que nao tem equivalente em `extras`; `converters/comum/gltf.py`, `eixos.py`).
- Texturas -> PNG (ou KTX2 com basisu/toktx depois): desfazer tiling/swizzle, decodificar formatos de GPU
  (`converters/comum/texturas.py`), sRGB para cor e linear para normal/rugosidade (`opcoes.espaco_cor`),
  alfa preservado, aviso de dimensoes nao potencia de 2; mipmaps regenerados na web.
- Audio -> OGG Vorbis/Opus (musica), WAV (efeito < 2 s): decodificar ADPCM para PCM primeiro, loop em
  `metadados.loop` do manifesto (a web nao le loop do OGG), taxa e canais preservados.
- Dados -> JSON com esquema (`schemas/dados/*.schema.json`): UTF-8, controles como `{marcacao}`, unidade
  no nome do campo, referencias por id.
- Mapas -> glTF (geometria) + `dados/fases.json` (entidades, gatilhos, colisao, spawn).
- Determinismo: mesma entrada -> mesmos bytes (sem data/hora, zlib com nivel fixo, ffmpeg `+bitexact`).

## Saidas
- `plano_conversao.json`, `build/convertido/<id>/`, `web/assets/**`, `web/dados/**`,
  `web/asset_manifest.json` (`schemas/asset_manifest.schema.json`), conversores e testes novos.

## Criterios para avancar
- `plano_conversao.json` sem itens em `erro`; `python -m pytest tests/test_conversores.py` passando.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| `falha inesperada (bug do conversor...)` | leitura sem conferencia de limites: use `LeitorBinario` |
| hash muda entre execucoes | tirar data/hora, ordem de dicionario, aleatoriedade |
| resposta do Gemini fora do esquema | ja e refeita N vezes; se persistir, mais tokens ou outro modelo |
| `ffmpeg nao encontrado` | instale ou passe `opcoes.ffmpeg` |
| item `aguardando_conversor` | formato conhecido sem conversor: veja `ferramentas_conhecidas` no registro |
