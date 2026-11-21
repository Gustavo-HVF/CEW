---
name: cew-mapeamento-cenas
description: Use para mapear e reposicionar os elementos dos mapas do jogo - inimigos, vegetacao, pilastras, itens, spawn, portas, gatilhos, luzes -, "posicao dos objetos", "cena", "entidades do mapa", cena_bruta.json, mapeamento_entidades.json, ajustes_cena.json, cew cena.
---

# 08 - Mapeamento e reposicionamento de cenas

## Gatilho
- O alvo tem mapas/fases com objetos posicionados (BSP, Tiled, cenas Unity/Godot, formatos proprios).
- A pessoa quer que inimigos, vegetacao, estruturas etc. carreguem no lugar certo junto com o mapa.
- Elementos aparecem fora do lugar, girados, na categoria errada ou sem modelo/sprite.

## Entradas
- Mapas identificados no inventario (registro global ou do projeto, `tipo: "mapa"`).
- Receitas que geram cena: `cookbook/idtech/bsp_entidades_to_cena.py` (Quake BSP),
  `cookbook/generico/tiled_json_to_cena.py` (Tiled JSON). Outros formatos: conversor do projeto (skill 04).
- `schemas/dados/cena.schema.json`, `schemas/mapeamento_entidades.schema.json`, `schemas/ajustes_cena.schema.json`.
- `analise/` (Ghidra/Craft Anything): onde o jogo le posicao, rotacao e tipo de cada objeto.

## Passos com comandos
1. **Conversor do mapa** (se nenhuma receita cobre): `cew novo-conversor <id> --projeto P --destino cena`.
   Ele grava `cena_bruta.json` com `estado: "bruta"`, as posicoes nas unidades do jogo e o
   `sistema_coordenadas` declarado (eixo para cima, mao, metros por unidade, origem 2D, sentido da rotacao).
   Use o id original do objeto em `id_original` sempre que o formato tiver um (ids estaveis entre versoes).
   Rotacao 3D completa: `rotacao` em quaternion no sistema original (o CEW converte); so guinada: `angulos_graus`.
2. `cew etapa conversao --projeto P`: o CEW normaliza (3D: metros, Y para cima, mao direita; 2D: pixels,
   topo esquerdo, graus horarios), categoriza e liga os assets, e publica em `web/dados/cenas/`.
3. Conferir: `cew cena listar --projeto P` e `cew cena mostrar <cena> --projeto P [--categoria inimigo]`.
4. **Regras** (reorganizacao por tipo, valem para todas as cenas e conversoes futuras):
   `cew cena regra --projeto P --tipo-original "monster_*" --categoria inimigo --asset-glob "*ogre*" --fator 1.5`
   `cew cena regra --projeto P --tipo-original "info_null" --remover`
5. **Ajustes** (reposicionamento nao destrutivo, reaplicado a cada conversao):
   `cew cena ajustar e1m1 --projeto P --op mover --entidade e_<id> --para 1,0,-2 --motivo "afastar do spawn"`
   `cew cena ajustar floresta --projeto P --op deslocar --categoria vegetacao --delta 0,-8`
   Operacoes: mover, deslocar, girar, escalar, grade, remover, definir (categoria/asset/nome/propriedades), adicionar.
6. `cew check --projeto P`: a verificacao exige cena valida, assets existentes e ids unicos; no navegador,
   todo elemento da cena precisa ter sido colocado (`window.__CEW_ESTADO.cenas[id].instanciadas`).

## Delegacao
- Gemini (opcional): sugerir categoria para tipos originais obscuros, em lote (`tipo_original` -> categoria), sempre revisado.
- IA principal: conversor da cena, sistema de coordenadas, regras, ajustes combinados com a pessoa.

## Padroes de conversao
- 3D: posicao em metros, Y para cima, mao direita; rotacao em quaternion `[x, y, z, w]`; troca de mao
  (esquerda -> direita) espelha um eixo e inverte o sinal da guinada.
- 2D: pixels com origem no topo esquerdo, y para baixo, rotacao em graus horarios (Phaser/PixiJS);
  `posicao_m = [x, -y, 0] * metros_por_unidade` para quem desenhar o 2D num motor 3D.
- Categoria: regra > conversor > palavras-chave (pt/en) > `categoria_padrao`. Asset: regra > conversor >
  referencia de modelo do original > nome do tipo (`monster_ogre` -> `ogre.*`).
- Elemento sem asset aparece no jogo como marcador colorido pela categoria (nada some).
- Entidade sem posicao propria (ex.: porta feita de brush no Quake) vem com `posicao_estimada: true`.

## Saidas
- `web/dados/cenas/<cena>-<id>.json` (tipo `mapa` no manifesto), `mapeamento_entidades.json`,
  `ajustes_cena.json`; nos modelos web, `src/cena.js` carrega e posiciona tudo.

## Criterios para avancar
- Itens `cena:*` aprovados em `relatorio_verificacao.json` e o teste de navegador mostrando
  `instanciadas == entidades` em todas as cenas.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| mapa deitado ou espelhado | `sistema_coordenadas` errado na cena bruta (eixo para cima ou mao) |
| tudo pequeno/gigante | `metros_por_unidade` (Quake ~0,0254; Tiled: 1/pixels por metro) |
| rotacao invertida | sentido da rotacao (`anti_horaria`/`horaria`) no sistema de origem |
| elementos como cubos coloridos | sem asset ligado: regra `--asset-glob` ou `definir` com `asset_id` |
| ajuste "nao encontrou entidades" | o id mudou porque o formato nao tem id proprio e a posicao original mudou: use filtro ou refaca o ajuste |
| categoria errada | regra por `tipo_original` (ou `definir` para um elemento so) |
