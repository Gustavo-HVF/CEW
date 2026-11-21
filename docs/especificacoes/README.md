# Especificacoes (etapa 4 - engenharia reversa)

Cada projeto guarda as especificacoes do alvo em `projects/<nome>/especificacoes/`:

- `<formato_id>.md` - uma por formato que sera convertido (gerada como esqueleto pelo CEW e
  completada pela IA principal). Modelo de campos: `docs/formatos/MODELO.md`.
- `logica.md` - a logica do jogo/aplicativo, no modelo abaixo.

Toda afirmacao leva evidencia: funcao e endereco (Ghidra/Craft Anything), trecho de pseudo-C, ou
offset de arquivo. O resumo estruturado vai para `analise/hipoteses.json`
(`schemas/hipoteses_formato.schema.json`) e as regras "quem carrega o que" para
`analise/contexto.json` (`schemas/contexto_formatos.schema.json`), que alimentam a camada 4 da
identificacao.

O criterio para avancar (Engenharia -> Conversao) e: cada formato com item `pendente` no plano tem
hipotese `confirmada`, com evidencia e com o arquivo de especificacao presente
(`cew/engenharia.py: criterio_saida`).

---

## Modelo: `logica.md`

```markdown
# Logica de <jogo>

Programa analisado: <arquivo> (SHA-256 ...), Ghidra <versao>, analise/<programa>.json

## Laco principal
- funcao, endereco; ordem: entrada -> atualizar -> desenhar; passo de tempo (fixo/variavel, Hz)

## Maquina de estados
| Estado | Entra quando | Sai para | Funcao (endereco) |
|---|---|---|---|

## Controles
| Acao | Tecla/botao original | Funcao que le | Equivalente web |
|---|---|---|---|

## Fisica
| Constante | Valor | Unidade | Evidencia (funcao, endereco, pseudo-C) |
|---|---|---|---|
(os valores viram dados/configuracoes.json com a unidade no nome do campo)

## Carregadores de formato e descompactacao
| Formato | Funcao | Endereco | Observacoes |
|---|---|---|---|

## Duvidas
-
```
