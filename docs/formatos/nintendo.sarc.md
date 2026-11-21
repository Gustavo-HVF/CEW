# nintendo.sarc

- Empresa/motor: Nintendo (Wii U/3DS/Switch)
- Extensoes: .sarc, .pack, .bars, .blarc
- Ordem de bytes: big
- Tipo: conteiner
- Conversor: `converters/nintendo/sarc_to_dir.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://zeldamods.org/wiki/SARC

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | 'SARC' |
| 0x04 | u16 | 2 | tamanho do cabecalho (0x14) |
| 0x06 | u16 | 2 | BOM: FE FF big / FF FE little |
| 0x08 | u32 | 4 | tamanho do arquivo |
| 0x0C | u32 | 4 | offset dos dados |
| 0x10 | u16 | 2 | versao (0x0100) |
| 0x14 | char[4] | 4 | 'SFAT' + u16 tamanho, u16 quantidade, u32 chave do hash (0x65) |
| no | 4 x u32 | 16 | hash do nome, atributos (0x01 << 24 | offset/4 do nome), inicio, fim |
| depois | char[4] | 4 | 'SFNT' + nomes terminados em zero alinhados a 4 |

## Exemplo em hex (`tests/fixtures/amostras/nintendo/pacote.sarc`, amostra sintetica)

```
00000000  53 41 52 43 14 00 ff fe 14 06 00 00 00 01 00 00  SARC............
00000010  00 01 00 00 53 46 41 54 0c 00 03 00 65 00 00 00  ....SFAT....e...
00000020  3f dc df 18 00 00 00 01 00 00 00 00 e0 04 00 00  ?...............
00000030  8d 7e 23 50 03 00 00 01 e0 04 00 00 e5 04 00 00  .~#P............
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
