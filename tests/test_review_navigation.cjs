const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

const source = fs.readFileSync('plataforma/static/fatiador-ux.js', 'utf8');
const reviewCode = source.slice(source.indexOf(' function rows()'), source.indexOf(' function saveStatus('));

function fixture() {
 const document = {activeElement: null};
 const nodes = new Map();
 const mounted = [];
 const released = [];
 const makeNode = () => ({
  hidden: false, dataset: {}, classList: {toggle() {}},
  setAttribute(name, value) { this[name] = value; },
  focus() { document.activeElement = this; },
  querySelectorAll() { return []; },
 });
 const $ = id => {
  if (!nodes.has(id)) nodes.set(id, makeNode());
  return nodes.get(id);
 };
 const click = {};
 const list = $('ux-list');
 let buttons = [];
 let renders = 0;
 Object.assign(list, {
  addEventListener: (type, handler) => click[type] = handler,
  contains: field => buttons.includes(field),
  querySelectorAll: () => buttons,
 });
 Object.defineProperty(list, 'innerHTML', {set(markup) {
  renders++;
  buttons = Array.from(markup.matchAll(/data-ux-row="([^"]+)"/g), match => {
   const button = makeNode();
   button.dataset.uxRow = match[1];
   button.closest = () => button;
   return button;
  });
 }});
 const phrases = [
  {id: 'first', novo: 'Primeira', speaker: 'A', aprovado: true},
  {id: 'alert', novo: 'Verificar', speaker: 'B', aprovado: true, speaker_pendente: true},
  {id: 'last', novo: 'Última', speaker: 'A', aprovado: true},
 ];
 const editors = phrases.map(row => ({...makeNode(), dataset: {swapRow: row.id}}));
 $('flist').querySelectorAll = () => editors;
 const context = {
  window: {RipagemAudio: {mount: field => mounted.push(field), release: field => released.push(field)}},
  $,
  all: () => [],
  esc: value => String(value),
  fmt: () => '',
  document,
  U: {plan: {itens: phrases}, capture: () => phrases},
  list, listMarkup: '', displayedIds: [], listButtons: new Map(), editors: new Map(), openEditor: null,
  filter: 'all', search: '', active: '',
  moreFilters: {...makeNode(), querySelector: () => makeNode()},
 };
 vm.createContext(context);
 vm.runInContext(reviewCode, context);
 return {context, list, document, click: event => click.click(event), editors, mounted, released, renders: () => renders};
}

test('trocar a frase conserva os botões e o foco, liberando somente o player anterior', () => {
 const view = fixture();
 view.context.refresh();
 const [alert, first] = view.list.querySelectorAll();
 assert.equal(alert['aria-current'], 'true');
 first.focus();
 view.click({target: first});
 assert.equal(view.renders(), 1);
 assert.equal(view.document.activeElement, first);
 assert.equal(first['aria-current'], 'true');
 assert.equal(alert['aria-current'], 'false');
 assert.equal(view.editors[0].hidden, false);
 assert.equal(view.editors[1].hidden, true);
 assert.equal(view.released[0], view.editors[1]);
 view.context.refresh();
 assert.equal(view.renders(), 1);
 assert.equal(view.document.activeElement, first);
});

test('atalho percorre a ordem que aparece na lista, com alertas primeiro', () => {
 const view = fixture();
 view.context.refresh();
 const [alert, first, last] = view.list.querySelectorAll();
 alert.focus();
 let handled = 0;
 const down = {key: 'ArrowDown', preventDefault: () => handled++};
 view.context.stepRow(down);
 assert.equal(view.document.activeElement, first);
 view.context.stepRow(down);
 assert.equal(view.document.activeElement, last);
 view.context.stepRow(down);
 assert.equal(handled, 2);
 assert.equal(view.renders(), 1);
});
