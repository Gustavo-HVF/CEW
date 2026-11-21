// Ajudantes dos testes de navegador do CEW.
// - observar(page): junta erros do console e os assets do manifesto que o app requisitou;
// - estado(page): le window.__CEW_ESTADO (contrato: o app expoe o que o teste precisa observar);
// - concluir(page, obs, nome): grava ../checks/assets_carregados/<nome>.json (cobertura de conteudo).
import fs from 'node:fs';

export function observar(page) {
  const obs = { erros: [], assets: new Set() };
  page.on('console', (m) => { if (m.type() === 'error') obs.erros.push(m.text()); });
  page.on('pageerror', (e) => obs.erros.push(String(e)));
  page.on('request', (r) => {
    const u = new URL(r.url());
    const caminho = decodeURIComponent(u.pathname).replace(/^\/+/, '');
    if (caminho.startsWith('assets/') || caminho.startsWith('dados/')) obs.assets.add(caminho);
  });
  return obs;
}

export async function abrir(page, url = '/') {
  await page.goto(url);
  await page.waitForFunction(() => window.__CEW_PRONTO === true, null, { timeout: 30_000 });
}

export async function estado(page) {
  return page.evaluate(() => JSON.parse(JSON.stringify(window.__CEW_ESTADO ?? {})));
}

export function concluir(obs, nome) {
  fs.mkdirSync('../checks/assets_carregados', { recursive: true });
  fs.writeFileSync(`../checks/assets_carregados/${nome}.json`, JSON.stringify({ nome, assets: [...obs.assets].sort() }, null, 2));
}

// Segura uma tecla por ms (o canvas recebe foco antes, para o jogo ouvir o teclado).
export async function segurarTecla(page, tecla, ms) {
  await page.locator('canvas').first().click({ position: { x: 5, y: 5 } }).catch(() => {});
  await page.keyboard.down(tecla);
  await page.waitForTimeout(ms);
  await page.keyboard.up(tecla);
}

// Espera ate predicado(estado) ser verdadeiro (o predicado roda no navegador; passe como string ou funcao).
export async function esperarEstado(page, predicado, timeout = 10_000) {
  await page.waitForFunction((src) => {
    const fn = new Function('e', `return (${src})(e)`);
    return fn(window.__CEW_ESTADO || {});
  }, predicado.toString(), { timeout });
  return estado(page);
}

// fps medio observado durante ms (usa window.__CEW_ESTADO.quadro).
export async function medirFps(page, ms = 2000) {
  const a = (await estado(page)).quadro || 0;
  await page.waitForTimeout(ms);
  const b = (await estado(page)).quadro || 0;
  return ((b - a) * 1000) / ms;
}

export const VIEWPORT_CELULAR = { width: 390, height: 844 };
