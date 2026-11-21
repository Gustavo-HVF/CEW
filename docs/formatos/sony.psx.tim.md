# sony.psx.tim

- Empresa/motor: Sony (PlayStation)
- Extensoes: .tim
- Ordem de bytes: little
- Tipo: textura
- Conversor (receita do cookbook): `cookbook/sony/tim_to_png.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://psx-spx.consoledev.net/

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | u32 LE | 4 | id 0x00000010 |
| 0x04 | u32 LE | 4 | flags: bits 0-2 modo (0 4bpp, 1 8bpp, 2 16bpp, 3 24bpp), bit 3 tem CLUT |
| clut+0x00 | u32 LE | 4 | tamanho do bloco (inclui 12 bytes) |
| clut+0x04 | u16 x2 | 4 | x, y na VRAM |
| clut+0x08 | u16 | 2 | cores por CLUT |
| clut+0x0A | u16 | 2 | quantidade de CLUTs |
| img+0x00 | u32 LE | 4 | tamanho do bloco |
| img+0x04 | u16 x2 | 4 | x, y na VRAM |
| img+0x08 | u16 | 2 | largura em unidades de 16 bits |
| img+0x0A | u16 | 2 | altura |
| img+0x0C | bytes | ... | pixels; 4bpp com nibble baixo primeiro; cor 16 bits R 0-4, G 5-9, B 10-14, STP 15; 0x0000 transparente |

## Exemplo em hex (`tests/fixtures/amostras/sony/imagem4.tim`, amostra sintetica)

```
00000000  10 00 00 00 08 00 00 00 4c 00 00 00 00 00 e0 01  ........L.......
00000010  10 00 02 00 00 00 01 84 02 88 03 8c 04 90 05 94  ................
00000020  06 98 07 9c 08 a0 09 a4 0a a8 0b ac 0c b0 0d b4  ................
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
