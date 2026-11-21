---
name: cew-criar-conversores
description: Use quando o plano tiver formato sem conversor ("falta_conversor", ".xnb", "formato desconhecido") ou para criar, embrulhar, testar e registrar um conversor no projeto - cew novo-conversor, conversor-testar, formato-registrar, cookbook, harness, decisao de ignorar/bloquear.
---

# 04 - Criar conversores no projeto (o agente escreve)

## Gatilho
- `plano_conversao.json` com grupos `falta_conversor` em `formatos[]` (o criterio da etapa conversao
  bloqueia formato de prioridade alta sem conversor nem decisao).
- Pessoa pede para converter um formato que nenhuma fonte cobre (ex.: `.xnb` do Terraria).
- Conversor do projeto reprovado ou desatualizado no harness (o codigo mudou).

## Entradas
- `plano_conversao.json` (`formatos[]`: formato, itens, bytes, cobertura, prioridade, decisao).
- `inventario.json`, `formats/registry.json` (global) e `formatos.json` (do projeto, mesmo esquema).
- `config/cew.json`: `fontes_conversores` (padrao `projeto -> cookbook -> generico`), limites do harness.
- `analise/carregadores.json` e o pseudo-C do Ghidra/Craft Anything (skill 03).
- Esquemas: `conversor_resultado`, `conversor_comando`, `conversor_projeto`, `log_conversor`, `registry`.

## Passos com comandos
Ciclo por formato, do grupo de prioridade mais alta para o mais baixo:
1. **Pesquisar** documentacao real do formato (especificacao publica, codigo aberto, ferramentas de
   referencia do registro) e/ou o carregador no programa original. Registre as fontes:
   `cew log-conversor <id> pesquisar --projeto P --detalhes "..." --evidencia "url ou funcao@endereco"`.
2. **Amostrar** 3-5 arquivos reais variados (o harness ja escolhe menor/maior/intermediarios) e ler os
   cabecalhos em hex: `python -c "print(open('<arq>','rb').read(64).hex(' '))"`.
3. **Registrar o formato** (assinatura e extensao; faz o inventario passar a identifica-lo):
   `cew formato-registrar empresa.familia.nome --projeto P --extensao xnb --assinatura 584e42 --tipo textura --destino png --ordem little --empresa "Microsoft XNA"`.
4. **Escrever** - escolha um caminho:
   - Python: `cew novo-conversor <id> --projeto P --destino png` gera o esqueleto com leitura defensiva;
   - comando externo (ferramenta pronta: vgmstream-cli, ffmpeg, binario Rust, script Node):
     `cew novo-conversor <id> --projeto P --tipo comando --destino wav` e edite o JSON
     (marcadores `{entrada}`, `{saida}`, `{saida_arquivo:nome}`, `{opcao:x}`, `{python}`, `{projeto}`);
   - receita existente: `cew conversor-copiar cookbook/<familia>/<nome>.py --projeto P` e adapte.
5. **Amostra sintetica minima** (montada pela especificacao, nunca arquivo comercial) em
   `conversores/<familia>/amostras/<nome-do-conversor>/` ou em `amostras/` com a extensao do formato.
6. **Testar**: `cew conversor-testar projeto:conversores/<familia>/<nome>.py --projeto P [--entrada ARQ]`
   -> executa, esquema, determinismo, robustez (truncados/corrompidos), dry-run, --help, tempo/memoria;
   grava `<nome>.teste.json` com o hash do codigo. Reprovado = tentativa contada.
7. **Conferir** com referencia independente quando existir (ferramenta de referencia, imagem que o jogo
   desenha, duracao do audio) e registre a metrica: `cew log-conversor <id> conferir --resultado ok --detalhes "SSIM 0.99"`.
8. **Ligar**: `cew formato-registrar <id> --projeto P --conversor projeto:conversores/<familia>/<nome>.py`
   e documente em `especificacoes/<id>.md` (modelo: `docs/formatos/MODELO.md`).
9. `cew etapa conversao --projeto P` (refaz so o que mudou: hash do arquivo e do conversor).
Quando nao der: `cew formato-registrar <id> --projeto P --decisao ignorar|substituir|bloqueado --motivo "..."`.
No limite de tentativas (`config/cew.json`), o harness marca `bloqueado` sozinho, com o motivo.

## Delegacao
- Gemini (opcional): hipotese de estrutura e rascunho (`schemas/gemini/tarefa_formato`), so trechos
  relevantes (cabecalhos em hex, pseudo-C do carregador). Rascunho roda antes em `cew sandbox`.
- IA principal: pesquisa, escreve, revisa, testa e registra. Nada entra no projeto sem harness aprovado.

## Padroes de conversao
- Leitura defensiva: `LeitorBinario`, `exigir`, `contagem_plausivel`, `limitar_tamanho`; nada de indice
  sem conferencia (o harness reprova "falha inesperada").
- Saidas: PNG (sRGB para cor, linear para normal), GLB (Y para cima, metros), WAV/OGG com loop em
  metadados, JSON com esquema (`schemas/dados/*`), pasta para conteineres (papel `extrator`).
- Determinismo: sem data/hora nem aleatoriedade; `ffmpeg` com `+bitexact`.
- Biblioteca comum primeiro (`converters/comum/`); se faltar algo geral, acrescente la, com teste.

## Saidas
- `projects/P/conversores/**` (codigo, `.teste.json`, amostras sinteticas), `formatos.json`,
  `log_conversores.jsonl`, `especificacoes/<id>.md`.

## Criterios para avancar
- Plano sem itens em erro; nenhum grupo `falta_conversor` de prioridade alta sem decisao; todo
  conversor do projeto em uso com `.teste.json` aprovado para o hash atual do codigo.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| harness: `robustez` reprovada ("falha inesperada") | leia com `LeitorBinario`/`exigir` em vez de indexar bytes |
| `tempo limite excedido` | laco sem condicao de saida ou contagem lida sem limite |
| `nenhuma amostra` | rode o inventario, registre a extensao do formato ou passe `--entrada` |
| `teste do harness reprovado ou desatualizado` | o codigo mudou: rode `cew conversor-testar` de novo |
| comando: `ferramenta nao encontrada` | instale a ferramenta ou ponha o caminho absoluto no JSON |
| itens continuam `desconhecido` | o formato nao foi registrado com assinatura/extensao: passo 3 |

## Caso trabalhado (formato ficticio, igual ao teste `tests/test_kit_agente.py`)
```bash
cew formato-registrar demo.qzx.imagem --projeto P --extensao qzx --assinatura 515a5831 --tipo textura --destino png --ordem big
cew novo-conversor demo.qzx.imagem --projeto P            # -> conversores/demo/qzx_imagem_to_png.py
# implementar: exigir 'QZX1'; largura/altura u16 BE em 4 e 6; RGBA a partir de 8; esc.gravar("imagem.png", ...)
cew conversor-testar projeto:conversores/demo/qzx_imagem_to_png.py --projeto P   # APROVADO
cew formato-registrar demo.qzx.imagem --projeto P --conversor projeto:conversores/demo/qzx_imagem_to_png.py
cew etapa conversao --projeto P
```
Versao comando (som): o JSON chama `{python} {projeto}/conversores/ferramentas/qzs2wav.py {entrada} {saida_arquivo:som.wav}`;
o CEW le a taxa e a duracao do WAV gerado e preenche os metadados do manifesto.
