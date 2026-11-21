// Regras do jogo de demonstracao (sem dependencia do motor). Constantes de web/dados/configuracoes.json;
// mapa e elementos de web/dados/cenas/floresta (tiles solidos, estrutura = caixa solida, inimigo, spawn).
import { posicaoInicial } from './comportamentos.js';

const sobrepoe = (a, b) => a.x < b.x + b.w && a.x + a.w > b.x && a.y < b.y + b.h && a.y + a.h > b.y;

export function criarJogo(cena, cfg) {
  const t = cena.tiles[0];
  const [tw, th] = t.tamanho_tile_px;
  const largura = t.largura * tw, altura = t.altura * th;
  const caixas = cena.entidades.filter((e) => e.categoria === 'estrutura' && e.tamanho).map((e) => ({ x: e.posicao[0], y: e.posicao[1], w: e.tamanho[0], h: e.tamanho[1] }));
  const [sx, sy] = posicaoInicial(cena) || [16, 16];
  const j = { x: sx - 5, y: sy - 14, w: 10, h: 14, vx: 0, vy: 0, noChao: false, inv: 0 };
  const inimigos = cena.entidades.filter((e) => e.categoria === 'inimigo').map((e) => ({
    id: e.id, x0: e.posicao[0] - 6, x: e.posicao[0] - 6, y: e.posicao[1] - 10, w: 12, h: 10, vy: 0, dir: 1,
    patrulha: Number((e.propriedades || {}).patrulha_px || 32), vivo: true,
  }));
  const s = { tela: 'jogando', pontuacao: 0, vida: cfg.vida_inicial, inimigos, jogador: j, largura, altura };

  function solidosPerto(c) {
    const r = [...caixas];
    const x0 = Math.floor(c.x / tw) - 1, x1 = Math.floor((c.x + c.w) / tw) + 1;
    const y0 = Math.floor(c.y / th) - 1, y1 = Math.floor((c.y + c.h) / th) + 1;
    for (let cy = y0; cy <= y1; cy++) for (let cx = x0; cx <= x1; cx++) {
      if (cx < 0 || cx >= t.largura) r.push({ x: cx * tw, y: cy * th, w: tw, h: th }); // paredes nas bordas
      else if (cy >= 0 && cy < t.altura && t.dados[cy * t.largura + cx] !== 0) r.push({ x: cx * tw, y: cy * th, w: tw, h: th });
    }
    return r;
  }

  function mover(c, dx, dy) {
    let noChao = false;
    c.x += dx;
    for (const b of solidosPerto(c)) if (sobrepoe(c, b)) c.x = dx > 0 ? b.x - c.w : b.x + b.w;
    c.y += dy;
    for (const b of solidosPerto(c)) if (sobrepoe(c, b)) {
      if (dy > 0) { c.y = b.y - c.h; noChao = true; } else { c.y = b.y + b.h; }
      c.vy = 0;
    }
    return noChao;
  }

  function reiniciarJogador() {
    Object.assign(j, { x: sx - 5, y: sy - 14, vx: 0, vy: 0, inv: cfg.invencivel_s });
  }

  return {
    estado: s,
    passo(dt, acoes) {
      if (s.tela !== 'jogando') return;
      j.vx = ((acoes.direita ? 1 : 0) - (acoes.esquerda ? 1 : 0)) * cfg.velocidade_px_s;
      if (acoes.pular && j.noChao) j.vy = -cfg.pulo_px_s;
      j.vy = Math.min(j.vy + cfg.gravidade_px_s2 * dt, 600);
      j.noChao = mover(j, j.vx * dt, j.vy * dt);
      j.inv = Math.max(0, j.inv - dt);
      for (const i of inimigos) {
        if (!i.vivo) continue;
        i.vy = Math.min(i.vy + cfg.gravidade_px_s2 * dt, 600);
        mover(i, 0, i.vy * dt);
        const antes = i.x;
        mover(i, i.dir * 30 * dt, 0);
        if (i.x === antes || Math.abs(i.x - i.x0) > i.patrulha / 2) i.dir = -i.dir;
        if (sobrepoe(j, i)) {
          if (j.vy > 0 && j.y + j.h - i.y < 8) {
            i.vivo = false;
            s.pontuacao += cfg.pontos_por_inimigo;
            j.vy = -cfg.pulo_px_s * 0.6;
          } else if (j.inv <= 0) {
            s.vida -= 1;
            j.inv = cfg.invencivel_s;
            j.vy = -120;
            j.x += j.x < i.x ? -8 : 8;
          }
        }
      }
      if (j.y > altura + 64) { s.vida -= 1; reiniciarJogador(); }
      if (s.vida <= 0) s.tela = 'derrota';
      else if (inimigos.every((i) => !i.vivo)) s.tela = 'fase_concluida';
    },
    observavel() {
      return { tela: s.tela, pontuacao: s.pontuacao, vida: s.vida, inimigos_vivos: inimigos.filter((i) => i.vivo).length,
        jogador: { posicao: [Math.round(j.x * 100) / 100, Math.round(j.y * 100) / 100], no_chao: j.noChao } };
    },
    posicionar(x, y) { Object.assign(j, { x, y, vx: 0, vy: 0 }); }, // gancho de teste
  };
}
