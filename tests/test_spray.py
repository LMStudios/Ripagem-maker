import unittest
from plataforma import formas as F
class SprayTests(unittest.TestCase):
 def config(self,source='spray',target='capsule',**kw):return F.normalize(dict(ativo=True,origem=source,destino=target,**kw))
 def test_all_other_forms_both_directions_three_languages(self):
  templates={'en':'Our formula contains {form}.','pt':'Nossa fórmula contém {form}.','es':'Nuestra fórmula contiene {form}.'}
  for form in F.FORMS:
   if form=='spray':continue
   for source,target in [('spray',form),(form,'spray')]:
    for lang,template in templates.items():
     for plural in ((0,1) if F.FORMS[source][lang][0]!=F.FORMS[source][lang][1] else (0,)):
      with self.subTest(source=source,target=target,lang=lang,plural=plural):
       original=template.format(form=F.FORMS[source][lang][plural]);text,notes=F.adapt(original,self.config(source,target))
       self.assertEqual(text,template.format(form=F.FORMS[target][lang][plural]));self.assertFalse(F.pending(notes))
 def test_instructions_do_not_transfer_dosage(self):
  for text in ['Spray twice into your mouth.','Use 2 sprays.','Borrife duas vezes ao dia.','Press the pump into your mouth.']:
   self.assertTrue(F.match(text,self.config()));adapted,notes=F.adapt(text,self.config());self.assertTrue(F.pending(notes));self.assertEqual(adapted,text)
   adapted,notes=F.adapt(text,self.config(uso_novo='Follow confirmed capsule instructions.'));self.assertFalse(F.pending(notes));self.assertEqual(adapted,'Follow confirmed capsule instructions.')
 def test_routes_and_boundaries(self):
  for route in ('oral','sublingual','cutanea'):
   self.assertEqual(self.config('capsule','spray',via_uso=route)['via_uso'],route)
  with self.assertRaises(ValueError):self.config('spray','capsule',via_uso='cutanea')
  self.assertFalse(F.match('The display is ready.',self.config()))
