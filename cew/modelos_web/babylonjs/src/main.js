// Cena Babylon.js gerada pelo CEW: carrega os assets do asset_manifest.json.
import { Engine, Scene, ArcRotateCamera, HemisphericLight, Vector3, Color4, MeshBuilder, StandardMaterial, Texture, SceneLoader } from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';

const canvas = document.createElement('canvas');
canvas.style.width = '100%';
canvas.style.height = '100%';
document.getElementById('cena').appendChild(canvas);
const engine = new Engine(canvas, true);
const cena = new Scene(engine);
cena.clearColor = new Color4(0.12, 0.14, 0.16, 1);
const camera = new ArcRotateCamera('camera', -Math.PI / 2, Math.PI / 2.5, 5, Vector3.Zero(), cena);
camera.attachControl(canvas, true);
new HemisphericLight('luz', new Vector3(0, 1, 0), cena);

async function iniciar() {
  const m = await carregarManifesto();
  const audio = new Audio();
  let x = -2;
  for (const a of m.doTipo('modelo')) {
    const url = m.url(a);
    const pasta = url.slice(0, url.lastIndexOf('/') + 1);
    const arquivo = url.slice(url.lastIndexOf('/') + 1);
    const r = await SceneLoader.ImportMeshAsync('', pasta, arquivo, cena);
    r.meshes[0].position.x = x;
    x += 1.5;
    r.animationGroups.forEach((g, i) => (i === 0 ? g.start(true) : g.stop()));
  }
  m.doTipo('textura').forEach((a, i) => {
    const plano = MeshBuilder.CreatePlane('tex' + i, { size: 0.5, sideOrientation: 2 }, cena);
    const mat = new StandardMaterial('mat' + i, cena);
    mat.diffuseTexture = new Texture(m.url(a), cena, false, true, Texture.NEAREST_SAMPLINGMODE);
    mat.diffuseTexture.hasAlpha = !!a.metadados.tem_alfa;
    mat.emissiveTexture = mat.diffuseTexture;
    plano.material = mat;
    plano.position = new Vector3((i % 12) * 0.6 - 3.3, 1.2 + Math.floor(i / 12) * 0.6, 1.5);
  });
  painelAudio(m, audio);
  pronto(`${m.bruto.assets.length} assets`);
}

engine.runRenderLoop(() => cena.render());
window.addEventListener('resize', () => engine.resize());
iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
