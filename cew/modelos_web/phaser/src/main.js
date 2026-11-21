// Cena Phaser gerada pelo CEW: carrega texturas e audio do asset_manifest.json.
import * as Phaser from 'phaser';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';

async function iniciar() {
  const m = await carregarManifesto();
  const audio = new Audio();
  const texturas = m.doTipo('textura');
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
      painelAudio(m, audio);
      pronto(`${m.bruto.assets.length} assets (${texturas.length} texturas)`);
    }
  }
  new Phaser.Game({ type: Phaser.AUTO, parent: 'cena', width: 1000, height: 640, backgroundColor: '#202428', pixelArt: true, scene: [Principal] });
}

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
