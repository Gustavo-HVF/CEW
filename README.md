# CEW - Convert Everything for the Web

O CEW analisa um aplicativo, ROM ou jogo, identifica o formato de cada arquivo (inclusive de qual
empresa ou motor ele veio), converte os recursos para formatos abertos da web com tudo descrito em
JSON validado por esquema, e gera um projeto que roda no navegador no motor grafico que voce escolher.

Ele junta tres pecas:

- **[Craft Anything](https://github.com/storytold/craft-anything)** (modo Deep): inspecao de
  programas, jogos e arquivos, com evidencias (`craft-anything-cli`, tambem como servidor MCP);
- **Ghidra** em modo headless: funcoes, strings, grafo de chamadas e pseudo-C exportados para JSON;
- **API do Gemini** como IA secundaria: analise em lote de formatos desconhecidos, rascunhos de
  conversor e segunda opiniao visual, sempre com saida em JSON validado.

A IA principal e o agente de programacao no VS Code (Claude Code, Codex ou outro): ela decide a
arquitetura, revisa todo codigo gerado e e a unica que grava no repositorio. As skills em `skills/`
dizem a ela o que fazer em cada etapa.

> Use o CEW em software que voce possui ou tem permissao para examinar. O CEW nao decifra conteudo
> protegido (DRM, pacotes cifrados): ele identifica, registra e segue com o que estiver legivel.

## Requisitos

| Ferramenta | Versao | Para que |
|---|---|---|
| Python | 3.10+ | o CEW |
| Node.js + npm | 20+ | ajv, glTF Validator, projeto web (Vite, Playwright) |
| git | qualquer recente | clonar o Craft Anything |
| Rust (rustup) | 1.97+ | compilar o `craft-anything-cli` (o README dele pede 1.97) |
| ffmpeg | qualquer recente | WAV -> OGG; `ffprobe` na verificacao |
| Java (JDK) | 21 para Ghidra 12.1.x (25 para 12.2) | modo Deep com Ghidra (opcional) |
| Ghidra | 12.1.4 (fixado em `config/versoes.json`) | modo Deep (opcional) |
| Blender | opcional | inspecao manual de modelos |
| Chave do Gemini | obrigatoria | https://aistudio.google.com/apikey |

## Instalacao

### Linux e macOS

```bash
git clone <este repositorio> CEW && cd CEW
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
npm install --ignore-scripts
cp .env.example .env        # preencha GEMINI_API_KEY (e GHIDRA_INSTALL_DIR, se usar o Ghidra)
cew setup                   # clona e compila o Craft Anything, roda o doctor, testa o Gemini
```

### Windows (PowerShell)

```powershell
git clone <este repositorio> CEW; cd CEW
py -3 -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
npm install --ignore-scripts
Copy-Item .env.example .env   # preencha GEMINI_API_KEY e, se usar, GHIDRA_INSTALL_DIR=C:\ferramentas\ghidra_12.1.4_PUBLIC
cew setup
```

Rust: https://rustup.rs (`rustup update` para ter 1.97+). ffmpeg: pelo gerenciador de pacotes
(`apt install ffmpeg`, `brew install ffmpeg`, `winget install Gyan.FFmpeg`). Ghidra: baixe o zip
de `config/versoes.json`, confira o SHA-256 e extraia.

Sem instalar o pacote, tudo funciona com `python scripts/orchestrator.py <comando>`.

## Uso no VS Code

1. Abra a pasta do CEW. O `.vscode/` traz:
   - `tasks.json`: **Terminal > Run Task > "CEW: ..."** para setup, cada etapa, fluxo completo,
     verificacao, testes e o jogo web em modo dev;
   - `launch.json`: depurar a CLI, um conversor ou o servidor MCP;
   - `mcp.json`: servidores MCP `cew-mcp` (listar_projetos, estado_da_etapa, rodar_conversor,
     ver_manifesto) e `craft-anything` (`craft-anything-cli --deep mcp`);
   - `settings.json`: pytest e validacao dos JSON pelos esquemas enquanto voce edita.
2. Claude Code le `.mcp.json` na raiz; `cew skills instalar` copia as skills para `.claude/skills/`.
   Em outros agentes, aponte para `skills/<nn>-*/SKILL.md`.
3. Rode a tarefa **"CEW: menu interativo"** (ou `cew` no terminal). O menu so abre depois do teste
   real do Gemini; sem chave, ele pede a chave e oferece salva-la no `.env`.

## Fluxo

```bash
cew run --projeto meu-jogo --alvo "/caminho/do/jogo"     # retomavel: rode de novo para continuar
cew run --projeto meu-jogo --alvo "/caminho/do/jogo" --dry-run
cew status --projeto meu-jogo
cew check --projeto meu-jogo
```

| Etapa | O que faz | Criterio para avancar | Fase Craft Anything |
|---|---|---|---|
| 1 ambiente | ferramentas + `doctor` + Gemini -> `reports/ambiente.json` | nada obrigatorio faltando, Gemini ok | Estudar |
| 2 alvo | escolhe arquivo ou pasta | alvo acessivel | Estudar |
| 3 inventario | abre conteineres, SHA-256, assinatura, entropia, ordem de bytes, formato | `inventario.json` valido | Estudar |
| 4 engenharia | Craft Anything `triage` + Ghidra headless -> `analise/`, hipoteses, especificacoes | evidencia para cada formato a converter | Estudar |
| 5 conversao | `plano_conversao.json`, tarefas do Gemini, conversores -> `web/asset_manifest.json` | sem itens em erro, testes passando | Construir |
| 6 motor | notas 0-10 por motor -> `recomendacao_motor.json`; voce escolhe | escolha registrada | Construir |
| 7 reconstrucao | gera `app/` (Three.js, Babylon.js, Phaser ou PixiJS) | projeto carregando o manifesto | Construir |
| 8 verificacao | esquemas, determinismo, glTF Validator, texturas, audio, build, Playwright, capturas | `relatorio_verificacao.json` aprovado | Verificar |
| 9 pronto | `npm run dev` / `npm run preview` em `app/` | - | Pronto |

Para comparar com o original, coloque capturas em `projects/<nome>/referencias/<cena>.png`.

## Comandos

| Comando | Descricao |
|---|---|
| `cew` | menu interativo |
| `cew setup [--ssh\|--https] [--com-app] [--dry-run]` | ambiente, Craft Anything e Gemini |
| `cew run --projeto P [--alvo A] [--motor M] [--ate ETAPA] [--dry-run]` | fluxo completo, retomavel |
| `cew etapa <nome> --projeto P` | uma etapa |
| `cew check --projeto P [--instalar-dependencias] [--gemini]` | etapa Verificar |
| `cew status [--projeto P]` / `cew projetos` | estado |
| `cew gemini testar\|modelos` | teste real / modelos disponiveis para a chave |
| `cew identificar <arquivos...>` | identifica pelo registro de formatos |
| `cew conversores` / `cew converter <conversor> <entrada> [-o pasta] [--dry-run]` | conversores |
| `cew sandbox <rascunho.py\|sha.resposta.json> --entrada <amostra>` | roda rascunho do Gemini isolado |
| `cew validar <arquivo.json> [--esquema nome]` | valida um JSON |
| `cew skills instalar` | copia as skills para `.claude/skills/` |

Cada conversor tambem roda sozinho: `python converters/nintendo/tpl_to_png.py --help`.

## O que ja converte

| Origem | Formato | Destino |
|---|---|---|
| Nintendo | Yaz0/SZS, U8 (.arc), SARC | pasta (recursivo) |
| Nintendo | TPL (I4, I8, IA4, IA8, RGB565, RGB5A3, RGBA32, C4, C8, C14X2, CMPR) | PNG |
| Sony | TIM (4/8/16/24 bpp, CLUT) | PNG |
| Sony | VAG (PS-ADPCM, com loop) | WAV -> OGG |
| id Software | PAK; MD2 (frames -> morph targets + animacoes) | pasta; GLB |
| Valve | VPK v1/v2 | pasta |
| PC | DDS (BC1/2/3, RGB/RGBA), TGA, WAV, ZIP/APK/PK3 | PNG, OGG/WAV, pasta |
| Texto | tabelas Shift-JIS/UTF-16/Latin-1 | `dados/dialogos.json` |

O registro (`formats/registry.json`) tem 89 formatos com assinatura, ordem de bytes, destino web e
ferramentas de referencia; os que ainda nao tem conversor ficam `aguardando_conversor` no plano e o
fluxo de delegacao (skill 04) cria o conversor com o Gemini + revisao.

## Estrutura

```
cew/                 pacote do orquestrador (CLI, Gemini, inventario, plano, conversao, motor, verificacao, MCP)
cew/modelos_web/     modelos de projeto web por motor
scripts/             orchestrator.py, setup_craft_anything.py, mcp_server.py, ghidra/ExportarCEW.java
schemas/             JSON Schema 2020-12 de todos os contratos (+ exemplos validos em schemas/exemplos/)
formats/registry.json  registro de formatos por empresa/motor
converters/<empresa>/  um conversor por formato (--help, --dry-run, saida JSON validada)
converters/comum/    leitura binaria defensiva, compressoes, texturas de GPU, audio, glTF, eixos, texto
tests/               pytest (+ tests/js para ajv e glTF Validator) e amostras sinteticas em tests/fixtures/
docs/                DECISOES.md, formatos/, especificacoes/
skills/              seis skills para o agente no VS Code
projects/<nome>/     criado pelo CEW (estrutura do Craft Anything + JSONs do CEW)
```

## Testes

```bash
python -m pytest     # conversores, esquemas, registro, Gemini (transporte falso), fluxo, sandbox, MCP
npm test             # ajv em todos os esquemas/exemplos e glTF Validator nos GLB dos projetos
```

## Seguranca

- A chave do Gemini so vai no cabecalho `x-goog-api-key`; logs (`logs/**.jsonl`), cache e
  relatorios passam por redacao. `.env`, `cache/`, `logs/` e `build/` estao no `.gitignore`.
- Tudo o que vai ao Gemini fica em `logs/gemini/<data>.jsonl` (imagens so como hash) e as respostas
  validas em `cache/gemini/` por hash da entrada.
- Leitura binaria com limites, protecao contra zip slip e bombas de descompressao; arquivo
  corrompido gera erro de formato, nunca trava o fluxo.
- Rascunhos do Gemini rodam em sandbox (sem rede, tempo e memoria limitados) e so entram em
  `converters/` depois de revisados e testados.

Decisoes, diferencas em relacao a especificacao original e o que ainda e hipotese: `docs/DECISOES.md`.
