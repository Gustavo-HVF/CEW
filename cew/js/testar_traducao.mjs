// Roda os casos de equivalencia de uma unidade traduzida (schemas/testes_traducao.schema.json).
// Uso: node testar_traducao.mjs <modulo.js> <casos.json>  -> imprime {"casos", "aprovados", "falhas"} na ultima linha.
// Bytes nos casos: {"$bytes": "hex"} vira Uint8Array na entrada e e comparado como hex na saida.
import fs from 'node:fs';
import { pathToFileURL } from 'node:url';

const [modulo, arqCasos] = process.argv.slice(2);
const spec = JSON.parse(fs.readFileSync(arqCasos, 'utf-8'));
const tol = spec.tolerancia || 0;

const deHex = (h) => Uint8Array.from(h.match(/../g) || [], (b) => parseInt(b, 16));
const paraHex = (u) => Array.from(u, (b) => b.toString(16).padStart(2, '0')).join('');
function decodificar(v) {
  if (Array.isArray(v)) return v.map(decodificar);
  if (v && typeof v === 'object') {
    if (typeof v.$bytes === 'string') return deHex(v.$bytes);
    return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, decodificar(x)]));
  }
  return v;
}
function normalizar(v) {
  if (v instanceof Uint8Array || v instanceof Uint8ClampedArray) return { $bytes: paraHex(v) };
  if (ArrayBuffer.isView(v)) return Array.from(v);
  if (Array.isArray(v)) return v.map(normalizar);
  if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, normalizar(x)]));
  return v;
}
function igual(a, b) {
  if (typeof a === 'number' && typeof b === 'number') return Number.isNaN(a) ? Number.isNaN(b) : Math.abs(a - b) <= tol;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => igual(x, b[i]));
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ka = Object.keys(a).sort(), kb = Object.keys(b).sort();
    return ka.length === kb.length && ka.every((k, i) => k === kb[i] && igual(a[k], b[k]));
  }
  return a === b;
}

const saida = { casos: spec.casos.length, aprovados: 0, falhas: [] };
try {
  const mod = await import(pathToFileURL(modulo).href);
  const fn = mod[spec.funcao] ?? mod.default?.[spec.funcao];
  if (typeof fn !== 'function') throw new Error(`o modulo nao exporta a funcao ${spec.funcao}`);
  for (const [i, c] of spec.casos.entries()) {
    try {
      const obtido = normalizar(await fn(...decodificar(c.entrada)));
      if (igual(obtido, c.saida)) saida.aprovados++;
      else saida.falhas.push(`caso ${c.nome || i}: esperado ${JSON.stringify(c.saida)}, obtido ${JSON.stringify(obtido)}`);
    } catch (e) {
      saida.falhas.push(`caso ${c.nome || i}: ${e && e.message ? e.message : e}`);
    }
  }
} catch (e) {
  saida.falhas.push(String(e && e.message ? e.message : e));
}
console.log(JSON.stringify(saida));
