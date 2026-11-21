# Decisoes e diferencas em relacao ao prompt

Registro pedido pela "regra de ouro": tudo o que foi conferido na fonte real, o que mudou em
relacao ao prompt original e o que ainda e hipotese. Datas no formato AAAA-MM-DD.

## Versoes conferidas

| Ferramenta | Versao usada | Como foi conferida |
|---|---|---|
| Craft Anything | commit `44c89badd69c` (workspace 0.6.1), 2026-11-20 | repositorio clonado; `apps/craft-anything-cli/src/*.rs`, `README.md`, `docs/tools.md`, `docs/STATUS.md`, `docs/file-formats.md`, `docs/schemas/craft.schema.json` lidos; `craft-anything-cli` compilado com Rust 1.97 e executado (`--version`, `doctor`, `commands`, `triage`, `settings-show`, `mcp`) |
| Ghidra | 12.1.4 (`ghidra_12.1.4_PUBLIC_20260921.zip`, SHA-256 `ddac49f9...d2d4db` igual ao da pagina de releases) | `Ghidra/application.properties` e `support/analyzeHeadlessREADME.md` lidos no repositorio oficial; `scripts/ghidra/ExportarCEW.java` executado de verdade em modo headless com OpenJDK 21 |
| API do Gemini | REST `generativelanguage.googleapis.com` | o site ai.google.dev nao resolvia no ambiente de construcao; o contrato foi lido no codigo do SDK oficial `google-genai` 3.6.1 (PyPI). O host respondeu 403 sem chave (alcancavel). **Nenhuma chamada com chave real foi feita aqui.** |
| glTF Validator (Khronos) | npm `gltf-validator` 2.0.0-dev.3.10 | GLB gerado pelo `md2_to_glb.py`: 0 erros, 0 avisos |
| ffmpeg | 6.1.1 | OGG Vorbis com `-fflags +bitexact`: mesma entrada -> mesmos bytes |
| Node / Vite / Playwright | Node 22, Vite 8.3.8, @playwright/test 1.65.1 | os quatro modelos web (Three.js 0.187.0, Babylon.js 9.37.1, Phaser 4.2.1, PixiJS 8.23.0) compilaram e passaram no teste de navegador |

## Diferencas em relacao ao prompt

1. **Logica em `cew/`, scripts como invólucros.** O prompt pede `scripts/orchestrator.py`,
   `scripts/setup_craft_anything.py` e `scripts/mcp_server.py` e um comando `cew` empacotado.
   Empacotar uma pasta chamada `scripts` como pacote Python instalaria um modulo global com nome
   generico. A logica ficou no pacote `cew/` (entrypoint `cew = "cew.cli:main"`) e os tres
   arquivos em `scripts/` existem e funcionam sem instalar nada, chamando o pacote.
2. **`craft.json` pertence ao Craft Anything.** Ele e a struct `Manifest` versionada
   (`MANIFEST_VERSION` = 5) e o Craft Anything nao preserva campos desconhecidos ao salvar.
   Por isso os caminhos relativos do CEW ficam em `projects/<nome>/cew.json`
   (`schemas/cew_projeto.schema.json`) e o `craft.json` que o CEW grava e minimo e validado
   contra o esquema publicado pelo proprio Craft Anything (copiado em
   `schemas/externos/craft-anything-craft.json`).
3. **`investigation.cany` e uma pasta de projeto** (com `project.toml`, criada pelo
   `craft-anything-cli --project`), nao um arquivo.
4. **O Craft Anything acha o Ghidra pela configuracao**, nao por `GHIDRA_INSTALL_DIR`
   (`engines.ghidra.install_dir` em `settings-show`). O `cew setup` repassa a pasta com
   `craft-anything-cli settings-set --key engines.ghidra.install_dir --value "<pasta>"`.
