---
name: cew-motor-grafico
description: Use para escolher o motor grafico web e montar o projeto - "qual motor", Phaser, PixiJS, Three.js, Babylon.js, PlayCanvas, Godot HTML5, Unity WebGL, Construct 3, GDevelop, recomendacao_motor.json, carregar asset_manifest.json no motor, gerar app/.
---

# 05 - Selecao e arquitetura do motor grafico

## Gatilho
- Etapa `motor` (escolha) ou `reconstrucao` (gerar o projeto web); pedido para trocar de motor.

## Entradas
- `inventario.json`, `web/asset_manifest.json`, `especificacoes/logica.md`.
- Preferencias da pessoa: fisica, interface, multijogador, dispositivos, experiencia da equipe
  (`--perfil '{"fisica": "complexa", "experiencia_equipe": ["typescript"]}'`).

## Passos com comandos
1. `cew etapa motor --projeto <p>` -> `recomendacao_motor.json` com nota 0-10, motivos e alertas por motor.
2. Mostrar a tabela a pessoa; **a escolha e dela**: `cew etapa motor --projeto <p> --motor <id>`.
3. `cew etapa reconstrucao --projeto <p> [--modelo-marcos jogo|app]` gera `app/` (Three.js, Babylon.js, Phaser ou PixiJS) com Vite,
   carregador do manifesto, teste Playwright e `marcos.json` (skill 07). Depois: `cd projects/<p>/app && npm install && npm run dev`.
4. Implementar o jogo em `app/src/` a partir de `especificacoes/logica.md` e `web/dados/*.json`,
   carregando assets sempre pelo id do manifesto (`manifesto.get(id)`), nunca por caminho solto.
5. Motores sem modelo automatico: criar o projeto na estrutura oficial (tabela abaixo) e apontar o
   carregamento para `asset_manifest.json`; `cew check` funciona igual se houver `app/package.json`
   com `build` e testes Playwright.

## Delegacao
- Gemini: nada obrigatorio; pode resumir trechos de logica em lote (skill 03).
- IA principal: pontuacao final, explicacao a pessoa, arquitetura de `app/` e todo o codigo do jogo.

## Padroes de conversao

Carregamento do `asset_manifest.json` em cada motor:
| Motor | Modelos `.glb` | Texturas | Audio com loop | Dados JSON | Estrutura / build |
|---|---|---|---|---|---|
| Three.js | `GLTFLoader` (`three/addons/loaders/GLTFLoader.js`); animacao com `AnimationMixer`; KTX2 com `KTX2Loader` | `TextureLoader`, `colorSpace = SRGBColorSpace` para cor | Web Audio `AudioBufferSourceNode.loopStart/loopEnd` = amostra / taxa (ja em `src/manifesto.js`) | `fetch` | Vite: `index.html`, `src/`, `publicDir: '../web'`, `npm run build` -> `dist/` |
| Babylon.js | `SceneLoader.ImportMeshAsync('', pasta, arquivo, cena)` com `@babylonjs/loaders/glTF`; `animationGroups` | `Texture` | igual (Web Audio) ou `Sound` com `loopStart/loopEnd` (conferir na versao) | `fetch` | Vite, igual ao Three.js |
| Phaser | (2D) | `this.load.image(id, url)` no `preload` | `this.load.audio` + marcadores, ou o `Audio` do CEW | `this.load.json` | Vite; `new Phaser.Game({scene: [...]})` |
| PixiJS | (2D) | `await Assets.load(url)`; `TextureStyle.defaultOptions.scaleMode = 'nearest'` para pixel art | Web Audio (o CEW) | `fetch` | Vite; `await app.init({...})` (v8) |
| PlayCanvas | `app.assets.loadFromUrl(url, 'container', cb)` e `asset.resource.instantiateRenderEntity()` | `loadFromUrl(url, 'texture')` | `SoundComponent` com slots (conferir suporte a loopStart) | `'json'` | editor na nuvem ou engine-only com bundler; build exportado pelo editor |
| Godot (4.x) | importar `.glb` no editor (ou `GLTFDocument` em tempo de execucao) | importar PNG; KTX2 conforme suporte da versao | `AudioStreamOggVorbis.loop` + `loop_offset` em segundos | `FileAccess` + `JSON.parse_string` | projeto com `project.godot`; Exportar > Web gera `.html/.js/.wasm/.pck`; C# na web: verificar a versao |
| Unity WebGL | pacote glTFast (`com.unity.cloud.gltfast`) para `.glb` em tempo de execucao, ou importar no editor | `UnityWebRequestTexture` | `AudioClip` + loop manual por amostra (`AudioSource.timeSamples`) | `UnityWebRequest` + `JsonUtility` | `Assets/`, `ProjectSettings/`; Build Settings > WebGL; atencao ao tamanho no celular |
| Construct 3 | (2D; 3D limitado) | importar imagens nos objetos | Audio com loop do arquivo inteiro; pontos de loop exigem cortar o audio | plugin AJAX + JSON | editor; exportar "Web (HTML5)" |
| GDevelop | (2D; objetos 3D basicos) | recursos do projeto | Sound/Music; pontos de loop exigem cortar o audio | extensao/acao de leitura de JSON | editor; exportar para Web |

Regras gerais: todos os `caminho_web` sao relativos a `web/`; respeite `metadados.espaco_cor`,
`tem_alfa`, `eixo_para_cima` (sempre Y) e `escala_metros`; textura nao potencia de 2 pode precisar de
`wrap = clamp` e sem mipmaps no WebGL1.

## Saidas
- `recomendacao_motor.json` (`schemas/recomendacao_motor.schema.json`) com `escolha_usuario`.
- `projects/<p>/app/` (projeto web) e `app/tests/cenas.json` (uma cena por `referencias/<cena>.png`).

## Criterios para avancar
- Motor escolhido e registrado; `app/` gerado e carregando `asset_manifest.json`
  (o build e os testes sao conferidos na skill 06).

## Erros comuns e o que fazer
| Sintoma | Acao |
|---|---|
| tela preta, nenhum erro | confira `publicDir` e se `web/asset_manifest.json` existe |
| 404 no console | caminho fora do manifesto (ou `favicon`: o modelo ja inclui icone vazio) |
| textura escura/lavada | espaco de cor errado (sRGB x linear) |
| modelo deitado/espelhado | conversor nao converteu eixos; confira `eixo_para_cima` e a ordem das faces |
| audio nao toca | navegadores exigem gesto do usuario antes do `AudioContext` |
