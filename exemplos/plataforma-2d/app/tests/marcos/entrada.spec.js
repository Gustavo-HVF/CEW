import { test, expect } from '@playwright/test';
import { observar, abrir, estado, concluir, segurarTecla, esperarEstado } from '../cew_helpers.js';

// Marco entrada: segurar a seta para a direita move o jogador.
test('marco entrada', async ({ page }) => {
  const obs = observar(page);
  await abrir(page, '/');
  const antes = await esperarEstado(page, (e) => e.jogador && e.jogador.no_chao);
  await segurarTecla(page, 'ArrowRight', 300);
  const depois = await estado(page);
  concluir(obs, 'marco-entrada');
  expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  expect(depois.jogador.posicao[0]).toBeGreaterThan(antes.jogador.posicao[0] + 5);
});