5. **Versao do Ghidra fixada em 12.1.4.** A 12.2 (mais nova) exige Java 25
   (`application.java.min=25`); a 12.1.4 exige Java 21 e e a que o proprio Craft Anything documenta
   em execucoes reais. Troque em `config/versoes.json` se tiver o JDK 25.
6. **Craft Anything ja tem servidor MCP** (`craft-anything-cli mcp`, 39 ferramentas Essenciais por
   padrao, todas com `--all-tools`). Os dois servidores estao em `.vscode/mcp.json` e `.mcp.json`:
   o do Craft Anything e o `cew-mcp` (as quatro ferramentas pedidas).
7. **Papel do Craft Anything no fluxo.** O CEW usa o Craft Anything como motor de inspecao (modo
   Deep: `triage`, ferramentas `game_*`, `native_*`, evidencias em `investigation.cany`). A
   reconstrucao do jogo pelo `craft-anything-cli rebuild` usa um agente de codigo (Claude Code) e
   continua disponivel, mas o CEW gera o projeto web a partir do `asset_manifest.json` no motor
   escolhido. As quatro fases do Craft Anything (Study/Build/Check/Ready) aparecem como
   `fase_craft_anything` em `estado.json`.
8. **Etapas.** O prompt lista 7 etapas; o `estado.json` tem 9 (`ambiente`, `alvo`, `inventario`,
   `engenharia`, `conversao`, `motor`, `reconstrucao`, `verificacao`, `pronto`) porque a etapa 7 do
   prompt junta reconstruir e verificar, e o item 9 tem o criterio "Motor -> Pronto".
9. **Gemini por REST, sem SDK.** `urllib` da biblioteca padrao, para nao depender da evolucao do
   SDK. Campos usados: `systemInstruction`, `contents`, `generationConfig.responseMimeType`,
   `responseJsonSchema` (ou `responseSchema`), `temperature`, `maxOutputTokens`,
   `thinkingConfig.thinkingLevel`; chave no cabecalho `x-goog-api-key`.
   - `responseJsonSchema` aceita so `$id $defs $ref $anchor type format title description enum
     items prefixItems minItems maxItems minimum maximum anyOf oneOf properties
     additionalProperties required` (docstring do SDK). Os esquemas `schemas/gemini/resposta_*`
     usam so isso (teste `test_respostas_gemini_so_usam_palavras_aceitas`); `enum` so com strings
     e numeros, por isso o `{"ok": true}` do teste de conexao e conferido no codigo.
   - Modelo padrao `gemini-3.8-flash`: e o nome usado nos exemplos do SDK 3.6.1. **Nao foi
     confirmado com chave real**; rode `cew gemini modelos` e ajuste `config/gemini.json`.
   - `versao_api` = `v1beta` (o SDK usa `v1` por padrao; as duas ficam configuraveis).
   - Precos por milhao de tokens ficam 0 ate voce preencher: com preco 0 o limite em dolares
     nao bloqueia, so os de chamadas e tokens.
10. **`cew-mcp` sem dependencias.** JSON-RPC 2.0 por stdio implementado na biblioteca padrao
    (initialize, ping, tools/list, tools/call), versoes de protocolo 2025-06-18, 2025-03-26 e
    2024-11-05. Testado por subprocesso.
11. **Tipos de formato a mais.** O enum `tipo` do registro ganhou `compressao`, `video`, `fonte` e
    `imagem` (Yaz0, USM e PNG nao cabiam nos tipos do prompt).
12. **Estado de verificacao do registro.** Alem de `confianca`, cada entrada tem `verificacao.estado`:
    `a_verificar` (semente, nada conferido em arquivo real), `fixtures_sinteticas` (conversor
    testado com amostra montada pela especificacao publica) e `verificado` (conferido com arquivos
    reais e ferramenta de referencia - nenhuma entrada chegou aqui ainda). Os repositorios das
    ferramentas de referencia foram confirmados com `git ls-remote` em 2026-11-20 (`verificado_em`),
    mas o suporte de cada ferramenta a cada formato nao foi testado. As URLs de documentacao nao
    foram abertas, exceto `qfiles.h` (Quake II) e `bspfile.h` (Quake), lidos no repositorio da id.
