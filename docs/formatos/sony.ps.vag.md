# sony.ps.vag

- Empresa/motor: Sony (PlayStation)
- Extensoes: .vag
- Ordem de bytes: big
- Tipo: audio
- Conversor: `converters/sony/vag_to_wav.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | 'VAGp' |
| 0x04 | u32 BE | 4 | versao |
| 0x08 | u32 BE | 4 | reservado |
| 0x0C | u32 BE | 4 | tamanho dos dados |
| 0x10 | u32 BE | 4 | taxa de amostragem (Hz) |
| 0x14 | bytes | 12 | reservado |
| 0x20 | char[16] | 16 | nome |
| 0x30 | quadros | 16 | PS-ADPCM: byte 0 = filtro<<4 | deslocamento, byte 1 = flags (0x04 inicio do loop, 0x03 fim do loop, 0x01 fim), 14 bytes = 28 amostras de 4 bits (nibble baixo primeiro) |

## Exemplo em hex (`tests/fixtures/amostras/sony/som.vag`, amostra sintetica)

```
00000000  56 41 47 70 00 00 00 20 00 00 00 00 00 00 00 50  VAGp... .......P
00000010  00 00 56 22 00 00 00 00 00 00 00 00 00 00 00 00  ..V"............
00000020  63 65 77 5f 74 65 73 74 65 00 00 00 00 00 00 00  cew_teste.......
00000030  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
