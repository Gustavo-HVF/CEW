---
name: cew-descompilar-traduzir
description: Use para levar o codigo de funcionamento do jogo (backend, logica) para a linguagem do motor escolhido - descompilar com o Craft Anything (pseudo-C, C#, Java, JS), "traduzir funcao", plano_traducao.json, cew codigo, testes de equivalencia.
---

# 09 - Descompilacao e traducao do codigo do jogo

## Gatilho
- Depois da etapa de engenharia (o codigo ja foi descompilado) e da escolha do motor.
- A pessoa quer que o jogo web se comporte como o original (fisica, IA, regras, geracao de mundo).
- `relatorio_verificacao.json` com item `traducao:*` reprovado.

## Entradas
- `codigo/original/indice.json` (`schemas/codigo_original.schema.json`) e os arquivos descompilados.
- `codigo/plano_traducao.json` (`schemas/plano_traducao.schema.json`): unidades com papel, prioridade,
  distancia da entrada (main/Update...), chamadas e equivalencias de API.
- `config/equivalencias_api.json` (+ `codigo/equivalencias.json` do projeto).
- `analise/` (Ghidra, carregadores), `especificacoes/logica.md` (skill 03), `marcos.json` (skill 07).

## Passos com comandos
1. Descompilar (a etapa engenharia ja faz; para refazer): `cew codigo descompilar --projeto P`.
   - nativo: `craft-anything-cli --deep native-source-folder-write` (um .c por funcao; Ghidra no modo Deep
     quando configurado no Craft Anything); sem o Craft Anything, usa a exportacao do Ghidra do CEW;
   - .NET (Unity Mono, XNA/FNA/MonoGame): `managed-ilspy-decompile` tipo a tipo (precisa de `ilspycmd`);
   - Java/JAR: `java-vineflower-decompile` (Vineflower: `craft-anything-cli engines-install` oferece);
   - JavaScript empacotado: `js-sources-restore`; scripts em texto (Lua, GDScript...) sao copiados.
2. Planejar para o motor: `cew codigo planejar --projeto P` (a etapa reconstrucao ja faz).
   Linguagem: Three.js/Babylon.js/Phaser/PixiJS/PlayCanvas -> JavaScript; Godot -> GDScript;
   Unity WebGL -> C#; Construct 3/GDevelop -> especificacao de eventos.
3. Ver a fila: `cew codigo status --projeto P` (alta prioridade = logica alcancada a partir da entrada).
4. Para cada unidade, na ordem: `cew codigo pacote <nome|u_id> --projeto P [--gemini]` gera
   `codigo/pacotes/<u>.md` (codigo original, quem chama/quem e chamado, strings, equivalencias, regras)
   e o esqueleto em `app/src/logica/<programa>/<nome>.js`. Traduza o comportamento no esqueleto.
5. Escreva os casos de equivalencia em `codigo/testes/<u>.json` (`schemas/testes_traducao.schema.json`),
   com a origem do valor esperado (`execucao_original`, `rastreamento`, `pseudo_c`, `documentacao`, `manual`).
6. `cew codigo testar [<nome>] --projeto P` -> `testada` (todos batem) ou `reprovada` (com o caso que falhou).
7. Sem teste possivel: `cew codigo registrar <nome> --projeto P --estado traduzida`;
   fora do escopo: `--estado descartada --motivo "desenho refeito com sprites do motor"`.
8. Ligue as funcoes traduzidas ao jogo (`app/src/main.js`) e confira os marcos (skill 07) com `cew check`.

## Delegacao
- Gemini (opcional, `--gemini`): rascunho do modulo traduzido e casos sugeridos
  (`schemas/gemini/tarefa_traducao` -> `resposta_traducao`), salvos em `codigo/rascunhos/`; NUNCA aplicados sozinhos.
- IA principal: decide o que traduzir, escreve a traducao, os casos de teste e a integracao com o motor.

## Padroes de conversao
- Traduza comportamento, nao mecanica de compilador: registradores, pilha, canario e ponteiros somem.
- APIs do sistema viram as do motor (equivalencias); arquivos do jogo viram assets do manifesto.
- Desenho e janela sao reconstruidos no motor: traduza a logica que decide o que desenhar.
- Inteiros com `| 0`/`>>> 0`; `Math.fround` quando a precisao de float de 32 bits importar;
  gerador aleatorio do original reimplementado se a sequencia importar (geracao de mundo).
- Funcoes puras sempre que possivel, para o teste de equivalencia; constantes em `web/dados/*.json`.

## Saidas
- `codigo/original/**`, `codigo/plano_traducao.json`, `codigo/pacotes/*.md`, `codigo/testes/*.json`,
  `codigo/rascunhos/*` e o codigo traduzido em `app/` (pasta da linguagem do motor).

## Criterios para avancar
- Todo caso de equivalencia existente passa (`traducao:*` obrigatorios no relatorio).
- As unidades de prioridade alta usadas pelos marcos obrigatorios estao `testada` ou `traduzida`.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| programa `indisponivel` | instale/compile o Craft Anything (`cew setup`) ou rode a exportacao do Ghidra |
| .NET `falhou` | instale o `ilspycmd` (o Craft Anything usa o ILSpy de linha de comando) |
| Java `falhou` | `craft-anything-cli engines-install` para o Vineflower, ou configure o caminho nas Settings |
| pseudo-C ilegivel (registradores) | ative o Ghidra no Craft Anything (`settings-set engines.ghidra.install_dir`) e descompile de novo |
| caso falha com numero estranho | ordem de bytes, sinal (`>>> 0`) ou overflow de 32 bits |
| `traduzida` depois de `testada` | a traducao mudou depois do teste: `cew codigo testar` de novo |
| testes "manual" | GDScript/C#: rode os casos no proprio motor; o CEW testa automaticamente so JavaScript |