13. **Conteudo cifrado nao e decifrado.** O CEW nao tem bloqueio por origem, licenca ou patente,
    mas nao implementa quebra de DRM/cifra: formatos que costumam vir cifrados (NCA, CPK/HCA
    mascarados, indice AES de .pak do Unreal) ficam marcados e o inventario avisa quando a
    entropia sugere cifra. O Craft Anything segue a mesma regra ("never decrypting").
14. **Sandbox dos rascunhos do Gemini.** Processo separado, pasta propria, tempo limite, limites de
    memoria/CPU/arquivo (POSIX), proxies invalidos e um `sitecustomize` que bloqueia `socket`; no
    Linux com `unshare` liberado, tambem sem interface de rede no SO. No Windows so ha tempo limite
    e o bloqueio no nivel do Python: **nao e barreira contra codigo hostil** - a IA principal le o
    codigo antes de rodar (skill 04).
15. **Especificacoes por projeto.** As especificacoes de um alvo ficam em
    `projects/<nome>/especificacoes/`; `docs/especificacoes/` traz o modelo e o guia;
    `docs/formatos/` documenta os formatos com conversor.
16. **Raiz web.** Os assets publicados ficam em `projects/<nome>/web/` (com `asset_manifest.json`) e o
    projeto web gerado em `app/` serve essa pasta com `publicDir: '../web'` do Vite, sem copias.
17. **Motores com modelo gerado:** Three.js, Babylon.js, Phaser e PixiJS. Godot, Unity WebGL,
    PlayCanvas, Construct 3 e GDevelop recebem nota e o mapa de carregamento na skill 05, sem
    projeto gerado automaticamente.
18. **Regra de confirmacao de hipotese** (criterio Engenharia -> Conversao): uma hipotese gerada pelo
    CEW so fica `confirmada` se o conversor do formato foi testado E (ha documentacao publica +
    assinatura encontrada no arquivo, ou a identificacao no arquivo tem confianca >= 0,75). O resto
    fica `hipotese` ate a IA principal completar a evidencia (skill 03). Decisoes da IA principal
    (`confirmada`/`refutada` com evidencia) nao sao sobrescritas.
19. **Texto generico** (`.txt` identificado so pela extensao) nao e convertido sem evidencia de contexto
    (`analise/contexto.json`), para nao transformar todo leia-me em dialogo.
20. **IDs estaveis pelo caminho logico**, nao pelo conteudo: `i_`/`p_`/`a_` + 16 hex do SHA-256 do
    caminho (com `!/` entre conteineres, `/` como separador e Unicode NFC, para Windows, macOS e
    Linux darem o mesmo id). Assim a nova versao de um arquivo mantem o id e o caminho web, e o
    `hash_sha256` do manifesto muda (cache do navegador e comparacao entre versoes).
21. **Amostras de teste sinteticas.** Nenhum arquivo de jogo comercial esta no repositorio:
    `tests/fixtures/gerar_fixtures.py` monta cada amostra a partir da especificacao, de forma
    deterministica (os testes conferem que regenerar da os mesmos bytes).
22. **`--ignorar-ambiente`.** O criterio Ambiente -> Alvo bloqueia o fluxo com ferramenta obrigatoria
    faltando; a opcao existe para desenvolvimento e fica registrada no historico.
23. **Chromium do Playwright.** `CEW_CHROMIUM` (ou `--chromium`) aponta um Chromium ja instalado;
    sem isso use `npx playwright install chromium` em `app/`.

24. **Instalacao editavel.** O CEW le `schemas/`, `formats/`, `config/` e `converters/` da raiz do
    repositorio, entao o modo suportado e `pip install -e .` (ou rodar `scripts/orchestrator.py`).
    Uma instalacao nao editavel funciona para os conversores, mas a CLI precisa do repositorio.

