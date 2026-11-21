import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir, segurarTecla, esperarEstado } from '../cew_helpers.js';

// Marco laco central: cair sobre o slime o derrota e soma pontos (pulo pela pilastra + pisao).
test('marco laco_central', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  await esperarEstado(page, (e) => e.jogador && e.jogador.no_chao && e.inimigos_vivos === 1);
  await page.evaluate(() => window.__CEW_TESTE.posicionar(84, 70)); // depois da pilastra, acima da patrulha
  await page.keyboard.down('ArrowRight');
  const e = await esperarEstado(page, (x) => x.inimigos_vivos === 0, 8000);
  await page.keyboard.up('ArrowRight');
  concluir(obs, 'marco-laco_central');
  expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  expect(e.pontuacao).toBe(100);
  expect(e.vida).toBeGreaterThan(0);
});
