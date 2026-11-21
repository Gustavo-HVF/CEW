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
  // Navegadores so liberam audio depois de um gesto da pessoa: chame uma vez no inicio.
  desbloquear() {
    const liberar = () => {
      this._ctx().resume?.();
      window.removeEventListener('pointerdown', liberar);
      window.removeEventListener('keydown', liberar);
    };
    window.addEventListener('pointerdown', liberar);
    window.addEventListener('keydown', liberar);
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

// Medidor de quadros: window.__CEW_ESTADO.quadro sobe a cada quadro e .fps e atualizado a cada 0,5 s
// (os testes de sessao e de desempenho usam isso para provar que o jogo nao travou).
function iniciarMedidor() {
  if (window.__CEW_MEDIDOR) return;
  window.__CEW_MEDIDOR = true;
  let ultimo = performance.now(), quadros = 0;
  const passo = (agora) => {
    const e = window.__CEW_ESTADO || (window.__CEW_ESTADO = {});
    e.quadro = (e.quadro || 0) + 1;
    quadros++;
    if (agora - ultimo >= 500) {
      e.fps = Math.round((quadros * 1000) / (agora - ultimo));
      quadros = 0;
      ultimo = agora;
    }
    requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
}

export function pronto(texto) {
  document.getElementById('status').textContent = texto;
  estado({ assets_carregados: true });
  iniciarMedidor();
  window.__CEW_PRONTO = true;
}
