// Teste do nucleo SEM motor e SEM navegador (node tests/nucleo_node.mjs <cena.json> <configuracoes.json>):
// a arquitetura do v2.3 separa as regras do jogo do Phaser, entao elas podem ser testadas assim.
import fs from 'node:fs';
import assert from 'node:assert/strict';
import { criarJogo } from '../src/nucleo/jogo.js';

const [arqCena, arqCfg] = process.argv.slice(2);
const cena = JSON.parse(fs.readFileSync(arqCena, 'utf-8'));
const cfg = JSON.parse(fs.readFileSync(arqCfg, 'utf-8')).valores;
const nada = {}, direita = { direita: true }, dt = 1 / cfg.passo_logica_hz;
const rodar = (jogo, acoes, s) => { for (let i = 0; i < s * cfg.passo_logica_hz; i++) jogo.passo(dt, acoes); };

let j = criarJogo(cena, cfg);
rodar(j, nada, 1);
assert.equal(j.observavel().jogador.no_chao, true, 'cai ate o chao');
assert.equal(j.observavel().jogador.posicao[1], 98);
rodar(j, direita, 2);
assert.equal(j.observavel().jogador.posicao[0], 54, 'para na pilastra (x = 64 - 10)');

j = criarJogo(cena, cfg);
rodar(j, nada, 1);
j.posicionar(84, 70);
rodar(j, direita, 3);
const o = j.observavel();
assert.equal(o.inimigos_vivos, 0, 'pisao derrota o slime');
assert.equal(o.pontuacao, cfg.pontos_por_inimigo);
assert.equal(o.tela, 'fase_concluida');
console.log('nucleo ok');
