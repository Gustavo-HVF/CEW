// Valida todos os esquemas (JSON Schema 2020-12) e os exemplos com ajv, como pede o item 5.1.
// Uso: node tests/js/validar_esquemas.mjs [arquivo.json nome_do_esquema]
import fs from 'node:fs';
import path from 'node:path';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const RAIZ = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')), '..', '..');
const ajv = new Ajv2020({ allErrors: true, strict: false });
addFormats(ajv);

function listar(dir, filtro) {
  const saida = [];
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) saida.push(...listar(p, filtro));
    else if (filtro(p)) saida.push(p);
  }
  return saida.sort();
}

const pastaEsq = path.join(RAIZ, 'schemas');
const esquemas = listar(pastaEsq, (p) => p.endsWith('.schema.json'));
for (const arq of esquemas) ajv.addSchema(JSON.parse(fs.readFileSync(arq, 'utf-8')));
let falhas = 0;
for (const arq of esquemas) {
  const id = JSON.parse(fs.readFileSync(arq, 'utf-8')).$id;
  try { ajv.getSchema(id); } catch (e) { console.error(`ESQUEMA INVALIDO ${arq}: ${e.message}`); falhas++; }
}

function validar(arquivo, nome) {
  const v = ajv.getSchema(`https://cew.local/schemas/${nome}.schema.json`);
  if (!v) { console.error(`esquema desconhecido: ${nome}`); return false; }
  const ok = v(JSON.parse(fs.readFileSync(arquivo, 'utf-8')));
  if (!ok) console.error(`INVALIDO ${path.relative(RAIZ, arquivo)} (${nome}):`, JSON.stringify(v.errors.slice(0, 3)));
  return ok;
}

const args = process.argv.slice(2);
if (args.length === 2) {
  process.exit(validar(args[0], args[1]) ? 0 : 1);
}
const pastaEx = path.join(pastaEsq, 'exemplos');
const exemplos = listar(pastaEx, (p) => p.endsWith('.json'));
for (const ex of exemplos) {
  const nome = path.relative(pastaEx, ex).replace(/\\/g, '/').replace(/\.json$/, '');
  if (!validar(ex, nome)) falhas++;
}
for (const [arq, nome] of [['formats/registry.json', 'registry'], ['config/gemini.json', 'config_gemini'], ['config/versoes.json', 'config_versoes'], ['config/cew.json', 'config_cew'], ['config/equivalencias_api.json', 'equivalencias_api']]) {
  if (!validar(path.join(RAIZ, arq), nome)) falhas++;
}
console.log(`ajv: ${esquemas.length} esquemas, ${exemplos.length} exemplos + registro e configs; ${falhas} falhas`);
process.exit(falhas ? 1 : 0);
