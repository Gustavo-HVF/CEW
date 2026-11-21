import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir } from './cew_helpers.js';

// Sessao curta de ponta a ponta: joga por CEW_SESSAO_S segundos (padrao 30) apertando as acoes mais
// comuns e exige: nenhum erro no console, o jogo nao travou (quadros continuam subindo) e, se o jogo
// expoe o jogador, que ele se moveu em algum momento.
const SEGUNDOS = Number(process.env.CEW_SESSAO_S || 30);
const TECLAS = ['ArrowRight', 'ArrowLeft', 'Space', 'ArrowUp', 'KeyX'];

test('sessao curta de ponta a ponta', async ({ page }) => {
  test.setTimeout((SEGUNDOS + 60) * 1000);
  const obs = observar(page);
  await abrir(page, '/');
  await page.locator('canvas').first().click({ position: { x: 5, y: 5 } }).catch(() => {});
  const inicio = await estado(page);
  const posicoes = new Set();
  let ultimoQuadro = inicio.quadro || 0;
  let travou = 0;
  const fim = Date.now() + SEGUNDOS * 1000;
  let i = 0;
  while (Date.now() < fim) {
    const tecla = TECLAS[i++ % TECLAS.length];
    await page.keyboard.down(tecla);
    await page.waitForTimeout(250 + (i % 3) * 150);
    await page.keyboard.up(tecla);
    const e = await estado(page);
    if (e.jogador) posicoes.add(JSON.stringify(e.jogador.posicao ?? [e.jogador.x, e.jogador.y]));
    if ((e.quadro || 0) <= ultimoQuadro) travou++;
    ultimoQuadro = e.quadro || 0;
  }
  concluir(obs, 'sessao');
  expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  expect(travou, 'quadros pararam de subir (jogo travado?)').toBeLessThan(3);
  expect(ultimoQuadro - (inicio.quadro || 0)).toBeGreaterThan(SEGUNDOS * 5);
  if (inicio.jogador) expect(posicoes.size, 'o jogador nunca se moveu').toBeGreaterThan(1);
});
