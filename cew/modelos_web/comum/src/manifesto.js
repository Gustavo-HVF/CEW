// Carrega e confere o asset_manifest.json gerado pelo CEW (schemas/asset_manifest.schema.json).
// O jogo nunca usa caminhos soltos: tudo passa pelo id estavel do asset.

export async function carregarManifesto(url = './asset_manifest.json') {
  const r = await fetch(url, { cache: 'no-cache' });
  if (!r.ok) throw new Error(`asset_manifest.json: HTTP ${r.status}`);
  const m = await r.json();
  if (m.gerado_por !== 'cew' || !Array.isArray(m.assets)) throw new Error('asset_manifest.json invalido');
  const porId = new Map(m.assets.map((a) => [a.id, a]));
  return {
    bruto: m,
    porId,
    url: (a) => './' + a.caminho_web,
    doTipo: (tipo) => m.assets.filter((a) => a.tipo === tipo),
    get: (id) => {
      const a = porId.get(id);
      if (!a) throw new Error(`asset desconhecido: ${id}`);
      return a;
    },
  };
}

// Audio com pontos de loop do manifesto (a web nao le loop dentro do OGG).
export class Audio {
  constructor() {
    this.ctx = null;
    this.buffers = new Map();
    this.tocando = new Map();
  }
  _ctx() {
    this.ctx ??= new (window.AudioContext || window.webkitAudioContext)();
    return this.ctx;
  }
  async carregar(asset, url) {
    if (this.buffers.has(asset.id)) return this.buffers.get(asset.id);
    const dados = await (await fetch(url)).arrayBuffer();
    const buf = await this._ctx().decodeAudioData(dados);
    this.buffers.set(asset.id, buf);
    return buf;
  }
  async tocar(asset, url) {
    this.parar(asset);
    const buf = await this.carregar(asset, url);
    const fonte = this._ctx().createBufferSource();
    fonte.buffer = buf;
    const loop = asset.metadados && asset.metadados.loop;
    const taxa = (asset.metadados && asset.metadados.taxa_amostragem_hz) || buf.sampleRate;
    if (loop) {
      fonte.loop = true;
      fonte.loopStart = loop.inicio_amostra / taxa;
      fonte.loopEnd = loop.fim_amostra / taxa;
    }
    fonte.connect(this._ctx().destination);
    fonte.start();
    this.tocando.set(asset.id, fonte);
  }
  parar(asset) {
    const f = this.tocando.get(asset.id);
    if (f) { f.stop(); this.tocando.delete(asset.id); }
  }
}

export function painelAudio(manifesto, audio) {
  const div = document.getElementById('audio');
  for (const a of manifesto.doTipo('audio')) {
    const b = document.createElement('button');
    b.textContent = '▶ ' + a.caminho_web.split('/').pop() + (a.metadados.loop ? ' (loop)' : '');
    b.onclick = () => audio.tocar(a, manifesto.url(a)).catch((e) => console.warn(e));
    div.appendChild(b);
  }
}

// Contrato com os testes de marco: o app mantem em window.__CEW_ESTADO o que pode ser observado
// (posicao do jogador, tela atual, pontuacao...). Use estado({...}) sempre que algo mudar.
export function estado(parcial) {
  window.__CEW_ESTADO = { ...(window.__CEW_ESTADO || {}), ...parcial };
  return window.__CEW_ESTADO;
}

export function pronto(texto) {
  document.getElementById('status').textContent = texto;
  estado({ assets_carregados: true });
  window.__CEW_PRONTO = true;
}
