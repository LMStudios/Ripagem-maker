import json
import unittest
from unittest.mock import patch
from plataforma import projetos as P,trocas as T
from test_modular import Isolated
class PanelTests(Isolated):
 def test_delivery_none_does_not_break_project_listing(self):
  first=self.project('Primeiro');second=self.project('Segundo');plan=T.load(first);plan['entrega']=None;T.write(T.plan_path(first),plan)
  rows=P.listing(False);self.assertEqual(len(rows),2);self.assertEqual({r['pasta'] for r in rows},{'Primeiro','Segundo'});self.assertEqual(next(r['etapa'] for r in rows if r['pasta']=='Segundo'),'Entregue')
 def test_delivery_missing_is_a_valid_unfinished_project(self):
  out=self.project();plan=T.load(out);plan.pop('entrega',None);T.write(T.plan_path(out),plan);self.assertEqual(P.summary(out)['etapa'],'Falas')

 def test_unexpected_legacy_metadata_keeps_other_projects_accessible(self):
  damaged=self.project('Projeto antigo')
  self.project('Projeto atual')
  (damaged / P.META).write_text('null', encoding='utf-8')
  T.plan_path(damaged).write_text(json.dumps({'forma':None,'itens':[None]}), encoding='utf-8')
  rows={row['pasta']:row for row in P.listing()}
  self.assertEqual(rows['Projeto antigo']['etapa'],'Transcrição')
  self.assertEqual(rows['Projeto antigo']['nome'],'Projeto antigo')
  self.assertEqual(rows['Projeto atual']['etapa'],'Entregue')
