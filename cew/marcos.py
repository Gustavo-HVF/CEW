"""Marcos de utilizacao/jogabilidade (marcos.json), editaveis pelo agente (skill 07).

Cada marco tem criterio, um teste Playwright em app/tests/marcos/<id>.spec.js e "obrigatorio".
O primeiro marco ("abre") ja vem com teste real; os outros vem como test.fixme com um exemplo de
como injetar entradas e conferir window.__CEW_ESTADO. Teste pendente (fixme/skip) = marco nao aprovado.
"""

from __future__ import annotations

from pathlib import Path

from . import GERADO_POR, SCHEMA_VERSION
from .esquemas import gravar_json, ler_json
from .logs import agora_iso
from .projeto import Projeto

MODELOS = {
    "jogo": [
        ("abre", "Abre com assets reais", "A primeira tela abre, carrega assets do manifesto e nao ha erros no console.", True),
        ("entrada", "Entrada move algo", "Teclado/mouse/toque muda algo observavel em window.__CEW_ESTADO (ex.: jogador.x).", False),
        ("colisao", "Colisao e fisica basica", "O personagem para em paredes/chao e cai com gravidade (estado confirma).", False),
        ("laco_central", "Laco central do jogo", "A acao principal do jogo funciona (ex.: cavar/construir/atirar) e muda o estado esperado.", False),
        ("progressao", "Conteudo e progressao minimos", "Ha objetivo, pontuacao ou avanco de fase registrados no estado.", False),
        ("audio_interface_salvamento", "Audio, interface e salvamento", "Musica com loop toca, HUD aparece e o progresso sobrevive a recarregar a pagina.", False),
        ("desempenho", "Desempenho e celular", "Mantem o FPS minimo (estado.fps) em desktop e em viewport de celular.", False),
    ],
    "app": [
        ("abre", "Abre com assets reais", "A tela inicial abre, carrega assets do manifesto e nao ha erros no console.", True),
        ("navegacao", "Navegacao entre telas", "Clicar nos controles troca window.__CEW_ESTADO.tela para as telas esperadas.", False),
        ("acao_principal", "Acao principal", "A funcao central do app funciona e o resultado aparece no estado.", False),
        ("persistencia", "Dados persistem", "Dados criados continuam la depois de recarregar a pagina.", False),
        ("desempenho", "Desempenho", "Interacoes respondem em menos de 100 ms no desktop e no celular.", False),
    ],
}

TESTE_ABRE = """import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir } from '../cew_helpers.js';

// Marco "{id}": {criterio}
test('marco {id}', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  const e = await estado(page);
  concluir(obs, 'marco-{id}');
  expect(obs.erros, obs.erros.join('\\n')).toEqual([]);
  expect(e.assets_carregados).toBe(true);
  expect(obs.assets.size, 'nenhum asset do manifesto foi requisitado').toBeGreaterThan(0);
});
"""

TESTE_PENDENTE = """import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir } from '../cew_helpers.js';

// Marco "{id}": {criterio}
// PENDENTE: troque test.fixme por test quando o jogo/app implementar este marco.
// Exemplo (adapte ao que o app expoe em window.__CEW_ESTADO):
//   const antes = await estado(page);
//   await page.keyboard.down('ArrowRight'); await page.waitForTimeout(400); await page.keyboard.up('ArrowRight');
//   const depois = await estado(page);
//   expect(depois.jogador.x).toBeGreaterThan(antes.jogador.x);
test.fixme('marco {id}', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  const e = await estado(page);
  concluir(obs, 'marco-{id}');
  expect(obs.erros, obs.erros.join('\\n')).toEqual([]);
  expect(e).toBeTruthy();
});
"""


def caminho(projeto: Projeto) -> Path:
    return projeto.pasta / "marcos.json"


def ler(projeto: Projeto) -> dict | None:
    return ler_json(caminho(projeto), "marcos") if caminho(projeto).is_file() else None


def iniciar(projeto: Projeto, modelo: str = "jogo", sobrescrever: bool = False) -> dict:
    if modelo not in MODELOS:
        raise ValueError(f"modelo de marcos: {', '.join(MODELOS)}")
    doc = ler(projeto)
    if doc is None or sobrescrever:
        doc = {"schema_version": SCHEMA_VERSION, "gerado_por": GERADO_POR, "projeto": projeto.nome, "modelo": modelo,
               "marcos": [{"id": i, "titulo": t, "criterio": c, "teste": f"tests/marcos/{i}.spec.js", "obrigatorio": o, "estado": "pendente"}
                          for i, t, c, o in MODELOS[modelo]]}
        gravar_json(caminho(projeto), doc, "marcos")
    gerar_testes(projeto, doc)
    return doc


def gerar_testes(projeto: Projeto, doc: dict) -> list[str]:
    """Cria o teste de cada marco que ainda nao tem arquivo (nunca sobrescreve o que o agente escreveu)."""
    criados = []
    app = projeto.pasta / "app"
    for i, m in enumerate(doc["marcos"]):
        arq = app / m["teste"]
        if arq.exists():
            continue
        arq.parent.mkdir(parents=True, exist_ok=True)
        modelo = TESTE_ABRE if i == 0 else TESTE_PENDENTE
        arq.write_text(modelo.replace("{id}", m["id"]).replace("{criterio}", m["criterio"]), encoding="utf-8")
        criados.append(m["teste"])
    return criados


def atualizar(projeto: Projeto, resultados: dict[str, dict]) -> tuple[dict | None, str | None]:
    """resultados: {"tests/marcos/x.spec.js": {"aprovado": bool, "detalhes": str}}. Devolve (doc, marco_atingido)."""
    doc = ler(projeto)
    if doc is None:
        return None, None
    atingido = None
    consecutivo = True
    for m in doc["marcos"]:
        r = resultados.get(m["teste"])
        if r is None:
            m["estado"], m["detalhes"] = "pendente", "teste nao encontrado ou nao executado"
        else:
            m["estado"] = "aprovado" if r["aprovado"] else ("pendente" if r.get("pendente") else "reprovado")
            m["detalhes"] = r["detalhes"][:500]
            m["verificado_em"] = agora_iso()
        if consecutivo and m["estado"] == "aprovado":
            atingido = m["id"]
        else:
            consecutivo = False
    gravar_json(caminho(projeto), doc, "marcos")
    return doc, atingido
