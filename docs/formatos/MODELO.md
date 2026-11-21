# empresa.familia.nome

Use este modelo para todo formato novo descoberto e confirmado (item 4.4). Depois de confirmar,
acrescente a entrada em formats/registry.json (validada por schemas/registry.schema.json).

- Empresa/motor:
- Extensoes:
- Ordem de bytes: big | little
- Tipo: conteiner | compressao | modelo | textura | animacao | audio | video | mapa | dados | codigo
- Conversor: converters/<empresa>/<formato>_to_<destino>.py
- Confianca: documentado | engenharia_reversa | hipotese

## Campos

| Offset | Tipo | Tamanho | Descricao | Evidencia (funcao/endereco ou documento) |
|---|---|---|---|---|
| 0x00 | char[4] | 4 | magic | bytes 00-03 de N amostras; funcao `carregar_x` em 0x401000 |

## Exemplo em hex

```
00000000  ...
```

## Evidencias

- Ghidra: funcao, endereco, trecho de pseudo-C (analise/<programa>.json)
- Amostras: quais arquivos do inventario confirmam cada campo

## Duvidas

-
