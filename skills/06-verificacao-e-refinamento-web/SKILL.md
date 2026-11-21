---
name: cew-verificacao-web
description: Use para verificar e refinar o resultado - "cew check", relatorio_verificacao.json, glTF Validator, determinismo, SSIM, capturas de tela, Playwright, erros no console, comparar com o jogo original, etapa Pronto.
---

# 06 - Verificacao e refinamento web

## Gatilho
- Depois de gerar/alterar `app/` ou qualquer conversor; antes de declarar "pronto"; relatorio reprovado.

## Entradas
- Todos os JSON do projeto, `web/asset_manifest.json`, `app/` (com `package.json`).
- Opcional: `referencias/<cena>.png` (capturas do original fornecidas pela pessoa) e
  `referencias/texturas/<nome do asset>.png` (decodificacao de referencia de uma ferramenta externa).

## Passos com comandos
1. `cew check --projeto <p>` (com `--instalar-dependencias` para permitir `npm install` em `app/`,
   `--chromium <caminho>` ou `CEW_CHROMIUM` para um Chromium ja instalado, `--sem-web` para so assets).
2. Ler `relatorio_verificacao.json`: cada item tem `categoria`, `obrigatorio`, `aprovado`, `detalhes`, `metricas`.
3. Corrigir na origem: conversor (e teste), dados, ou codigo em `app/`; repetir o check.
4. Segunda opiniao visual (opcional, nunca obrigatoria): `cew check --projeto <p> --gemini`.
5. Testes do repositorio: `python -m pytest` e `npm test` (ajv + glTF Validator).

## Delegacao
- Gemini: so a comparacao visual em JSON (`schemas/gemini/tarefa_comparacao_visual.schema.json` ->
  `resposta_comparacao_visual.schema.json`), depois da diferenca numerica.
- IA principal: decide o que corrigir e onde; nenhuma reprovacao obrigatoria e ignorada.

## Padroes de conversao
| Categoria | O que confere |
|---|---|
| esquema | todo JSON do projeto valida (jsonschema e ajv), inclusive `craft.json` contra o esquema do Craft Anything |
| determinismo | roda cada conversor de novo e compara o SHA-256 das saidas |
| modelo | glTF Validator oficial sem erros; vertices iguais aos do manifesto |
| textura | dimensoes e alfa; SSIM >= 0,98 contra a referencia, se houver |
| audio | taxa, duracao (WAV exato, OGG via ffprobe +-0,05 s) e pontos de loop |
| build_web | `npm run build` sem erros |
| navegador | Playwright abre cada cena, sem erros no console, salva `checks/capturas/<cena>.png` |
| comparacao_visual | SSIM (luminancia, janelas 8x8) entre `referencias/<cena>.png` e a captura, limiar 0,6 |

## Saidas
- `relatorio_verificacao.json` (`schemas/relatorio_verificacao.schema.json`), `checks/capturas/*.png`,
  `checks/gemini_<cena>.json` (se usado).

## Criterios para avancar
- Motor -> Pronto: `relatorio_verificacao.json` com `"aprovado": true` (todos os itens obrigatorios) e build web validado.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| `glTF Validator indisponivel` | `npm install` na raiz do CEW |
| `dependencias nao instaladas` | `npm install` em `app/` ou `--instalar-dependencias` |
| `playwright nao rodou` | `npx playwright install chromium` em `app/` ou `--chromium` |
| determinismo falhou | conversor usa data/hora, aleatoriedade ou ordem instavel |
| SSIM baixo com cena certa | resolucao/enquadramento diferentes: alinhe camera e tamanho da janela da captura |
