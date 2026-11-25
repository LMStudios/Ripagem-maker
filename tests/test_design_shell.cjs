// Ripagem Maker 4: sistema visual e casca de navegação carregados nas duas telas, sem lógica de servidor.
const fs = require('fs'), path = require('path'), assert = require('assert');
const root = path.resolve(__dirname, '..'), read = p => fs.readFileSync(path.join(root, p), 'utf8');

const panel = read('plataforma/static/index.html'), fatiador = read('index.html');
for (const [name, html] of [['painel', panel], ['troca de potes', fatiador]]) {
  const css = [...html.matchAll(/<link rel="stylesheet" href="\/static\/([^"?]+)/g)].map(m => m[1]);
  assert.strictEqual(css[css.length - 1], 'design.css', `design.css precisa ser a última folha de estilo no ${name}`);
  assert.ok(html.includes('/static/shell.js'), `shell.js ausente no ${name}`);
}
// Os testes de layout exigem estes scripts por último.
const last = html => [...html.matchAll(/<script src="\/static\/([^"?]+)/g)].map(m => m[1]).pop();
assert.strictEqual(last(panel), 'ajustes-abas.js');
assert.strictEqual(last(fatiador), 'studio-layout.js');

// Todos os destinos da navegação existem e têm ícone.
const css = read('plataforma/static/design.css');
for (const r of ['/', '/projetos', '/demanda', '/ferramentas', '/nomes', '/ajustes', '/studio', '/equipe']) {
  assert.ok(css.includes(`.nav a[data-r="${r}"]{--i:`), 'sem ícone: ' + r);
  if (r !== '/equipe') assert.ok(panel.includes(`data-r="${r}"`), 'sem link na navegação: ' + r);
}
assert.ok(panel.includes('href="/fatiador"'));
// Módulos que injetam links não duplicam os que já estão no HTML.
assert.ok(read('plataforma/static/ferramentas.js').includes(`!document.querySelector('.nav a[data-r="/ferramentas"]')`));
assert.ok(read('plataforma/static/graphite.js').includes(`!nav.querySelector('[data-r="/studio"]')`));

// A casca só navega: não chama rotas de geração, takes ou XML.
const shell = read('plataforma/static/shell.js');
for (const forbidden of ['/fatiador/trocas/', "method: 'POST'", 'method:"POST"']) assert.ok(!shell.includes(forbidden), 'shell não deve alterar dados: ' + forbidden);
const fetches = [...shell.matchAll(/fetch\('([^']+)'/g)].map(m => m[1]);
assert.deepStrictEqual(fetches, ['/api/projetos']);
console.log('design shell ok');
