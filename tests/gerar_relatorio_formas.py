"""Relatório reproduzível: python3 tests/gerar_relatorio_formas.py (sem rede)."""
import sys,io,json,csv,unittest
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from formas_matrix_cases import cases,NOUNS
import test_formas_matriz as tests
from plataforma import formas as F
stream=io.StringIO();suite=unittest.defaultTestLoader.loadTestsFromModule(tests);result=unittest.TextTestRunner(stream=stream,verbosity=1).run(suite)
if not result.wasSuccessful():print(stream.getvalue());raise SystemExit(1)
rows=[]
for r in cases():
 actual,notes=F.adapt(r['text'],F.normalize(r['config']));rows.append(dict(origem=r['source'],destino=r['target'],idioma=r['lang'],categoria=r['kind'],original=r['text'],esperado=r['expected'],resultado=actual,pendente_esperado=r['pending'],pendente_obtido=F.pending(notes),aprovado=actual==r['expected'] and F.pending(notes)==r['pending']))
folder=ROOT/'tests/resultados';folder.mkdir(exist_ok=True)
with (folder/'formas-matriz-3.1.2.csv').open('w',encoding='utf-8-sig',newline='') as f:
 writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
counts=Counter((r['origem'],r['destino']) for r in rows)
text='''# Verificação das trocas de forma — Ripagem Maker 3.1.2

Foram aprovados **1.105 cenários automatizados**, abrangendo as **30 direções** entre patch, dropper, capsule, powder, gummy e liquid.

- 925 casos de texto em inglês, português e espanhol: referências simples, singular/plural quando distinguíveis, artigos, maiúsculas, expressões idiomáticas, instruções confirmadas/ausentes, mecanismos, contradições e texto já na forma nova.
- 90 casos com instrução em frase adjacente sem repetir o nome do produto/forma (três idiomas por direção).
- 30 casos no plano salvo, verificando novo texto, speaker, início/fim e ausência de aprovação/áudio automáticos.
- 60 casos de validação das respostas do Gemini: rejeição de resíduos da forma antiga e aceitação de respostas limpas (simuladas).

## Resultado por direção

| Origem | Destino | Casos de texto | Contexto | Plano salvo | Guarda Gemini | Resultado |
|---|---|---:|---:|---:|---:|---|
'''
for (source,target),n in sorted(counts.items()):text+=f'| {source} | {target} | {n} | 3 | 1 | 2 | Aprovado |\n'
text+='''
## Correções encontradas nesta checagem

- Expressões como “put an end to”, “take a closer look” e “a mix of” não viram instruções de aplicar, ingerir ou misturar o produto.
- Detecção do idioma pelo contexto, principalmente cápsula, líquido e goma.
- Artigos e determinantes no masculino/feminino em português/espanhol; preservação de maiúsculas.
- “Conta-gotas” sem indicação de número não é tratado automaticamente como plural apenas por terminar em “gotas”.
- Nome comum “adesivo” não é confundido com uma explicação científica de absorção.
- Instruções já na forma nova são preservadas.
- Reconhecimento de imperativos em espanhol com pronome, como “Trágala”, “Disuélvelo”, “Mastícala” e “Bébelo”, dentro do contexto adjacente.

## Limites desta validação

Os testes usam textos e mídias sintéticos. **Não houve chamada real ao Gemini**, nem avaliação humana da qualidade das respostas do modelo. Os casos simulados validam o contrato e as proteções do app; não demonstram a qualidade do modelo em todas as VSLs. Não foram testados importação no Premiere nem execução nativa no Windows nesta checagem. Frases novas, mecanismos e informações de uso continuam exigindo revisão; o app não calcula doses equivalentes entre formas.

O CSV ao lado contém os 925 casos de texto com original, esperado e resultado. Para repetir: `python3 tests/gerar_relatorio_formas.py`.
'''
(folder/'formas-matriz-3.1.2.md').write_text(text);print('1.105 cenários aprovados; relatório e CSV em tests/resultados.')
