# generico.dds

- Empresa/motor: Microsoft DirectX
- Extensoes: .dds
- Ordem de bytes: little
- Tipo: textura
- Conversor: `converters/generico/dds_to_png.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://learn.microsoft.com/windows/win32/direct3ddds/dx-graphics-dds-pguide

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | 'DDS ' |
| 0x04 | u32 | 4 | dwSize = 124 |
| 0x08 | u32 | 4 | dwFlags |
| 0x0C | u32 | 4 | altura |
| 0x10 | u32 | 4 | largura |
| 0x14 | u32 | 4 | pitch ou tamanho linear |
| 0x1C | u32 | 4 | quantidade de mipmaps |
| 0x4C | u32 | 4 | DDS_PIXELFORMAT.dwSize = 32 |
| 0x50 | u32 | 4 | flags (0x4 FOURCC, 0x40 RGB, 0x1 ALPHAPIXELS) |
| 0x54 | char[4] | 4 | fourCC (DXT1/DXT3/DXT5/DX10) |
| 0x58 | u32 | 4 | bits por pixel |
| 0x5C..0x6B | u32 x4 | 16 | mascaras R, G, B, A |
| 0x70 | u32 | 4 | caps2 (cubemap 0x200, volume 0x200000) |
| 0x80 | bytes | ... | DX10: DDS_HEADER_DXT10 de 20 bytes (dxgiFormat primeiro); depois os dados |

## Exemplo em hex (`tests/fixtures/amostras/generico/dxt1.dds`, amostra sintetica)

```
00000000  44 44 53 20 7c 00 00 00 07 10 08 00 08 00 00 00  DDS |...........
00000010  08 00 00 00 20 00 00 00 00 00 00 00 01 00 00 00  .... ...........
00000020  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000030  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
00000040  00 00 00 00 00 00 00 00 00 00 00 00 20 00 00 00  ............ ...
00000050  04 00 00 00 44 58 54 31 00 00 00 00 00 00 00 00  ....DXT1........
00000060  00 00 00 00 00 00 00 00 00 00 00 00 00 10 00 00  ................
00000070  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
