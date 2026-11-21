import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir, segurarTecla, esperarEstado } from '../cew_helpers.js';

// Marco colisao: o jogador cai ate o chao (y = 112 - 14) e para na pilastra (x <= 64 - 10).
test('marco colisao', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  const noChao = await esperarEstado(page, (e) => e.jogador && e.jogador.no_chao);
  expect(noChao.jogador.posicao[1]).toBeCloseTo(98, 0);
  await segurarTecla(page, 'ArrowRight', 1500);
  const e = await estado(page);
  concluir(obs, 'marco-colisao');
  expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  expect(e.jogador.posicao[0]).toBeLessThanOrEqual(54.01);
  expect(e.jogador.posicao[0]).toBeGreaterThan(50);
});
