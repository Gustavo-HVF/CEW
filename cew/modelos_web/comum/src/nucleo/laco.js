// Passo de tempo fixo com acumulador (o "fix your timestep" classico): use quando o original atualiza a
// logica numa frequencia fixa (ex.: 60 Hz) independente da taxa de quadros. A frequencia vem da
// especificacao (especificacoes/logica.md), com evidencia no codigo original.
export function criarLacoFixo(hz, atualizar, { maxPassosPorQuadro = 5 } = {}) {
  const dt = 1000 / hz;
  let acumulado = 0;
  return {
    hz,
    dt_ms: dt,
    // Chame com o tempo do quadro (ms); devolve a fracao para interpolar o desenho.
    passo(dtQuadroMs) {
      acumulado += Math.min(dtQuadroMs, dt * maxPassosPorQuadro);
      let n = 0;
      while (acumulado >= dt && n < maxPassosPorQuadro) {
        atualizar(dt / 1000);
        acumulado -= dt;
        n++;
      }
      return acumulado / dt;
    },
  };
}

// Gerador linear congruente com semente (troque pelos parametros EXATOS do original quando a
// sequencia importar, ex.: geracao de mundo; teste a sequencia em codigo/testes/).
export function criarLcg(semente, { a = 1103515245, c = 12345, mascara = 0x7fffffff } = {}) {
  let x = semente >>> 0;
  return () => {
    x = (Math.imul(x, a) + c) & mascara;
    return x;
  };
}