## CEW v2.1 - o agente cria os conversores (docs/prompt_cew_agente_cria_conversores.txt)

25. **Revisao do prompt antes de aplicar.** Mudancas em relacao a v2: o registro global NAO foi enxugado
    (identificar e barato; so o codigo saiu do nucleo); cadeia de fontes configuravel em vez de copia
    obrigatoria do cookbook; conversor pode ser Python ou comando externo em JSON; conversores do
    projeto rodam em subprocesso; marcos configuraveis (modelos "jogo" e "app") em vez de M0-M6 fixos;
    contrato `window.__CEW_ESTADO` para os testes de marco; cobertura de conteudo medida pelas
    requisicoes do navegador; decisoes por formato no registro do projeto.
26. **Migracao.** `converters/{nintendo,sony,idtech,valve}` e `dds_to_png`/`tga_to_png` foram para
    `cookbook/` com `git mv` (historico preservado) e os testes continuam passando nos novos caminhos.
    Ficaram em `converters/`: `comum/`, `generico/{copiar_web,zip_to_dir,wav_to_ogg}`, `dados/texto_to_json`.
27. **Referencia de conversor.** `converters/...`, `cookbook/...` ou `projeto:conversores/...(.py|.json)`
    (relativo a pasta do projeto, para o projeto continuar valido se a pasta mudar de lugar).
28. **Isolamento.** Conversor de projeto roda em `python -m cew._executor` com RLIMIT_AS/RLIMIT_CPU (POSIX) e
    tempo limite; no Windows so o tempo limite. Comando externo roda com tempo limite e codigos de saida
    aceitos declarados. `executar_conversores_do_projeto_em: "processo"` desliga o isolamento (depuracao).
29. **Harness.** "robustez" aceita `ok=false` com erro de formato; reprova "falha inesperada" (excecao nao
    tratada) e tempo limite. Para comando externo, sair com erro em arquivo corrompido e aceitavel; travar
    nao. "ajuda" confere `--help` (Python) ou a presenca/versao da ferramenta (comando).
30. **Amostras do harness.** Reais: do inventario pelo id ja identificado OU pela extensao registrada (o
    formato acabou de ser registrado e o inventario ainda nao rodou de novo), escolhendo menor, maior e
    intermediarias; mais `referencias/amostras/`. Sinteticas: `conversores/<familia>/amostras/<conversor>/`
    e, filtradas pela extensao do formato, `amostras/` (dois conversores da mesma familia nao se misturam).
31. **Tentativas.** Cada reprovacao no harness soma 1 em `tentativas` do formato no registro do projeto; no
    limite (`max_tentativas_por_formato`) o formato vira `bloqueado` com o motivo, e o fluxo segue.
32. **Prioridade de um formato sem conversor** = alta se for de tipo essencial (textura, modelo, audio,
    mapa, dados...) ou desconhecido E tiver >= `prioridade_alta_min_itens` arquivos ou >= 10 MB. So
    prioridade alta bloqueia a etapa; media/baixa ficam visiveis no plano.
33. **Marcos.** Apenas o primeiro marco ("abre") vem obrigatorio e com teste real; os outros vem como
    `test.fixme` e o agente os torna obrigatorios conforme o escopo combinado com a pessoa. O Playwright
    informa o arquivo do teste relativo ao `testDir`; o CEW normaliza para `tests/...` (bug encontrado no
    teste real e corrigido).
34. **Exemplo de comando externo** (`schemas/exemplos/conversor_comando.json`): flags do vgmstream-cli
    (`-o`, `-V`) conferidas em `cli/vgmstream_cli.c` do repositorio oficial (commit 24ffd6c, 2026-11-10).

## Mapeamento e reposicionamento de elementos de cena

35. **Cena bruta x normalizada.** O conversor so le o que o formato diz (tipo, posicao, rotacao nas
    unidades e eixos do jogo) e declara o `sistema_coordenadas`; toda conversao de eixos, categoria,
    ligacao com assets e ajuste fica em `cew/cenas.py`, igual para todos os formatos. Um conversor novo
    escrito pelo agente nao precisa reimplementar nada disso.
