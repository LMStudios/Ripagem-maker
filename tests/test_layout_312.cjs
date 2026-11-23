// Layout 3.12: carregado por último, sem mudar a lógica; etapas na ordem certa; Ajustes em abas.
const fs = require('fs'), path = require('path'), assert = require('assert');
const root = path.resolve(__dirname, '..'), read = p => fs.readFileSync(path.join(root, p), 'utf8');

const fatiador = read('index.html');
const scripts = [...fatiador.matchAll(/<script src="\/static\/([^"?]+)/g)].map(m => m[1]);
assert.strictEqual(scripts[scripts.length - 1], 'studio-layout.js', 'o layout precisa ser o último script da troca de potes');
assert.ok(fatiador.includes('/static/studio-layout.css'), 'estilo do layout ausente');

const final = read('plataforma/static/finalizacao.js');
assert.ok(final.includes('nav.insertBefore(captions,delivery)'), 'Legendas (6) deve vir antes de Entrega (7)');

const guided = read('plataforma/static/fluxo-guiado.js');
assert.ok(/\]\.filter\(Boolean\)\)/.test(guided), 'elementos ausentes não podem virar o texto "null"');

const panel = read('plataforma/static/index.html');
const panelScripts = [...panel.matchAll(/<script src="\/static\/([^"?]+)/g)].map(m => m[1]);
assert.strictEqual(panelScripts[panelScripts.length - 1], 'ajustes-abas.js', 'as abas de Ajustes precisam envolver todas as outras versões da rota');

// Todo cartão conhecido de Ajustes cai num grupo (nenhum some por falta de aba).
const source = read('plataforma/static/ajustes-abas.js');
const groups = [...source.matchAll(/\['(\w+)', '[^']+', (\/[^\n]+\/i)\]/g)].map(m => [m[1], eval(m[2])]);
const titles = ['Fluxo de Troca de potes', 'Notificações de tarefas', 'Margem dos takes', 'Integrações e APIs', 'Versão e atualizações',
  'Limpar o início das trocas de fala', 'Transcrição e cortes', 'Pasta dos novos projetos', 'Mover um projeto com os materiais',
  'Armazenamento e limpeza', 'Limpeza automática', 'Tratamento de áudio padrão', 'Limpeza segura de materiais'];
for (const title of titles) assert.ok(groups.some(([, re]) => re.test(title)), 'sem aba: ' + title);

// A camada de layout não reescreve regras: não chama as rotas de geração, takes ou XML diretamente.
const layout = read('plataforma/static/studio-layout.js');
for (const forbidden of ['/fatiador/trocas/', 'fetch(']) assert.ok(!layout.includes(forbidden), 'layout não deve chamar o servidor: ' + forbidden);
console.log('layout 3.12 ok');
