# idtech.quake2.md2

- Empresa/motor: id Software (Quake II)
- Extensoes: .md2
- Ordem de bytes: little
- Tipo: modelo
- Conversor (receita do cookbook): `cookbook/idtech/md2_to_glb.py`
- Estado no registro: `fixtures_sinteticas` - conversor testado com amostra sintetica montada pela especificacao publica (tests/fixtures/gerar_fixtures.py); falta conferir com arquivo real e ferramenta de referencia; estrutura conferida em qcommon/qfiles.h; GLB aprovado pelo glTF Validator 2.0.0-dev.3.10

Documentacao publica usada:

- https://github.com/id-Software/Quake-2/blob/master/qcommon/qfiles.h

## Campos

| Offset | Tipo | Tamanho | Descricao |
|---|---|---|---|
| 0x00 | char[4] | 4 | 'IDP2' |
| 0x04 | s32 LE | 4 | versao 8 |
| 0x08 | s32 x2 | 8 | largura e altura da skin |
| 0x10 | s32 | 4 | tamanho de cada quadro (40 + 4 * vertices) |
| 0x14..0x2B | s32 x6 | 24 | num_skins, num_xyz, num_st, num_tris, num_glcmds, num_frames |
| 0x2C..0x43 | s32 x6 | 24 | ofs_skins, ofs_st, ofs_tris, ofs_frames, ofs_glcmds, ofs_end |
| st | s16 x2 | 4 | s, t (pixels da skin) |
| tri | u16 x6 | 12 | index_xyz[3], index_st[3] |
| quadro | f32 x6 + char[16] | 40 | scale[3], translate[3], nome; depois num_xyz x (u8 v[3], u8 indice da normal) |

## Exemplo em hex (`tests/fixtures/amostras/idtech/tetra.md2`, amostra sintetica)

```
00000000  49 44 50 32 08 00 00 00 40 00 00 00 40 00 00 00  IDP2....@...@...
00000010  38 00 00 00 01 00 00 00 04 00 00 00 04 00 00 00  8...............
00000020  04 00 00 00 00 00 00 00 03 00 00 00 44 00 00 00  ............D...
00000030  84 00 00 00 94 00 00 00 c4 00 00 00 6c 01 00 00  ............l...
00000040  6c 01 00 00 6d 6f 64 65 6c 73 2f 63 65 77 2f 73  l...models/cew/s
```

## O que falta confirmar

- Conferir com arquivos reais e com uma ferramenta de referencia do registro antes de marcar `verificado`.
