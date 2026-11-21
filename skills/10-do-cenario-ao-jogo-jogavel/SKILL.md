---
name: cew-jogo-jogavel
description: Use para levar um projeto do CEW (assets, cenas, codigo descompilado e app/ prontos) ao estado jogavel no navegador - "deixar jogavel", escopo minimo, cew escopo, logica com evidencia, nucleo/adaptadores, testes de marco reais, sessao curta, cew jogavel.
---

# 10 - Do cenario pronto ao jogo jogavel

## Gatilho
- O projeto ja tem `web/asset_manifest.json`, cenas em `web/dados/cenas/`, `codigo/plano_traducao.json`
  e `app/` gerado, e a pessoa quer jogar no navegador sem o executavel original.

## Entradas
- `inventario.json`, `plano_conversao.json`, `codigo/plano_traducao.json`, `marcos.json`,
  `cobertura_conteudo.json`, `especificacoes/logica.md`, `relatorio_verificacao.json`, `escopo.json`.
- Esquemas: `escopo`, `jogavel`, `marcos`, `dados/configuracoes`, `dados/controles`, `dados/cena`, `testes_traducao`.
- Exemplo completo: `exemplos/plataforma-2d/` (nucleo, camada do motor, testes de marco, teste do nucleo em Node).

## Passos com comandos
1. **Escopo antes de programar**: `cew escopo analisar --projeto P` (numeros, limites da web com
   evidencia, tamanho estimado, proposta). Combine com a pessoa e registre:
   `cew escopo definir --projeto P --marcos abre,entrada,colisao,laco_central --descricao "primeira fase completa"`.
   Diga com franqueza quando o jogo for grande (semanas) e que redistribuir assets exige permissao.
2. **Logica com evidencia** (skills 03 e 09): laco principal (passo fixo? Hz), maquina de estados, controles,
   fisica/colisao, IA, regras/progressao, gerador aleatorio. Constantes em `dados/configuracoes.json`
   (unidade no nome + `evidencias`), controles em `dados/controles.json`; `especificacoes/logica.md`.
3. **Traduzir da entrada para fora**: `cew codigo status`, depois por unidade `cew codigo pacote <u> [--gemini]`,
   traducao, `codigo/testes/<u>.json`, `cew codigo testar`. Nenhum esqueleto alcancavel a partir de `src/main.js`.
4. **Montar no motor** (`app/ARQUITETURA.md`): regras em `src/nucleo/` (sem motor), funcoes traduzidas em
   `src/logica/`, adaptadores em `src/adaptadores/` (`entrada.js`: acoes por teclado/gamepad/toque;
   `salvamento.js`), passo fixo `src/nucleo/laco.js` (`criarLacoFixo(hz, atualizar)`), comportamento por
   categoria da cena `src/nucleo/comportamentos.js` (spawn -> jogador, inimigo -> IA, item, porta/gatilho),
   `Audio.desbloquear()` no inicio. Exponha em `window.__CEW_ESTADO` posicao, vida, tela, pontuacao, fase;
   `quadro` e `fps` ja vem do medidor do CEW. Chame `pronto()` so quando a cena do motor existir.
5. **Testes de marco reais**: troque `test.fixme` por `test` em `app/tests/marcos/<id>.spec.js` usando
   `segurarTecla`, `esperarEstado`, `medirFps`, `VIEWPORT_CELULAR` (`tests/cew_helpers.js`). Gancho de teste
   (`window.__CEW_TESTE`) so para posicionar sem depender de tempo; o resto por entrada injetada.
6. **Nucleo testado sem navegador**: um script Node (ex.: `tests/nucleo_node.mjs`) que roda as regras com a
   cena e as constantes publicadas. Nao use o sufixo `.test.`/`.spec.` (o Playwright pegaria).
7. **Verificar**: `cew check --projeto P [--sessao-s 30]` ate `marco_atingido` chegar ao ultimo marco obrigatorio;
   a sessao curta (`tests/sessao.spec.js`) joga sozinha e exige zero erros e quadros subindo.
8. **Jogavel?** `cew jogavel avaliar --projeto P`. A pessoa joga (`npm run preview` em `app/`) e confirma num
   terminal interativo: `cew jogavel confirmar --projeto P --nota "..."` - o agente nunca confirma por ela.

## Delegacao
- Gemini (opcional): rascunhos de traducao e segunda opiniao visual; nunca decide regra de jogo.
- IA principal: escopo com a pessoa, especificacao com evidencia, nucleo, camada do motor e testes.

## Padroes de conversao
- Nucleo puro (entrada -> estado), testavel em Node; o motor so desenha e le entrada.
- Numeros do original: inteiros de 32 bits (`| 0`, `>>> 0`), `Math.fround`, ordem de bytes explicita.
- Fidelidade: SSIM contra `referencias/<cena>.png`; numeros conferidos contra evidencia (item `fidelidade`).
- Cobertura: ligue ao jogo os assets que `cobertura_conteudo.json` mostra sem uso, ou justifique.

## Saidas
- `escopo.json`, `especificacoes/logica.md`, `web/dados/{configuracoes,controles}.json`, `app/src/{nucleo,logica,adaptadores}/`,
  `app/tests/marcos/*.spec.js`, `relatorio_verificacao.json` (marco_atingido), `jogavel.json`.

## Criterios para avancar
- `cew jogavel avaliar` com todos os criterios aprovados: escopo definido, marcos obrigatorios (com o laco
  central), equivalencia das unidades usadas, sem esqueleto alcancavel, sessao curta, build estatico e a
  confirmacao da pessoa.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| teste le estado vazio logo apos abrir | `pronto()` chamado antes da cena do motor existir |
| HUD invisivel com zoom de camera | desenhe o HUD no DOM ou numa camera de interface |
| teclado sem efeito no teste | clique no canvas antes (`segurarTecla` ja faz) |
| Playwright tenta rodar script de Node | nome sem `.test.`/`.spec.` (o modelo usa `testMatch: '**/*.spec.js'`) |
| sessao reprova "jogo travado" | laco do jogo parou (excecao silenciosa, `await` pendurado) |
| `equivalencia` reprova | unidade importada pelo jogo sem `cew codigo testar` aprovado |
| `confirmacao_pessoa` pendente | so a pessoa confirma, depois de jogar |
