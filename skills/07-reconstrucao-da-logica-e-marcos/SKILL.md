---
name: cew-reconstrucao-marcos
description: Use para tornar o app/jogo web utilizavel ou jogavel - reconstruir a logica a partir da engenharia reversa, marcos.json, testes de marco, window.__CEW_ESTADO, "fazer o personagem andar", "esta jogavel?", cobertura de conteudo.
---

# 07 - Reconstrucao da logica e marcos

## Gatilho
- Depois de gerar `app/` (etapa reconstrucao) ou quando a pessoa pergunta se o app ja e utilizavel/jogavel.
- `relatorio_verificacao.json` com `marco_atingido` abaixo do combinado.

## Entradas
- `especificacoes/logica.md` (skill 03), `web/dados/*.json`, `web/asset_manifest.json`.
- `marcos.json` (`schemas/marcos.schema.json`) e `app/tests/marcos/*.spec.js`.
- `cobertura_conteudo.json` (`schemas/cobertura_conteudo.schema.json`).

## Passos com comandos
1. Combine o escopo com a pessoa ANTES de programar: quais marcos cabem e quais serao obrigatorios.
   Jogos grandes levam semanas; diga isso com franqueza.
2. `cew marcos iniciar --projeto P --modelo jogo|app` (a etapa reconstrucao ja cria com `--modelo-marcos`).
   Edite `marcos.json`: renomeie, remova ou acrescente marcos; marque `obrigatorio: true` nos combinados.
3. Para cada marco, em ordem:
   - implemente em `app/src/` carregando tudo por `manifesto.get(id)` e expondo o observavel com
     `estado({...})` de `src/manifesto.js` (vira `window.__CEW_ESTADO`);
   - troque `test.fixme` por `test` em `app/tests/marcos/<id>.spec.js` e escreva a afirmacao real
     (entrada injetada com `page.keyboard`/`page.mouse` -> mudanca em `estado(page)`);
   - `cew check --projeto P` ate o marco ficar `aprovado`; commit por marco.
4. Leia `cobertura_conteudo.json`: assets nunca requisitados indicam conteudo ainda nao ligado ao jogo.
5. `cew marcos status --projeto P` mostra onde o projeto esta.

## Delegacao
- Gemini (opcional): resumir funcoes longas de logica (`schemas/gemini/tarefa_analise_funcao`).
- IA principal: arquitetura do jogo, todo o codigo de `app/`, os testes de marco e a conversa de escopo.

## Padroes de conversao
- Constantes de fisica e tabelas vem de `web/dados/*.json` com unidade no nome (`gravidade_m_s2`).
- Contrato: `window.__CEW_PRONTO = true` quando carregou; `window.__CEW_ESTADO` so com dados serializaveis.
- Teste pendente (`test.fixme`/`skip`) nunca conta como aprovado.

## Saidas
- `app/src/**`, `app/tests/marcos/*.spec.js`, `marcos.json` atualizado pela verificacao,
  `cobertura_conteudo.json`, `relatorio_verificacao.json` com `marco_atingido`.

## Criterios para avancar
- Todos os marcos `obrigatorio: true` aprovados; "jogavel" so e dito com o laco central aprovado em
  teste automatizado e confirmado pela pessoa.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| marco `pendente (test.fixme)` | o teste ainda e o modelo: escreva a afirmacao real |
| `estado(page)` vazio | o app nao chama `estado({...})`; importe de `./manifesto.js` |
| teclado nao surte efeito | foco no canvas: clique antes (`page.click('canvas')`) |
| cobertura baixa | assets carregados sob demanda nao foram exercitados pelos testes, ou nao estao ligados |
| marco aprova sozinho localmente e falha no check | tempo: espere o estado mudar com `page.waitForFunction` |
