// Cenas do CEW: elementos do mapa (inimigos, vegetacao, estruturas, itens...) ja posicionados.
// O arquivo vem de web/dados/cenas/ (tipo "mapa" no asset_manifest.json) e segue schemas/dados/cena.schema.json:
// 3D em metros, Y para cima, mao direita, rotacao em quaternion [x,y,z,w];
// 2D em pixels com origem no topo esquerdo e rotacao em graus no sentido horario.
import { estado } from './manifesto.js';

export const CORES = {
  inimigo: 0xe53935, npc: 0x8e24aa, jogador: 0x1e88e5, spawn: 0x43a047, vegetacao: 0x2e7d32, estrutura: 0x9e9e9e,
  decoracao: 0xbcaaa4, item: 0xfdd835, porta: 0x6d4c41, plataforma: 0x78909c, gatilho: 0xff9800, luz: 0xfff59d,
  som: 0x00acc1, camera: 0x546e7a, veiculo: 0x3949ab, efeito: 0xf06292, regiao: 0x80cbc4, outro: 0xffffff,
};

export async function carregarCenas(manifesto) {
  const lista = manifesto.bruto.assets.filter((a) => a.tipo === 'mapa' && a.caminho_web.startsWith('dados/cenas/'));
  const cenas = [];
  for (const a of lista) {
    const r = await fetch(manifesto.url(a));
    if (!r.ok) throw new Error(`cena ${a.caminho_web}: HTTP ${r.status}`);
    const c = await r.json();
    if (c.estado !== 'normalizada') throw new Error(`cena ${a.caminho_web} nao normalizada`);
    cenas.push(c);
  }
  return cenas;
}

// Origem do sprite 2D pela ancora gravada na cena.
export function origem2d(ancora) {
  return { topo_esquerdo: [0, 0], base_esquerda: [0, 1], base_centro: [0.5, 1], centro: [0.5, 0.5] }[ancora || 'topo_esquerdo'];
}

// Informa aos testes quantos elementos de cada cena foram de fato colocados no jogo.
export function registrarCena(cena, instanciadas, placeholders) {
  const cenas = { ...((window.__CEW_ESTADO && window.__CEW_ESTADO.cenas) || {}) };
  cenas[cena.id_cena] = { entidades: cena.entidades.length, instanciadas, placeholders, por_categoria: (cena.estatisticas || {}).por_categoria || {} };
  estado({ cenas });
}
