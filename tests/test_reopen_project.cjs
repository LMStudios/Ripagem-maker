const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const {test} = require('node:test');

test('continuar projeto ignora cliques repetidos e permite tentar novamente após falha', async () => {
 const html = fs.readFileSync('index.html', 'utf8');
 const handler = html.slice(html.indexOf('async function reopenSavedProject()'), html.indexOf('function transcriptionBlocked()'));
 const button = {disabled: false}, select = {value: 'project'}, notice = {textContent: ''};
 const fields = {'reopen': button, 'saved-work': select, 'reopen-error': notice};
 let reply, requests = 0, opened;
 const scope = {$: id => fields[id], show: data => { opened = data; },
   fetch: (_url, options) => {
    requests++;
    assert.equal(JSON.parse(options.body).folder, 'project');
    return new Promise(resolve => { reply = resolve; });
   }};
 vm.runInNewContext(handler, scope);
 const first = button.onclick();
 await button.onclick();
 assert.equal(requests, 1);
 assert.equal(select.disabled, true);
 reply({ok: false, json: async () => ({erro: 'Falha temporária'})});
 await first;
 assert.equal(notice.textContent, 'Falha temporária');
 assert.equal(button.disabled, false);
 const retry = button.onclick();
 reply({ok: true, json: async () => ({folder: 'project'})});
 await retry;
 assert.equal(requests, 2);
 assert.equal(opened.folder, 'project');
 assert.equal(notice.textContent, '');
 assert.equal(select.disabled, false);
});
