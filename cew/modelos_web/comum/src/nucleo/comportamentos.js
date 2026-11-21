// Liga os elementos das cenas (src/cena.js) ao comportamento do jogo, por categoria ou tipo original.
// O nucleo nao depende do motor: cada fabrica recebe a entidade da cena e um contexto do jogo.
const porCategoria = new Map();
const porTipo = new Map();

export function registrarComportamento({ categoria, tipo_original: tipo }, fabrica) {
  if (tipo) porTipo.set(tipo, fabrica);
  else if (categoria) porCategoria.set(categoria, fabrica);
  else throw new Error('registrarComportamento: informe categoria ou tipo_original');
}

// Devolve [{entidade, comportamento}] e a lista de entidades que ficaram sem comportamento.
export function instanciar(cena, contexto) {
  const ativos = [], semComportamento = [];
  for (const e of cena.entidades) {
    const fabrica = porTipo.get(e.tipo_original) || porCategoria.get(e.categoria);
    if (fabrica) ativos.push({ entidade: e, comportamento: fabrica(e, contexto) });
    else semComportamento.push(e);
  }
  return { ativos, semComportamento };
}

// Posicao inicial do jogador: entidade de categoria spawn/jogador (a primeira, ou a de nome dado).
export function posicaoInicial(cena, nome) {
  const s = cena.entidades.find((e) => (e.categoria === 'spawn' || e.categoria === 'jogador') && (!nome || e.nome === nome));
  return s ? s.posicao : null;
}

// Alvos de portas/gatilhos (ex.: Quake: target -> targetname).
export function porNome(cena, nome) {
  return cena.entidades.filter((e) => e.nome === nome);
}
