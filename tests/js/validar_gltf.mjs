// Valida arquivos .glb com o glTF Validator oficial da Khronos e imprime um JSON por arquivo.
// Uso: node tests/js/validar_gltf.mjs arquivo1.glb [arquivo2.glb ...]
// Sem argumentos: valida todos os .glb em projects/*/web/assets/.
import fs from 'node:fs';
import path from 'node:path';
import validator from 'gltf-validator';

function listarPadrao() {
  const base = 'projects';
  const saida = [];
  if (!fs.existsSync(base)) return saida;
  const visitar = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const p = path.join(d, e.name);
      if (e.isDirectory() && e.name !== 'node_modules') visitar(p);
      else if (e.isFile() && p.endsWith('.glb') && p.includes(`${path.sep}web${path.sep}`)) saida.push(p);
    }
  };
  visitar(base);
  return saida;
}

const arquivos = process.argv.slice(2).length ? process.argv.slice(2) : listarPadrao();
let erros = 0;
const resultados = [];
for (const arq of arquivos) {
  const r = await validator.validateBytes(new Uint8Array(fs.readFileSync(arq)));
  const contagem = {};
  (r.info && r.info.totalVertexCount !== undefined) && (contagem.vertices = r.info.totalVertexCount);
  resultados.push({ arquivo: arq, versao_validador: r.validatorVersion, erros: r.issues.numErrors, avisos: r.issues.numWarnings,
    mensagens: r.issues.messages.filter((m) => m.severity <= 1).slice(0, 20), info: r.info || {} });
  erros += r.issues.numErrors;
}
console.log(JSON.stringify({ arquivos: resultados.length, erros, resultados }, null, 2));
process.exit(erros ? 1 : 0);
