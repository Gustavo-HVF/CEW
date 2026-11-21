// Jogo de demonstracao: camada do Phaser. Regras em src/nucleo/jogo.js (sem motor).
import * as Phaser from 'phaser';
import { carregarManifesto, Audio, pronto, estado } from './manifesto.js';
import { carregarCenas, registrarCena } from './cena.js';
import { criarLacoFixo } from './nucleo/laco.js';
import { criarJogo } from './nucleo/jogo.js';
import { Entrada, carregarControles } from './adaptadores/entrada.js';
import { salvar, carregar } from './adaptadores/salvamento.js';

const ESCALA = 4;

async function iniciar() {
  const m = await carregarManifesto();
  const cena = (await carregarCenas(m)).find((c) => c.dimensao === '2d');
  const cfgAsset = m.bruto.assets.find((a) => /(^|\/)configuracoes[-.]/.test(a.caminho_web));
  const cfg = (await (await fetch(m.url(cfgAsset))).json()).valores;
  const entrada = new Entrada(await carregarControles(m));
  new Audio().desbloquear();
  const jogo = criarJogo(cena, cfg);
  window.__CEW_TESTE = { posicionar: (x, y) => jogo.posicionar(x, y) };
  const recorde = carregar('recorde', 1, (d) => Number.isFinite(d)) || 0;
  let pausado = false;

  class Fase extends Phaser.Scene {
    constructor() { super('fase'); }
    preload() { for (const a of m.doTipo('textura')) this.load.image(a.id, m.url(a)); }
    create() {
      this.cameras.main.setZoom(ESCALA).centerOn(jogo.estado.largura / 2, jogo.estado.altura / 2);
      const t = cena.tiles[0];
      t.dados.forEach((g, i) => { if (g) this.add.rectangle((i % t.largura) * 16, Math.floor(i / t.largura) * 16, 16, 16, 0x5d4037).setOrigin(0, 0); });
      let inst = 0;
      for (const e of cena.entidades) {
        if (e.categoria === 'estrutura') this.add.rectangle(e.posicao[0], e.posicao[1], e.tamanho[0], e.tamanho[1], 0x9e9e9e).setOrigin(0, 0);
        else if (e.categoria === 'vegetacao' && e.asset_id) this.add.image(e.posicao[0], e.posicao[1], e.asset_id).setOrigin(0, 1).setDisplaySize(e.tamanho[0], e.tamanho[1]);
        else if (e.categoria === 'vegetacao') this.add.rectangle(e.posicao[0], e.posicao[1], (e.tamanho || [8, 8])[0], (e.tamanho || [8, 8])[1], 0x2e7d32).setOrigin(0, 0).setAngle(e.guinada_graus || 0);
        inst++;
      }
      registrarCena(cena, inst, 0);
      this.inimigos = jogo.estado.inimigos.map((i) => this.add.rectangle(i.x, i.y, i.w, i.h, 0xe53935).setOrigin(0, 0));
      this.jogador = this.add.rectangle(0, 0, 10, 14, 0x1e88e5).setOrigin(0, 0);
      this.hud = document.getElementById('status'); // HUD no DOM: legivel em qualquer zoom da camera
      this.laco = criarLacoFixo(cfg.passo_logica_hz, (dt) => jogo.passo(dt, entrada.atual));
      estado({ ...jogo.observavel(), pausado, recorde });
      pronto('demo: setas/A-D para andar, espaco para pular, P pausa'); // so depois da cena existir
    }
    update(_t, delta) {
      const acoes = entrada.atualizar();
      if (entrada.apertou('pausa')) pausado = !pausado;
      if (!pausado) this.laco.passo(delta);
      const j = jogo.estado.jogador;
      this.jogador.setPosition(j.x, j.y).setAlpha(j.inv > 0 ? 0.5 : 1);
      jogo.estado.inimigos.forEach((i, k) => this.inimigos[k].setPosition(i.x, i.y).setVisible(i.vivo));
      const obs = jogo.observavel();
      if (obs.tela === 'fase_concluida' && obs.pontuacao > recorde) salvar('recorde', obs.pontuacao);
      this.hud.textContent = `vida ${obs.vida}  pontos ${obs.pontuacao}${pausado ? '  PAUSA' : ''}${obs.tela === 'fase_concluida' ? '  FASE CONCLUIDA' : ''}`;
      estado({ ...obs, pausado, recorde, acoes });
    }
  }
  new Phaser.Game({ type: Phaser.AUTO, parent: 'cena', width: 640, height: 512, backgroundColor: '#202428', pixelArt: true, scene: [Fase] });
}

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
