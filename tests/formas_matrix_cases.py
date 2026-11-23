"""Casos editoriais independentes: formas simples, idiomas, uso e mecanismo."""
from itertools import permutations
NOUNS={
 'patch':{'en':('patch','patches'),'pt':('adesivo','adesivos'),'es':('parche','parches')},
 'dropper':{'en':('dropper','droppers'),'pt':('conta-gotas','conta-gotas'),'es':('gotero','goteros')},
 'capsule':{'en':('capsule','capsules'),'pt':('cápsula','cápsulas'),'es':('cápsula','cápsulas')},
 'powder':{'en':('powder','powder'),'pt':('pó','pó'),'es':('polvo','polvo')},
 'gummy':{'en':('gummy','gummies'),'pt':('goma','gomas'),'es':('gomita','gomitas')},
 'liquid':{'en':('liquid','liquid'),'pt':('líquido','líquido'),'es':('líquido','líquido')}}
USE={
 'patch':('Wear one patch on your skin for 24 hours.','Aplique um adesivo na pele todos os dias.','Aplica un parche en la piel cada día.'),
 'dropper':('Put two drops under your tongue twice daily.','Pingue duas gotas embaixo da língua por dia.','Pon dos gotas debajo de la lengua cada día.'),
 'capsule':('Swallow two capsules with water every day.','Engula duas cápsulas com água por dia.','Traga dos cápsulas con agua cada día.'),
 'powder':('Mix one scoop of powder with water daily.','Misture uma medida de pó com água por dia.','Mezcla una medida de polvo con agua cada día.'),
 'gummy':('Chew two gummies every day.','Mastigue duas gomas todos os dias.','Mastica dos gomitas cada día.'),
 'liquid':('Drink 5 ml of liquid every day.','Beba 5 ml de líquido por dia.','Bebe 5 ml de líquido cada día.')}
MECHANISM={
 'patch':('The patch uses transdermal absorption.','O adesivo usa absorção transdérmica.','El parche usa absorción transdérmica.'),
 'dropper':('The dropper uses sublingual absorption.','O conta-gotas usa absorção sublingual.','El gotero usa absorción sublingual.'),
 'capsule':('The capsule bypasses the digestive tract.','A cápsula evita o trato digestivo.','La cápsula evita el tracto digestivo.'),
 'powder':('The powder releases compounds into the bloodstream.','O pó libera compostos na corrente sanguínea.','El polvo libera compuestos en el torrente sanguíneo.'),
 'gummy':('The gummy releases compounds into the bloodstream.','A goma libera compostos na corrente sanguínea.','La gomita libera compuestos en el torrente sanguíneo.'),
 'liquid':('The liquid uses sublingual absorption.','O líquido usa absorção sublingual.','El líquido usa absorción sublingual.')}
LANGS=('en','pt','es')
def cases():
 rows=[]
 def add(source,target,kind,text,expected,pending=False,lang='en',**config):rows.append(dict(source=source,target=target,kind=kind,lang=lang,text=text,expected=expected,pending=pending,config=dict(ativo=True,origem=source,destino=target,**config)))
 for source,target in permutations(NOUNS,2):
  for lang in LANGS:
   for plural in (0,1):
    if plural and NOUNS[source][lang][0]==NOUNS[source][lang][1]:continue
    old=NOUNS[source][lang][plural];new=NOUNS[target][lang][plural]
    template={'en':'Our formulas contain {form}.','pt':'Nossas fórmulas contêm {form}.','es':'Nuestras fórmulas contienen {form}.'}[lang]
    add(source,target,'reference_plural' if plural else 'reference',template.format(form=old),template.format(form=new),lang=lang)
   old=NOUNS[source][lang][0];new=NOUNS[target][lang][0]
   usage={'en':f'Follow the confirmed label instructions for the {new}.','pt':f'Siga a orientação confirmada para {new}.','es':f'Sigue la instrucción confirmada para {new}.'}[lang]
   description={'en':f'The product is supplied as {new}.','pt':f'O produto tem apresentação em {new}.','es':f'El producto se presenta como {new}.'}[lang]
   original=USE[source][LANGS.index(lang)]
   add(source,target,'usage_missing',original,original,True,lang)
   add(source,target,'usage_confirmed',original,usage,False,lang,uso_novo=usage)
   original=MECHANISM[source][LANGS.index(lang)]
   add(source,target,'mechanism_missing',original,original,True,lang,uso_novo=usage)
   add(source,target,'mechanism_confirmed',original,description,False,lang,descricao_nova=description)
  old=NOUNS[source]['en'][0];new=NOUNS[target]['en'][0]
  for template in ('If I could adapt all the extracts in my formula into a {form}, I could put an end to this once and for all.','We can put an end to this with our {form} formula.','Take a closer look at our {form} formula.','This {form} formula takes our presentation to the next level.','Our {form} is a mix of familiar ingredients.'):
   text=template.format(form=old);expected=template.format(form=new)
   if target in ('powder','liquid'):expected=expected.replace('into a '+new,'into the '+new)
   add(source,target,'idiom',text,expected)
  for lang,template in [('en','Our formulas contain {form}.'),('pt','Nossas fórmulas contêm {form}.'),('es','Nuestras fórmulas contienen {form}.')]:
   add(source,target,'uppercase',template.format(form=NOUNS[source][lang][0].upper()),template.format(form=NOUNS[target][lang][0].upper()),lang=lang)
  for lang,template in [('pt','{article} {form} chegou.'),('es','{article} {form} llegó.')]:
   feminine={'capsule','gummy'};old_article=('A' if source in feminine else 'O') if lang=='pt' else ('La' if source in feminine else 'El');new_article=('A' if target in feminine else 'O') if lang=='pt' else ('La' if target in feminine else 'El')
   add(source,target,'article',template.format(article=old_article,form=NOUNS[source][lang][0]),template.format(article=new_article,form=NOUNS[target][lang][0]),lang=lang)
  # Uma instrução na forma já correta não deve ser reescrita pelo substituidor local.
  correct=USE[target][0];add(source,target,'already_target',correct,correct)
  # Quantidade e frequência genuínas não podem atravessar uma troca de forma.
  text=f'Use the {old} once per day.';add(source,target,'real_frequency',text,text,True)
  text=f'Our {old} formula contains no {new}.';add(source,target,'target_contradiction',text,text,True)
  add(source,target,'unrelated','The customer called the support team.','The customer called the support team.')
 return rows
