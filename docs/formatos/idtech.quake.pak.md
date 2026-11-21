# idtech.quake.pak

- Empresa/motor: id Software (Quake/Quake II)
- Extensoes: .pak
- Ordem de bytes: little
- Tipo: conteiner
- Conversor (receita do cookbook): `cookbook/idtech/pak_to_dir.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia; estrutura conferida em qcommon/qfiles.h

Documentacao publica usada:

- https://github.com/id-Software/Quake-2/blob/master/qcommon/qfiles.h

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | 'PACK' |
| 0x04 | s32 LE | 4 | offset do diretorio |
| 0x08 | s32 LE | 4 | tamanho do diretorio (multiplo de 64) |
| dir | char[56] + 2 x s32 | 64 | nome, offset, tamanho |

## Exemplo em hex (`tests/fixtures/amostras/idtech/pak0.pak`, amostra sintetica)

```
00000000  50 41 43 4b b8 01 00 00 80 00 00 00 1d 00 00 00  PACK............
00000010  00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00  ................
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
