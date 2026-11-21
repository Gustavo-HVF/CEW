---
name: cew-inventario-formatos
description: Use para selecionar o alvo e mapear seus arquivos - "inventario", "que formato e este arquivo", magic bytes, abrir conteiners (SZS, U8, SARC, PAK, VPK, ZIP), formats/registry.json, adicionar formato novo ao registro.
---

# 02 - Inventario e mapeamento de formatos

## Gatilho
- Alvo novo (executavel, ROM, pacote de recursos, pasta de jogo), arquivo "desconhecido" no
  inventario, pedido para registrar um formato descoberto.

## Entradas
- Alvo (arquivo ou pasta) informado com `--alvo`.
- `formats/registry.json` (`schemas/registry.schema.json`).
- Opcional: `projects/<p>/analise/contexto.json` (camada 4) e `projects/<p>/tarefas_gemini/<sha>.resposta.json` (camada 5).

## Passos com comandos
1. `cew run --projeto <p> --alvo "<caminho>" --ate inventario` (ou `cew etapa alvo` + `cew etapa inventario`).
2. Ler `projects/<p>/inventario.json`: `resumo`, e para cada item `formato.camada`, `formato.confianca`,
   `estado` (identificado | desconhecido | compactado), `entropia_bits_por_byte`, `observacoes`.
3. Identificar um arquivo solto: `cew identificar <arquivo>`.
4. Para um desconhecido, abrir os bytes: `python -c "print(open('<arq>','rb').read(64).hex(' '))"` e
   comparar com `formats/registry.json`.
5. Formato novo confirmado (assinatura vista em >= 2 amostras + ferramenta ou especificacao real):
   - copie `docs/formatos/MODELO.md` para `docs/formatos/<id>.md` e preencha a tabela de campos;
   - acrescente a entrada no registro com `verificacao.estado: "a_verificar"` (ou superior se testado);
   - se precisar, escreva o verificador em `cew/estruturas.py` (`@verificador`) e cite o nome em
     `verificador_estrutura`;
   - `cew validar formats/registry.json` e `python -m pytest tests/test_registro.py tests/test_esquemas.py`.
6. Rode o inventario de novo: extracoes ja feitas sao reaproveitadas pelo SHA-256.

## Delegacao
- Gemini: nada nesta etapa (desconhecidos viram tarefa na etapa 5).
- IA principal: confirma identificacoes de baixa confianca, escreve regras de contexto e entradas do registro.

## Padroes de conversao
- Ordem das camadas: assinatura -> extensao -> estrutura -> contexto -> Gemini; a camada que decidiu
  fica registrada. Confianca < 0,3 = desconhecido.
- Conteineres e compressoes sao abertos recursivamente em `build/extraido/<id>/` com limites
  (profundidade 8, 8 GiB extraidos, 200 mil arquivos, protecao contra zip slip).
- Caminho logico com `!/` entre conteineres; ids `i_<16 hex>` derivados do caminho (estaveis).

## Saidas
- `projects/<p>/inventario.json` (`schemas/inventario.schema.json`).
- `projects/<p>/build/extraido/` (conteudo aberto).

## Criterios para avancar
- `inventario.json` valido e mapeado: todo item com formato (ou `desconhecido` explicito) e estado.

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| tudo `desconhecido` com entropia ~8 | provavelmente cifrado/compactado: o CEW nao decifra; procure a rotina de descompactacao no Ghidra (skill 03) |
| `.bin`/`.dat` genericos | escreva regra em `analise/contexto.json` com a funcao que carrega o arquivo |
| assinatura compartilhada (TIM x DFF) | confira `formato.candidatos`; melhore o verificador de estrutura |
| "profundidade maxima atingida" | aumente `Limites.profundidade_maxima` so se fizer sentido |
| texto `.txt` ignorado no plano | confirme por contexto para converter em `dados/dialogos` |
