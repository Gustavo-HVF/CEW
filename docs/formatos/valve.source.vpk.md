# valve.source.vpk

- Empresa/motor: Valve (Source)
- Extensoes: .vpk
- Ordem de bytes: little
- Tipo: conteiner
- Conversor (receita do cookbook): `cookbook/valve/vpk_to_dir.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia

Documentacao publica usada:

- https://developer.valvesoftware.com/wiki/VPK_(file_format)

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | u32 LE | 4 | 0x55AA1234 |
| 0x04 | u32 LE | 4 | versao (1 ou 2) |
| 0x08 | u32 LE | 4 | tamanho da arvore |
| 0x0C (v2) | u32 x4 | 16 | secao de dados, MD5 dos arquivos, MD5 geral, assinatura |
| arvore | strings | ... | extensao\0 { caminho\0 { nome\0 entrada }* \0 }* \0; ' ' = vazio |
| entrada | u32,u16,u16,u32,u32,u16 | 18 | CRC32, bytes de preload, indice do arquivo (0x7FFF = este), offset, tamanho, 0xFFFF |

## Exemplo em hex (`tests/fixtures/amostras/valve/pak01_dir.vpk`, amostra sintetica)

```
00000000  34 12 aa 55 02 00 00 00 68 00 00 00 2e 00 00 00  4..U....h.......
00000010  00 00 00 00 00 00 00 00 00 00 00 00 74 78 74 00  ............txt.
00000020  20 00 6c 65 69 61 00 02 de c6 50 00 00 ff 7f 00   .leia....P.....
00000030  00 00 00 04 00 00 00 ff ff 00 73 63 72 69 70 74  ..........script
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
