# generico.tga

- Empresa/motor: Truevision
- Extensoes: .tga
- Ordem de bytes: little
- Tipo: textura
- Conversor (receita do cookbook): `cookbook/generico/tga_to_png.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | u8 | 1 | tamanho do id |
| 0x01 | u8 | 1 | tem mapa de cores |
| 0x02 | u8 | 1 | tipo (1/2/3 sem compressao, 9/10/11 RLE) |
| 0x03 | u16 LE x2 + u8 | 5 | primeira entrada, quantidade e bits do mapa |
| 0x08 | u16 x2 | 4 | origem x, y |
| 0x0C | u16 | 2 | largura |
| 0x0E | u16 | 2 | altura |
| 0x10 | u8 | 1 | bits por pixel |
| 0x11 | u8 | 1 | descritor: bits 0-3 alfa, bit 4 direita->esquerda, bit 5 origem em cima |

## Exemplo em hex (`tests/fixtures/amostras/generico/imagem.tga`, amostra sintetica)

```
00000000  00 00 0a 00 00 00 00 00 00 00 00 00 08 00 08 00  ................
00000010  20 28 00 00 00 00 ff 00 00 00 24 ff 00 00 00 48   (........$....H
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
