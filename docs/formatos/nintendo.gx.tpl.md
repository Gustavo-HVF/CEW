# nintendo.gx.tpl

- Empresa/motor: Nintendo (GameCube/Wii)
- Extensoes: .tpl
- Ordem de bytes: big
- Tipo: textura
- Conversor (receita do cookbook): `cookbook/nintendo/tpl_to_png.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://wiki.tockdom.com/wiki/TPL_(File_Format)

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | u32 BE | 4 | magic 0x0020AF30 |
| 0x04 | u32 BE | 4 | quantidade de imagens |
| 0x08 | u32 BE | 4 | offset da tabela (0x0C) |
| tabela | 2 x u32 | 8 | offset do cabecalho da imagem, offset do cabecalho da paleta (0 = nenhum) |
| img+0x00 | u16 BE | 2 | altura |
| img+0x02 | u16 BE | 2 | largura |
| img+0x04 | u32 BE | 4 | formato GX (0 I4, 1 I8, 2 IA4, 3 IA8, 4 RGB565, 5 RGB5A3, 6 RGBA32, 8 C4, 9 C8, 0xA C14X2, 0xE CMPR) |
| img+0x08 | u32 BE | 4 | offset dos dados |
| img+0x0C..0x1F | u32 x4, f32 | 20 | wrapS, wrapT, minFilter, magFilter, LODBias |
| img+0x20 | u8 x4 | 4 | edgeLOD, minLOD, maxLOD, desempacotado |
| pal+0x00 | u16 BE | 2 | quantidade de cores |
| pal+0x04 | u32 BE | 4 | formato da paleta (0 IA8, 1 RGB565, 2 RGB5A3) |
| pal+0x08 | u32 BE | 4 | offset dos dados da paleta |

## Exemplo em hex (`tests/fixtures/amostras/nintendo/texturas.tpl`, amostra sintetica)

```
00000000  00 20 af 30 00 00 00 08 00 00 00 0c 00 00 00 4c  . .0...........L
00000010  00 00 00 00 00 00 00 70 00 00 00 00 00 00 00 94  .......p........
00000020  00 00 00 00 00 00 00 b8 00 00 00 00 00 00 00 dc  ................
00000030  00 00 00 00 00 00 01 00 00 00 00 00 00 00 01 24  ...............$
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
