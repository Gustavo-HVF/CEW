# nintendo.u8

- Empresa/motor: Nintendo (Wii/GameCube)
- Extensoes: .arc, .u8
- Ordem de bytes: big
- Tipo: conteiner
- Conversor: `converters/nintendo/u8_to_dir.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://wiibrew.org/wiki/U8_archive

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | u32 BE | 4 | magic 0x55AA382D |
| 0x04 | u32 BE | 4 | offset do no raiz (0x20) |
| 0x08 | u32 BE | 4 | tamanho dos nos + tabela de nomes |
| 0x0C | u32 BE | 4 | offset dos dados |
| 0x10 | bytes | 16 | reservado |
| no+0x00 | u8 | 1 | tipo (0 arquivo, 1 pasta) |
| no+0x01 | u24 BE | 3 | offset do nome na tabela |
| no+0x04 | u32 BE | 4 | arquivo: offset dos dados / pasta: indice do pai |
| no+0x08 | u32 BE | 4 | arquivo: tamanho / pasta: indice do proximo no fora da pasta |

## Exemplo em hex (`tests/fixtures/amostras/nintendo/arquivo.arc`, amostra sintetica)

```
00000000  55 aa 38 2d 00 00 00 20 00 00 00 83 00 00 00 c0  U.8-... ........
00000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000020  01 00 00 00 00 00 00 00 00 00 00 07 01 00 00 01  ................
00000030  00 00 00 00 00 00 00 04 01 00 00 07 00 00 00 01  ................
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
