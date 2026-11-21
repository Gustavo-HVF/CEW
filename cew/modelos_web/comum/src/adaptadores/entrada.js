// Entrada por ACOES (pular, andar_direita...), nao por tecla: teclado, gamepad e toque alimentam as
// mesmas acoes. O mapa vem de web/dados/controles.json (schemas/dados/controles.schema.json) quando
// existir no manifesto; senao, do padrao abaixo. O estado das acoes fica em window.__CEW_ESTADO.acoes.
import { estado } from '../manifesto.js';

const PADRAO = {
  esquerda: { teclas: ['ArrowLeft', 'KeyA'], gamepad: { botoes: [14], eixo: [0, -1] } },
  direita: { teclas: ['ArrowRight', 'KeyD'], gamepad: { botoes: [15], eixo: [0, 1] } },
  cima: { teclas: ['ArrowUp', 'KeyW'], gamepad: { botoes: [12], eixo: [1, -1] } },
  baixo: { teclas: ['ArrowDown', 'KeyS'], gamepad: { botoes: [13], eixo: [1, 1] } },
  pular: { teclas: ['Space', 'KeyZ'], gamepad: { botoes: [0] } },
  acao: { teclas: ['KeyX', 'Enter'], gamepad: { botoes: [2] } },
  pausa: { teclas: ['Escape', 'KeyP'], gamepad: { botoes: [9] } },
};

export async function carregarControles(manifesto) {
  const a = manifesto.bruto.assets.find((x) => x.tipo === 'dados' && /(^|\/)controles[-.]/.test(x.caminho_web));
  if (!a) return { acoes: PADRAO };
  const doc = await (await fetch(manifesto.url(a))).json();
  return { acoes: doc.acoes };
}

export class Entrada {
  constructor(mapa = { acoes: PADRAO }, alvo = window) {
    this.mapa = mapa.acoes;
    this.teclas = new Set();
    this.toque = new Set();
    this.anterior = {};
    this.atual = {};
    const bloquear = new Set(Object.values(this.mapa).flatMap((m) => m.teclas || []));
    alvo.addEventListener('keydown', (ev) => { this.teclas.add(ev.code); if (bloquear.has(ev.code)) ev.preventDefault(); });
    alvo.addEventListener('keyup', (ev) => this.teclas.delete(ev.code));
    alvo.addEventListener('blur', () => this.teclas.clear());
  }

  // Botoes na tela para celular: {acao: elemento}; o jogo decide o visual.
  ligarToque(botoes) {
    for (const [acao, el] of Object.entries(botoes)) {
      el.addEventListener('pointerdown', (e) => { e.preventDefault(); this.toque.add(acao); });
      for (const ev of ['pointerup', 'pointercancel', 'pointerleave']) el.addEventListener(ev, () => this.toque.delete(acao));
    }
  }

  // Chame uma vez por passo de logica.
  atualizar() {
    const pads = (navigator.getGamepads?.() || []).filter(Boolean);
    this.anterior = this.atual;
    this.atual = {};
    for (const [acao, m] of Object.entries(this.mapa)) {
      let ativo = (m.teclas || []).some((t) => this.teclas.has(t)) || this.toque.has(acao);
      for (const p of pads) {
        if ((m.gamepad?.botoes || []).some((b) => p.buttons[b]?.pressed)) ativo = true;
        const eixo = m.gamepad?.eixo;
        if (eixo && Math.sign(p.axes[eixo[0]] || 0) === eixo[1] && Math.abs(p.axes[eixo[0]]) > 0.5) ativo = true;
      }
      this.atual[acao] = ativo;
    }
    estado({ acoes: this.atual });
    return this.atual;
  }

  segurando(acao) { return !!this.atual[acao]; }
  apertou(acao) { return !!this.atual[acao] && !this.anterior[acao]; }
}
