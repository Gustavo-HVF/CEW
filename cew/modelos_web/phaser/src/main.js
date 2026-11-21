// Cena Phaser gerada pelo CEW: carrega texturas e audio do asset_manifest.json.
import * as Phaser from 'phaser';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';
import { carregarCenas, registrarCena, origem2d, CORES } from './cena.js';

async function iniciar() {
  const m = await carregarManifesto();
  const audio = new Audio();
  const texturas = m.doTipo('textura');
  const cenas = await carregarCenas(m);
  class Principal extends Phaser.Scene {
    constructor() { super('principal'); }
    preload() {
      for (const a of texturas) this.load.image(a.id, m.url(a));
    }
    create() {
      texturas.forEach((a, i) => {
        const img = this.add.image(80 + (i % 10) * 90, 120 + Math.floor(i / 10) * 90, a.id);
        img.setScale(64 / Math.max(img.width, img.height));
      });
      // cenas 2D: cada elemento no pixel gravado, com a ancora e a rotacao (graus, sentido horario)
      for (const c of cenas) {
        const raiz = this.add.container(40, 360);
        let inst = 0, marcadores = 0;
        for (const t of c.tiles || []) {
          t.dados.forEach((gid, i) => {
            if (gid) raiz.add(this.add.rectangle((i % t.largura) * t.tamanho_tile_px[0], Math.floor(i / t.largura) * t.tamanho_tile_px[1], t.tamanho_tile_px[0], t.tamanho_tile_px[1], 0x5d4037).setOrigin(0, 0));
          });
        }
        for (const e of c.entidades) {
          const [x, y] = c.dimensao === '2d' ? e.posicao : [e.posicao_m[0] * 20, e.posicao_m[2] * 20];
          const a = e.asset_id ? m.get(e.asset_id) : null;
          let obj;
          if (a && a.tipo === 'textura') {
            obj = this.add.image(x, y, a.id);
            if (e.tamanho && e.tamanho[0] && e.tamanho[1]) obj.setDisplaySize(e.tamanho[0], e.tamanho[1]); // tamanho do elemento no mapa
          } else {
            const [w, h] = e.tamanho && e.tamanho[0] ? e.tamanho : [10, 10];
            obj = this.add.rectangle(x, y, w, h, CORES[e.categoria] ?? 0xffffff);
            marcadores++;
          }
          const [ox, oy] = origem2d(e.ancora);
          obj.setOrigin(ox, oy).setAngle(e.guinada_graus || 0).setName(e.id);
          obj.setData('cew', { categoria: e.categoria, tipo_original: e.tipo_original, propriedades: e.propriedades || {} });
          raiz.add(obj);
          inst++;
        }
        registrarCena(c, inst, marcadores);
      }
      painelAudio(m, audio);
      pronto(`${m.bruto.assets.length} assets (${texturas.length} texturas)`);
    }
  }
  new Phaser.Game({ type: Phaser.AUTO, parent: 'cena', width: 1000, height: 640, backgroundColor: '#202428', pixelArt: true, scene: [Principal] });
}

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
