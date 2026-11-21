// Cena Three.js gerada pelo CEW: carrega todos os assets do asset_manifest.json.
// Modelos GLB com GLTFLoader (Y para cima, metros), texturas em planos, audio com loop.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { carregarManifesto, Audio, painelAudio, pronto } from './manifesto.js';

const el = document.getElementById('cena');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(window.innerWidth, window.innerHeight);
el.appendChild(renderer.domElement);
const cena = new THREE.Scene();
cena.background = new THREE.Color(0x202428);
const camera = new THREE.PerspectiveCamera(50, window.innerWidth / window.innerHeight, 0.01, 1000);
camera.position.set(0, 1.5, 4);
const controles = new OrbitControls(camera, renderer.domElement);
cena.add(new THREE.HemisphereLight(0xffffff, 0x404040, 2.0));
const sol = new THREE.DirectionalLight(0xffffff, 1.5);
sol.position.set(3, 5, 2);
cena.add(sol);
cena.add(new THREE.GridHelper(10, 10, 0x555555, 0x333333));
const mixers = [];
const relogio = new THREE.Clock();

window.addEventListener('resize', () => {
  camera.aspect = window.innerWidth / window.innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(window.innerWidth, window.innerHeight);
});

async function iniciar() {
  const m = await carregarManifesto();
  const audio = new Audio();
  const gltf = new GLTFLoader();
  const tex = new THREE.TextureLoader();
  let x = -2;
  for (const a of m.doTipo('modelo')) {
    const g = await gltf.loadAsync(m.url(a));
    g.scene.position.set(x, 0, 0);
    x += 1.5;
    cena.add(g.scene);
    if (g.animations.length) {
      const mixer = new THREE.AnimationMixer(g.scene);
      mixer.clipAction(g.animations[0]).play();
      mixers.push(mixer);
    }
  }
  const texturas = m.doTipo('textura');
  texturas.forEach((a, i) => {
    const t = tex.load(m.url(a));
    t.colorSpace = a.metadados.espaco_cor === 'linear' ? THREE.NoColorSpace : THREE.SRGBColorSpace;
    t.magFilter = THREE.NearestFilter;
    const mat = new THREE.MeshBasicMaterial({ map: t, transparent: !!a.metadados.tem_alfa, side: THREE.DoubleSide });
    const plano = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 0.5), mat);
    plano.position.set((i % 12) * 0.6 - 3.3, 1.2 + Math.floor(i / 12) * 0.6, -1.5);
    cena.add(plano);
  });
  painelAudio(m, audio);
  pronto(`${m.bruto.assets.length} assets (${m.doTipo('modelo').length} modelos, ${texturas.length} texturas)`);
}

renderer.setAnimationLoop(() => {
  const dt = relogio.getDelta();
  mixers.forEach((mx) => mx.update(dt));
  controles.update();
  renderer.render(cena, camera);
});

iniciar().catch((e) => { console.error(e); document.getElementById('status').textContent = 'erro: ' + e.message; });
