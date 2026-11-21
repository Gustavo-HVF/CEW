// Cena Babylon.js gerada pelo CEW: carrega os assets do asset_manifest.json.
import { Engine, Scene, ArcRotateCamera, HemisphericLight, Vector3, Color3, Color4, MeshBuilder, StandardMaterial, Texture, SceneLoader, TransformNode, Quaternion } from '@babylonjs/core';
import '@babylonjs/loaders/glTF';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';
import { carregarCenas, registrarCena, CORES } from './cena.js';

const canvas = document.createElement('canvas');
canvas.style.width = '100%';
canvas.style.height = '100%';
document.getElementById('cena').appendChild(canvas);
const engine = new Engine(canvas, true);
const cena = new Scene(engine);
cena.useRightHandedSystem = true; // mesmo sistema do glTF e das cenas do CEW (Y para cima, mao direita)
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
  const containers = new Map();
  for (const c of await carregarCenas(m)) {
    let inst = 0, marcadores = 0;
    const plano = c.dimensao === '2d';
    for (const e of c.entidades) {
      const no = new TransformNode(e.id, cena);
      if (plano) {
        no.position = Vector3.FromArray(e.posicao_m).add(new Vector3(-5, 4, -3)); // mapa 2D vira uma camada plana
        no.rotation.z = -(e.guinada_graus || 0) * Math.PI / 180;
      } else {
        no.position = Vector3.FromArray(e.posicao);
        if (e.rotacao) no.rotationQuaternion = Quaternion.FromArray(e.rotacao);
        if (e.escala) no.scaling = Vector3.FromArray(e.escala);
      }
      no.metadata = { cew: { categoria: e.categoria, tipo_original: e.tipo_original } };
      const a = e.asset_id ? m.get(e.asset_id) : null;
      if (a && a.tipo === 'modelo' && !plano) {
        if (!containers.has(a.id)) {
          const url = m.url(a);
          containers.set(a.id, await SceneLoader.LoadAssetContainerAsync(url.slice(0, url.lastIndexOf('/') + 1), url.slice(url.lastIndexOf('/') + 1), cena));
        }
        containers.get(a.id).instantiateModelsToScene().rootNodes.forEach((r) => { r.parent = no; });
      } else {
        const caixa = MeshBuilder.CreateBox(e.id + ':marcador', { size: 0.3 }, cena);
        const mat = new StandardMaterial(e.id + ':mat', cena);
        mat.diffuseColor = Color3.FromHexString('#' + (CORES[e.categoria] ?? 0xffffff).toString(16).padStart(6, '0'));
        caixa.material = mat;
        caixa.parent = no;
        marcadores++;
      }
      inst++;
    }
    registrarCena(c, inst, marcadores);
  }
  painelAudio(m, audio);
  pronto(`${m.bruto.assets.length} assets`);
}

engine.runRenderLoop(() => cena.render());
window.addEventListener('resize', () => engine.resize());
iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
