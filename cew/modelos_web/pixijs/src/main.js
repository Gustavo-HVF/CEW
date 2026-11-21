// Cena PixiJS gerada pelo CEW: carrega texturas e audio do asset_manifest.json.
import { Application, Assets, Container, Graphics, Sprite, TextureStyle } from 'pixi.js';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';
import { carregarCenas, registrarCena, origem2d, CORES } from './cena.js';

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
  for (const c of await carregarCenas(m)) {
    const raiz = new Container();
    raiz.position.set(40, 360);
    app.stage.addChild(raiz);
    let inst = 0, marcadores = 0;
    for (const t of c.tiles || []) {
      const g = new Graphics();
      t.dados.forEach((gid, i) => { if (gid) g.rect((i % t.largura) * t.tamanho_tile_px[0], Math.floor(i / t.largura) * t.tamanho_tile_px[1], t.tamanho_tile_px[0], t.tamanho_tile_px[1]); });
      raiz.addChild(g.fill(0x5d4037));
    }
    for (const e of c.entidades) {
      const [x, y] = c.dimensao === '2d' ? e.posicao : [e.posicao_m[0] * 20, e.posicao_m[2] * 20];
      const a = e.asset_id ? m.get(e.asset_id) : null;
      const [w, h] = e.tamanho && e.tamanho[0] ? e.tamanho : [10, 10];
      const [ox, oy] = origem2d(e.ancora);
      let obj;
      if (a && a.tipo === 'textura') {
        obj = new Sprite(await Assets.load(m.url(a)));
        obj.anchor.set(ox, oy);
        if (e.tamanho && e.tamanho[0] && e.tamanho[1]) { obj.width = w; obj.height = h; } // tamanho do elemento no mapa
      } else {
        obj = new Graphics().rect(-ox * w, -oy * h, w, h).fill(CORES[e.categoria] ?? 0xffffff);
        marcadores++;
      }
      obj.position.set(x, y);
      obj.angle = e.guinada_graus || 0;
      obj.label = e.id;
      raiz.addChild(obj);
      inst++;
    }
    registrarCena(c, inst, marcadores);
  }
  painelAudio(m, audio);
  pronto(`${m.bruto.assets.length} assets (${texturas.length} texturas)`);
}

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
