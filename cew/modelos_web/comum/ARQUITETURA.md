# Arquitetura do jogo web ({{PROJETO}}, {{MOTOR_NOME}})

```
src/
  main.js            cena do motor: carrega manifesto, cenas e liga tudo (unico lugar que conhece o motor)
  manifesto.js       asset_manifest.json, Audio (loop + desbloqueio), estado() e medidor de quadros
  cena.js            elementos dos mapas (web/dados/cenas/) ja posicionados
  nucleo/            regras do jogo SEM dependencia do motor (testaveis em Node)
    laco.js          passo de tempo fixo com acumulador, gerador com semente
    comportamentos.js  categoria/tipo da cena -> comportamento (inimigo -> IA, item -> coletavel...)
  logica/<programa>/ funcoes traduzidas do codigo original (cew codigo), com testes de equivalencia
  adaptadores/       entrada.js (acoes: teclado/gamepad/toque), salvamento.js (localStorage)
tests/
  marcos/*.spec.js   um teste por marco (marcos.json); test.fixme = pendente
  sessao.spec.js     sessao curta de ponta a ponta (CEW_SESSAO_S segundos, padrao 30)
  cena.spec.js       abre cada cena, sem erros no console, todos os elementos colocados
```

Regras:
- O nucleo e a logica traduzida nao importam o motor; o motor chama o nucleo a cada passo.
- Toda regra de jogo tem evidencia em especificacoes/logica.md (funcao, endereco, pseudo-C).
- Constantes em web/dados/configuracoes.json, com a unidade no nome; controles em web/dados/controles.json.
- O que os testes observam fica em window.__CEW_ESTADO (posicao, vida, tela, pontuacao, fase, fps, quadro).
