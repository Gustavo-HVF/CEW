import { test, expect } from '@playwright/test';
import fs from 'node:fs';

// Abre cada cena, exige zero erros no console e salva a captura em ../checks/capturas/
// (a etapa Verificar do CEW compara com referencias/<cena>.png, se a pessoa forneceu).
const cenas = JSON.parse(fs.readFileSync(new URL('./cenas.json', import.meta.url), 'utf-8'));

for (const cena of cenas) {
  test(`cena ${cena.id}`, async ({ page }) => {
    const erros = [];
    page.on('console', (m) => { if (m.type() === 'error') erros.push(m.text()); });
    page.on('pageerror', (e) => erros.push(String(e)));
    await page.goto(cena.url);
    await page.waitForFunction(() => window.__CEW_PRONTO === true, null, { timeout: 30_000 });
    await page.waitForTimeout(500);
    fs.mkdirSync('../checks/capturas', { recursive: true });
    await page.screenshot({ path: `../checks/capturas/${cena.id}.png` });
    expect(erros, erros.join('\n')).toEqual([]);
  });
}
