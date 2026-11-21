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
arquitetura, **escreve os conversores do app que a pessoa quer converter**, revisa todo codigo gerado
e e a unica que grava no repositorio. As skills em `skills/` dizem a ela o que fazer em cada etapa.

**Modelo "o agente cria os conversores".** O CEW nao tenta trazer um conversor pronto para cada formato
do mundo. Ele traz o kit (esqueleto, biblioteca de leitura binaria/texturas/audio/glTF, harness de testes,
sandbox, registro de formatos e verificacao) e o agente da pessoa escreve - ou embrulha uma ferramenta
existente - os conversores do alvo dela, dentro do projeto. Os conversores especificos que ja existiam
viraram receitas opcionais em `cookbook/`.

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
| 5 conversao | `plano_conversao.json` com cobertura por formato; o agente cria os conversores que faltam (skill 04) -> `web/asset_manifest.json` | sem erros; formato de prioridade alta sem conversor so com decisao; conversores do projeto aprovados no harness | Construir |
| 6 motor | notas 0-10 por motor -> `recomendacao_motor.json`; voce escolhe | escolha registrada | Construir |
| 7 reconstrucao | gera `app/` (Three.js, Babylon.js, Phaser ou PixiJS) e `marcos.json`; o agente reconstroi a logica marco a marco (skill 07) | projeto carregando o manifesto | Construir |
| 8 verificacao | esquemas, determinismo, glTF Validator, texturas, audio, build, Playwright, capturas, **testes de marco** e **cobertura de conteudo** | `relatorio_verificacao.json` aprovado (marcos obrigatorios inclusive) | Verificar |
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
| `cew novo-conversor <formato> --projeto P [--tipo python\|comando] [--destino png]` | esqueleto de conversor no projeto |
| `cew conversor-testar <ref> --projeto P [--entrada A]` | harness: executa, determinismo, robustez, dry-run, ajuda, tempo/memoria |
| `cew formato-registrar <formato> --projeto P [--extensao] [--assinatura] [--conversor] [--decisao]` | registro do projeto (`formatos.json`) |
| `cew conversor-copiar <cookbook/...> --projeto P` | traz uma receita do cookbook para adaptar |
| `cew log-conversor <formato> <passo> --projeto P` | registra pesquisa/amostragem/conferencia em `log_conversores.jsonl` |
| `cew marcos iniciar\|status --projeto P [--modelo jogo\|app]` | marcos de utilizacao/jogabilidade |

Cada conversor tambem roda sozinho: `python cookbook/nintendo/tpl_to_png.py --help`.

## Conversores: tres fontes

A ordem de busca fica em `config/cew.json` (`fontes_conversores`, padrao `projeto -> cookbook -> generico`):

| Fonte | Onde | O que e |
|---|---|---|
| projeto | `projects/<nome>/conversores/` | escritos pelo agente para o alvo da pessoa: modulo Python ou comando externo declarado em JSON (embrulha vgmstream-cli, ffmpeg, um binario proprio...). Rodam em subprocesso com tempo e memoria limitados |
| cookbook | `cookbook/` | receitas testadas e opcionais: Yaz0, U8, SARC, TPL (GX), TIM, VAG, PAK, MD2->GLB, VPK, DDS, TGA. Tire `cookbook` da lista para o agente escrever tudo no projeto |
| generico | `converters/` | o que quase todo alvo precisa: arquivos que a web ja le, ZIP/APK/PK3, WAV->OGG, tabelas de texto->JSON |

O registro global (`formats/registry.json`, 89 formatos) continua completo, porque identificar e barato e
ajuda todo mundo; o registro do projeto (`projects/<nome>/formatos.json`) completa ou substitui entradas
(ex.: o agente registra a assinatura do `.xnb` e o conversor que escreveu). Formato sem conversor aparece no
plano como `falta_conversor`, com prioridade pelo impacto; a pessoa pode decidir `ignorar`, `substituir`
ou `bloqueado`.

## Estrutura

```
cew/                 pacote do orquestrador (CLI, Gemini, inventario, plano, conversao, motor, verificacao, MCP)
cew/modelos_web/     modelos de projeto web por motor
scripts/             orchestrator.py, setup_craft_anything.py, mcp_server.py, ghidra/ExportarCEW.java
schemas/             JSON Schema 2020-12 de todos os contratos (+ exemplos validos em schemas/exemplos/)
formats/registry.json  registro de formatos por empresa/motor
converters/comum/    biblioteca para o agente: leitura binaria defensiva, compressoes, texturas de GPU, audio, glTF, eixos, texto
converters/generico/ conversores genericos (fonte "generico")
cookbook/<familia>/  receitas opcionais e testadas (fonte "cookbook")
tests/               pytest (+ tests/js para ajv e glTF Validator) e amostras sinteticas em tests/fixtures/
docs/                DECISOES.md, formatos/, especificacoes/
skills/              sete skills para o agente no VS Code
projects/<nome>/     criado pelo CEW (estrutura do Craft Anything + JSONs do CEW + conversores/ do agente, formatos.json, marcos.json)
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
