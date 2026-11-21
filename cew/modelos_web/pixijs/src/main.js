// Cena PixiJS gerada pelo CEW: carrega texturas e audio do asset_manifest.json.
import { Application, Assets, Sprite, TextureStyle } from 'pixi.js';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';

async function iniciar() {
  const m = await carregarManifesto();
  const audio = new Audio();
  TextureStyle.defaultOptions.scaleMode = 'nearest';
  const app = new Application();
  await app.init({ resizeTo: window, background: '#202428' });
  document.getElementById('cena').appendChild(app.canvas);
  const texturas = m.doTipo('textura');
  for (const [i, a] of texturas.entries()) {
    const tex = await Assets.load(m.url(a));
    const s = new Sprite(tex);
    s.scale.set(64 / Math.max(tex.width, tex.height));
    s.position.set(40 + (i % 10) * 90, 100 + Math.floor(i / 10) * 90);
    app.stage.addChild(s);
  }
  painelAudio(m, audio);
  pronto(`${m.bruto.assets.length} assets (${texturas.length} texturas)`);
}

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
