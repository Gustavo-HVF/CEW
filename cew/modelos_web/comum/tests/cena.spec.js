import { test, expect } from '@playwright/test';
import fs from 'node:fs';
import { observar, abrir, concluir } from './cew_helpers.js';

// Abre cada cena, exige zero erros no console e salva a captura em ../checks/capturas/
// (a etapa Verificar do CEW compara com referencias/<cena>.png, se a pessoa forneceu).
const cenas = JSON.parse(fs.readFileSync(new URL('./cenas.json', import.meta.url), 'utf-8'));

for (const cena of cenas) {
  test(`cena ${cena.id}`, async ({ page }) => {
    const obs = observar(page);
    await abrir(page, cena.url);
    await page.waitForTimeout(500);
    fs.mkdirSync('../checks/capturas', { recursive: true });
    await page.screenshot({ path: `../checks/capturas/${cena.id}.png` });
    concluir(obs, `cena-${cena.id}`);
    expect(obs.erros, obs.erros.join('\n')).toEqual([]);
  });
}
