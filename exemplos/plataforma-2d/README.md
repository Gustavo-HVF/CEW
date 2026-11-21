# Exemplo: plataforma 2D jogavel (CEW v2.3)

Caso trabalhado do fluxo "do cenario pronto ao jogo jogavel", com o mapa do Tiled das amostras
(`tests/fixtures/amostras/generico/fase.tmj`): spawn, pilastra, slime que patrulha e chao de tiles.
Nao ha executavel original: as constantes de `alvo/configuracoes.json` tem evidencia "valor de projeto"
(num jogo real, a evidencia e funcao/endereco/pseudo-C do original).

```bash
mkdir -p /tmp/alvo && cp tests/fixtures/amostras/generico/fase.tmj exemplos/plataforma-2d/alvo/*.json /tmp/alvo/
cp tests/fixtures/amostras/web/pronto.png /tmp/alvo/tree.png
cew run --projeto demo --alvo /tmp/alvo --motor phaser --ate reconstrucao
cp -r exemplos/plataforma-2d/app/* projects/demo/app/          # o trabalho do agente: nucleo, cena do motor, testes de marco
cew escopo definir --projeto demo --marcos abre,entrada,colisao,laco_central,progressao --descricao "fase floresta completa"
cd projects/demo/app && npm install && node tests/nucleo_node.mjs ../web/dados/cenas/floresta-*.json ../web/dados/configuracoes-*.json && cd -
cew check --projeto demo --sessao-s 20
cew jogavel avaliar --projeto demo                              # tudo verde menos a confirmacao
cew jogavel confirmar --projeto demo --nota "joguei a fase"     # so a pessoa, em terminal interativo
```

| Arquivo | Papel |
|---|---|
| `app/src/nucleo/jogo.js` | regras (colisao AABB com tiles e estruturas da cena, gravidade, pulo, patrulha, pisao, dano, fim de fase), sem Phaser |
| `app/src/main.js` | camada do motor: desenha a cena, passo fixo (`nucleo/laco.js`), acoes (`adaptadores/entrada.js`), recorde (`adaptadores/salvamento.js`), HUD, `window.__CEW_ESTADO` |
| `app/tests/marcos/*.spec.js` | testes reais dos marcos (entrada, colisao, laco central, progressao) |
| `app/tests/nucleo_node.mjs` | as mesmas regras testadas em Node, sem navegador |

`window.__CEW_TESTE.posicionar(x, y)` e um gancho de teste para levar o jogador ate o inimigo sem
depender de tempo de pulo; o resto e jogado por teclado injetado.