36. **Rotacao.** Quaternion: parte vetorial transformada como pseudovetor (`v' = det(M) M v`), conferido
    por teste de propriedade (girar e converter == converter e girar) para as quatro combinacoes de
    eixo/mao. So guinada: mesmo angulo em torno do novo eixo para cima, sinal invertido na troca de mao.
    Arfagem e rolagem sem quaternion geram aviso (convencoes de Euler variam por motor).
37. **Ids de entidade.** `id_original` quando o formato tem (Tiled: id do objeto) - ajustes sobrevivem a
    nova versao do mapa; sem id (Quake): tipo + posicao original + ordem entre identicos, e um ajuste por
    entidade se perde se o objeto mudar de lugar no original (os ajustes por filtro continuam valendo; a
    verificacao avisa "ajuste nao encontrou entidades").
38. **Ligacao com assets** por ordem: regra (`asset_id`/`origem_glob`) > conversor > referencia de modelo do
    original (`modelo_original`) > ultimo token do tipo (`monster_ogre` -> arquivo `ogre.*`). Heuristica
    de nome desligada para spawn, gatilho, luz, som, camera e regiao.
39. **Quake BSP:** `angle` -1/-2 (portas/plataformas) e direcao, nao rotacao: vai para
    `propriedades.direcao`. Entidades de brush (`"model" "*n"`) nao tem `origin`: posicao [0,0,0] com
    `posicao_estimada`. A geometria do BSP nao e convertida (so as entidades).
40. **Tiled:** objeto-tile (com `gid`) ancorado na base esquerda em mapa ortogonal com alinhamento
    `unspecified` (comportamento conhecido do Tiled; a documentacao lida so lista as opcoes de
    `objectalignment` - hipotese a confirmar). Mapas infinitos (chunks) e compressao zstd ainda nao.
41. **Motores 3D com cena 2D** (e vice-versa): nada e descartado. Three.js/Babylon.js desenham a cena 2D
    como camada plana (`posicao_m`); Phaser/PixiJS desenham a cena 3D vista de cima (x, z). O teste de
    navegador exige `instanciadas == entidades` em toda cena (bug encontrado: antes o teste deixava
    passar cena ignorada).
42. **Babylon.js** passa a usar `scene.useRightHandedSystem = true`, para posicoes e quaternions das cenas
    (e do glTF) valerem sem conversao extra.

## Hipoteses tecnicas nos conversores (a conferir com arquivos reais)

- **MD2:** ordem das faces invertida por padrao (o glquake desenha com `glCullFace(GL_FRONT)`, ou
  seja, face visivel horaria); opcao `inverter_faces`. Normais calculadas da geometria (a tabela de
  162 normais do MD2 nao foi transcrita). Animacoes a 10 quadros/s.
- **CMPR/BC1:** interpolacao padrao S3TC (2/3 + 1/3); o hardware do GameCube pode diferir em 1-2
  niveis por canal.
- **PS-ADPCM:** `(h1*f0 + h2*f1) >> 6` sem arredondamento; deslocamentos > 12 tratados como 9.
- **TIM:** 0x0000 = transparente; o bit STP vira alfa 255 (semitransparencia do GPU nao tem
  equivalente direto).
- **Identificacao fraca:** LZ10/LZ11 so pela razao de compressao plausivel; assinatura do `.pak`
  do Unreal no rodape varia por versao.

## Nao testado neste ambiente

- Chamada real ao Gemini com chave (todos os testes usam transporte falso; o contrato vem do SDK).
- Windows e macOS (o codigo trata caminhos com espacos/acentos e NFC; os testes rodaram no Linux).
- Compilacao do app desktop do Craft Anything (`--com-app`); so o CLI foi compilado.
- Conversores contra arquivos reais de jogos (so amostras sinteticas).
