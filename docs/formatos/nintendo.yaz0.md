# nintendo.yaz0

- Empresa/motor: Nintendo (GameCube/Wii/Switch)
- Extensoes: .szs, .yaz0, .carc
- Ordem de bytes: big
- Tipo: compressao
- Conversor (receita do cookbook): `cookbook/nintendo/yaz0_to_bin.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- http://www.amnoid.de/gc/yaz0.txt

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | magic 'Yaz0' |
| 0x04 | u32 BE | 4 | tamanho descompactado |
| 0x08 | u32 BE | 4 | alinhamento (versoes novas) / reservado |
| 0x0C | u32 | 4 | reservado |
| 0x10 | bytes | ... | grupos: 1 byte de flags (bit 7 primeiro); 1 = literal, 0 = referencia de 2 ou 3 bytes (distancia 12 bits + tamanho 4 bits; tamanho 0 -> proximo byte + 0x12) |

## Exemplo em hex (`tests/fixtures/amostras/nintendo/arquivo.szs`, amostra sintetica)

```
00000000  59 61 7a 30 00 00 05 e0 00 00 00 00 00 00 00 00  Yaz0............
00000010  ff 55 aa 38 2d 00 00 00 20 52 10 03 83 10 03 c0  .U.8-... R......
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
