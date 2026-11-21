import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir, segurarTecla, esperarEstado } from '../cew_helpers.js';

// Marco progressao: sem inimigos vivos a fase e concluida e o recorde e salvo (sobrevive a recarregar).
test('marco progressao', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  await esperarEstado(page, (e) => e.jogador && e.jogador.no_chao);
  await page.evaluate(() => window.__CEW_TESTE.posicionar(84, 70));
  await page.keyboard.down('ArrowRight');
  await esperarEstado(page, (x) => x.tela === 'fase_concluida', 8000);
  await page.keyboard.up('ArrowRight');
  await page.reload();
  await abrir(page, '/');
  const e = await estado(page);
  concluir(obs, 'marco-progressao');
  expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  expect(e.recorde).toBe(100);
});
