import copy
import json
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import xml.etree.ElementTree as ET
from plataforma import visuais as V,trocas as T,ml_core as M

class VisualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.src=cls.root/'source.mp4';cls.assets=cls.root/'Materiais';cls.assets.mkdir()
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=blue:s=160x90:r=25:d=8','-f','lavfi','-i','sine=frequency=220:duration=8','-c:v','libx264','-c:a','aac','-shortest',str(cls.src)],check=True)
        for name,color,duration in [('kit_1_red.mp4','red',.8),('1_pote_green.mp4','green',.6),('kit_3_yellow.mp4','yellow',.8),('3_potes_purple.mp4','purple',.6)]:
            subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i',f'color={color}:s=90x160:r=25:d={duration}','-an','-c:v','libx264',str(cls.assets/name)],check=True)
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        self.case=tempfile.TemporaryDirectory();self.out=Path(self.case.name);shutil.copy(self.src,self.out/'_fonte.mp4')
        words=[{'text':text,'start':1000+i*200,'end':1180+i*200,'speaker':'A'} for i,text in enumerate('One bottle works. Six months pass. Three bottles work.'.split())]
        (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':[{'text':'Old.','start':0,'end':100,'speaker':'A'}]+words,'audio_duration':8}))
        (self.out/'frases_TEST.json').write_text(json.dumps({'produto':'Old','produto_novo':'New','frases':[{'n':1,'speaker':'A','start':1000,'end':3300,'text':'Old works.','novo':'New works.'}]}))
        T.build(self.out,'Old')
        V.write(self.out,dict(V.load(self.out),modo_takes='recortes'))
    def tearDown(self):self.case.cleanup()
    def job(self):return M.Job('visual_test','Teste local',None)
    def setup_plan(self):
        V.scan(self.job(),self.out,self.assets);V.detect(self.out);s=V.load(self.out);first=s['mentions'][0];s['mentions']=[dict(first,start=1000,end=3300)];s['max_clip_s']=1;V.write(self.out,s);return V.schedule(self.out,seed=19)
    def test_first_mention_matches_joined_and_split_brand_without_early_usage(self):
        plan=T.load(self.out);plan['produto']='GoldenBrain';T.write(T.plan_path(self.out),plan)
        words=[{'text':t,'start':i*200,'end':i*200+150,'speaker':'A'}
               for i,t in enumerate('Apply the patch. Try Golden Brain today.'.split())]
        (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}))
        self.assertEqual(V.first_product_mention(self.out),800)
        plan['produto']='Golden Brain';T.write(T.plan_path(self.out),plan)
        words[4]['text']='GoldenBrain';del words[5]
        (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}))
        self.assertEqual(V.first_product_mention(self.out),800)

    def test_unknown_first_mention_cannot_export_markers_as_prepared_takes(self):
        state=V.load(self.out)
        state.update(cobrir_falas=True,incluir=True,sem_takes=False)
        with patch.object(V,'first_product_mention',return_value=None),patch.object(V,'audio_windows',return_value=[]),patch.object(V,'coverage_policy',return_value={}):
            state.update(audio_windows=[],coverage_policy={})
            V.write(self.out,state)
            with self.assertRaisesRegex(ValueError,'primeira menção'):
                V.valid_prepared(self.out)

    def test_first_mention_never_joins_speakers_sentences_or_long_pauses(self):
        plan=T.load(self.out);plan['produto']='GoldenBrain';T.write(T.plan_path(self.out),plan)
        for first,second,start,speaker in [('Golden.','Brain',200,'A'),('Golden','Brain',200,'B'),('Golden','Brain',2000,'A')]:
            with self.subTest(first=first,speaker=speaker,start=start):
                words=[{'text':first,'start':0,'end':100,'speaker':'A'},
                       {'text':second,'start':start,'end':start+100,'speaker':speaker}]
                (self.out/'transcricao_bruta.json').write_text(json.dumps({'words':words}))
                self.assertIsNone(V.first_product_mention(self.out))

    def test_midproject_product_correction_invalidates_cached_take_plan(self):
        state=V.load(self.out)
        state.update(cobrir_falas=True,audio_windows=V.audio_windows(self.out),
                     coverage_policy=V.coverage_policy(self.out),prepared={'signature':'old','segments':[]},
                     segments=[{'asset':'old'}])
        V.write(self.out,state)
        plan=T.load(self.out);plan['produto']='CorrectedBrand';T.write(T.plan_path(self.out),plan)
        updated=V.current_state(self.out)
        self.assertIsNone(updated['prepared']);self.assertFalse(updated['segments'])
        self.assertTrue(updated['cobertura_desatualizada'])
        self.assertEqual(updated['modo_takes'],state['modo_takes'])
        self.assertEqual(updated['assets'],state['assets'])

    def test_basis_uses_canonical_source_path(self):
        import os
        self.assertEqual(V.basis(self.out),V.basis(Path(os.path.relpath(self.out,Path.cwd()))))

    def test_appledouble_and_hidden_materials_are_ignored(self):
        from unittest.mock import patch
        folder=self.out/'mac-library';folder.mkdir()
        for name in ('1_pote_video.mp4','3_potes_video.mp4'):
            shutil.copy(self.assets/'kit_1_red.mp4' if name.startswith('1') else self.assets/'kit_3_yellow.mp4',folder/name)
            (folder/('._'+name)).write_bytes(b'\x00\x05\x16\x07AppleDouble metadata')
        (folder/'.hidden.mp4').write_bytes(b'not video')
        (folder/'__MACOSX').mkdir();(folder/'__MACOSX'/'ghost.mp4').write_bytes(b'not video')
        with patch.object(V,'probe',wraps=V.probe) as probe:
            result=V.scan(self.job(),self.out,folder)
        self.assertEqual(result['materiais'],2);self.assertEqual(result['avisos'],[])
        self.assertEqual(probe.call_count,2)
        self.assertEqual({Path(r[0]).name for r in V.inventory(folder)},{'1_pote_video.mp4','3_potes_video.mp4'})
        initial=V.inventory(folder);(folder/'._1_pote_video.mp4').write_bytes(b'changed metadata only')
        self.assertEqual(V.inventory(folder),initial)

    def test_detect_quantities_and_ignore_months_prices(self):
        result=V.detect(self.out);self.assertEqual([r['kit'] for r in result['mentions']],[1,3])
        self.assertEqual(result['mentions'][0]['start'],850)
        (self.out/'precos_TROCA.json').write_text(json.dumps({'mapa_qtd':{'3|frascos':'6'}}))
        self.assertEqual([r['kit'] for r in V.detect(self.out)['mentions']],[1,6])
        self.assertEqual(V.guess_kit('kit_6/animacao.mp4'),6)
        self.assertEqual(V.guess_kit('3 potes/animacao.mp4'),3)
        self.assertIsNone(V.guess_kit('material_049_v2.mp4'))

    def test_500_distinct_takes_allow_other_files_but_501_are_rejected(self):
        folder = self.out / 'biblioteca'
        folder.mkdir()
        for i in range(500):
            (folder / f'1_pote_{i:03}.mp4').write_bytes(f'take {i}'.encode())
        (folder / 'LEIA-ME.txt').write_text('arquivo de apoio', encoding='utf-8')
        (folder / 'z-copia.mp4').write_bytes(b'take 0')
        with patch.object(V, 'probe', return_value={'kind':'video','duration':2,'width':160,'height':90}):
            self.assertEqual(V.scan(self.job(), self.out, folder)['materiais'], 500)
            (folder / '1_pote_500.mp4').write_bytes(b'take 500')
            with self.assertRaisesRegex(ValueError, 'até 500 materiais'):
                V.scan(self.job(), self.out, folder)
            self.assertEqual(len(V.load(self.out)['assets']), 500)

    def test_schedule_covers_frames_and_never_repeats(self):
        s=self.setup_plan();segments=s['segments'];self.assertGreaterEqual(len(segments),3);self.assertFalse(s['issues'])
        self.assertEqual(segments[0]['start_frame'],25);self.assertEqual(segments[-1]['end_frame'],round(3.3*25))
        for a,b in zip(segments,segments[1:]):self.assertEqual(a['end_frame'],b['start_frame']);self.assertNotEqual(a['asset'],b['asset'])
        self.assertEqual(segments,V.schedule(self.out,seed=19)['segments'])
    def test_single_material_is_pending_instead_of_loop(self):
        self.setup_plan();s=V.load(self.out);s['assets']=[next(a for a in s['assets'] if a['kit']==1)];V.write(self.out,s)
        result=V.schedule(self.out,seed=1);self.assertFalse(result['segments']);self.assertIn('outro material',result['issues'][0]['error'])
        with self.assertRaises(ValueError):V.prepare(self.job(),self.out)
    def test_duplicate_files_and_cancel(self):
        folder=self.out/'duplicates';folder.mkdir();src=self.assets/'kit_1_red.mp4';shutil.copy(src,folder/src.name);shutil.copy(src,folder/'1_pote_copy.mp4')
        V.scan(self.job(),self.out,folder);s=V.load(self.out);self.assertEqual(len(s['assets']),1);self.assertTrue(s['warnings'])
        job=self.job();job.cancel=True
        with self.assertRaises(M.Cancelled):V.scan(job,self.out,self.assets)
    def test_render_silent_full_frame_xml_and_preview(self):
        self.setup_plan();V.prepare(self.job(),self.out);segments=V.valid_prepared(self.out,False)
        for s in segments:
            metadata=T.probe(self.out/s['file'],False);self.assertFalse(metadata['has_audio']);self.assertAlmostEqual(metadata['fps'],25,places=4);self.assertEqual((metadata['width'],metadata['height']),(160,90))
            self.assertAlmostEqual(metadata['duration'],(s['end_frame']-s['start_frame'])/25,delta=.002)
        result=T.export_xml(self.out,visual_only=True);xml=ET.parse(self.out/result['xml']);video=xml.findall('.//sequence/media/video/track');self.assertEqual(len(video),2)
        overlays=video[1].findall('clipitem');self.assertEqual(len(overlays),len(segments));self.assertTrue(all(c.findtext('in')=='0' for c in overlays))
        self.assertTrue(all(c.find('file/media/audio') is None for c in overlays))
        self.assertEqual(len(xml.findall('.//sequence/media/audio/track/clipitem')),1)
        p=V.preview(self.job(),self.out,segments[0]['mention']);meta=T.probe(self.out/p['arquivo']);self.assertTrue(meta['has_audio'])
        self.assertAlmostEqual(meta['duration'],(segments[-1]['end_frame']-segments[0]['start_frame'])/25,delta=.06)
        s=V.load(self.out);V.save(self.out,{'max_clip_s':2,'incluir':True});self.assertIsNone(V.load(self.out)['prepared']);self.assertTrue((self.out/segments[0]['file']).exists())
        with self.assertRaises(ValueError):T.export_xml(self.out,visual_only=True)
    def test_manual_overlap_and_changed_basis_block(self):
        self.setup_plan();V.add(self.out,{'start':2000,'end':4000,'kit':1})
        with self.assertRaises(ValueError):V.schedule(self.out)
        s=V.load(self.out);s['mentions']=s['mentions'][:1];V.write(self.out,s)
        (self.out/'precos_TROCA.json').write_text(json.dumps({'mapa_qtd':{'1|frascos':'3'}}))
        with self.assertRaises(ValueError):V.schedule(self.out)
    def test_combined_xml_keeps_a2_a3_and_adds_v2(self):
        # A menção sintética precisa estar dentro da fala trocada, como na mídia real.
        raw_data=json.loads((self.out/'transcricao_bruta.json').read_text());raw_data['words'][0].update(start=1000,end=1100);(self.out/'transcricao_bruta.json').write_text(json.dumps(raw_data))
        self.setup_plan();V.prepare(self.job(),self.out);V.save(self.out,{'incluir':True})
        plan=T.load(self.out);row=plan['itens'][0];raw=self.out/'voice.wav'
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','sine=frequency=1000:duration=2.3',str(raw)],check=True)
        audio=T.fit(self.job(),self.out,row,raw);T.record_audio(self.out,row['id'],audio);T.save(self.out,[{'id':row['id'],'aprovado':True}]);T.approve_audio(self.out,row['id'],audio['texto_hash'])
        result=T.export_xml(self.out);xml=ET.parse(self.out/result['xml'])
        self.assertEqual(len(xml.findall('.//sequence/media/video/track')),2)
        tracks=xml.findall('.//sequence/media/audio/track');self.assertEqual(len(tracks),3)
        self.assertEqual(tracks[1].findtext('clipitem/enabled'),'FALSE');self.assertEqual(tracks[2].findtext('clipitem/enabled'),'TRUE')
        (self.out/'precos_TROCA.json').write_text(json.dumps({'mapa_qtd':{'1|frascos':'3'}}))
        with self.assertRaises(ValueError):T.export_xml(self.out)

    def test_still_image_fills_frame_without_audio(self):
        from PIL import Image
        library=self.out/'Imagens';library.mkdir();Image.new('RGB',(50,100),(255,0,0)).save(library/'1_pote.png')
        V.scan(self.job(),self.out,library);V.detect(self.out);state=V.load(self.out);state['mentions']=state['mentions'][:1];V.write(self.out,state);state=V.schedule(self.out,seed=2)
        self.assertEqual(len(state['segments']),1);V.prepare(self.job(),self.out);segment=V.valid_prepared(self.out,False)[0]
        file=self.out/segment['file'];meta=T.probe(file,False);self.assertFalse(meta['has_audio']);self.assertEqual((meta['width'],meta['height']),(160,90))
        import numpy as np
        data=subprocess.check_output([M.FFMPEG,'-v','error','-i',str(file),'-frames:v','1','-f','rawvideo','-pix_fmt','rgb24','-'])
        rgb=np.frombuffer(data,dtype=np.uint8).reshape(90,160,3)
        for y,x in ((0,0),(0,159),(89,0),(89,159)):
            self.assertGreater(int(rgb[y,x,0]),220);self.assertLess(int(rgb[y,x,1]),20)

    def test_inclusion_toggle_keeps_prepared_signature(self):
        self.setup_plan();V.prepare(self.job(),self.out);before=copy.deepcopy(V.load(self.out)['prepared'])
        V.save(self.out,{'incluir':True});self.assertEqual(V.load(self.out)['prepared'],before);self.assertTrue(V.valid_prepared(self.out))



    def test_automatic_chain_reuses_prepared_and_edits(self):
        result=V.automatic(self.job(),self.out,str(self.assets),1)
        self.assertEqual(result['mentions'],2);s=V.load(self.out);self.assertTrue(s['incluir']);self.assertFalse(s.get('sem_takes'));files=[r['file'] for r in s['prepared']['segments']]
        first=s['mentions'][0];V.save(self.out,{'mentions':[{'id':first['id'],'start':900,'end':first['end'],'kit':1,'selected':True}]})
        V.automatic(self.job(),self.out,str(self.assets),1);self.assertEqual(V.load(self.out)['mentions'][0]['start'],900)
        prepared=V.load(self.out)['prepared'];V.automatic(self.job(),self.out,str(self.assets),1);self.assertEqual(V.load(self.out)['prepared'],prepared)
        self.assertTrue(all((self.out/f).exists() for f in files))
    def test_automatic_unknown_kit_and_cancel(self):
        folder=self.out/'Unsorted';folder.mkdir();shutil.copy(self.assets/'kit_1_red.mp4',folder/'take.mp4')
        with self.assertRaisesRegex(ValueError,'não há material associado'):V.automatic(self.job(),self.out,str(folder))
        self.assertEqual(len(V.load(self.out)['assets']),1)
        job=self.job();job.cancel=True
        with self.assertRaises(M.Cancelled):V.automatic(job,self.out,str(self.assets))
    def test_single_take_replacement_preserves_other_segments(self):
        extra=self.assets/'kit_1_orange.mp4'
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=orange:s=90x160:r=25:d=2','-an','-c:v','libx264',str(extra)],check=True)
        try:
            s=self.setup_plan();before=copy.deepcopy(s['segments']);target=next(a for a in s['assets'] if a['name']==extra.name)
            # Encontra posição sem o novo material em vizinhos, com duração suportada.
            index=next(i for i,seg in enumerate(before) if seg['asset']!=target['id'] and all(before[j]['asset']!=target['id'] for j in (i-1,i+1) if 0<=j<len(before)))
            changed=V.replace_segment(self.out,{'index':index,'asset':target['id']})
            self.assertEqual(changed['segments'][index]['asset'],target['id'])
            for i,row in enumerate(before):
                if i!=index:self.assertEqual(changed['segments'][i],row)
            bad=next(a for a in s['assets'] if a['kit']==3)
            with self.assertRaises(ValueError):V.replace_segment(self.out,{'index':index,'asset':bad['id']})
        finally:extra.unlink()
    def test_explicit_skip_takes_is_persisted(self):
        self.setup_plan();s=V.save(self.out,{'incluir':True,'sem_takes':True});self.assertTrue(s['sem_takes']);self.assertFalse(s['incluir'])
        self.assertEqual(V.valid_prepared(self.out),[])

    def test_team_naming_quantity_and_support(self):
        for name,qty,fmt in [('1 POTE - V.mp4',1,'V'),('2 PRODUTO - H.mp4',2,'H'),('3 UGC - V.mp4',3,'V'),('KIT 3/3 POTES - V - 4.mp4',3,'V'),('KIT 6/6 POTES - H.mp4',6,'H'),('OUTROS/7 POTES - V - 2.mp4',7,'V'),('OUTROS/9 POTES - V.mp4',9,'V')]:
            info=V.material_info(name);self.assertEqual(info['kit'],qty);self.assertEqual(info['formato'],fmt)
        for name in ['ESTEIRA - V - 1.mp4','ESTOQUE - V.mp4','UGC 01- V.mp4','MAE UGC 03.mp4','SETA - H.png','KIT 1/ESTOQUE - V.mp4']:
            self.assertIsNone(V.guess_kit(name))
        self.assertEqual(V.material_info('ESTOQUE - V.mp4')['categoria'],'estoque')
    def test_support_does_not_block_automatic_prep(self):
        support=self.assets/'ESTOQUE - V.mp4'
        subprocess.run([M.FFMPEG,'-y','-v','error','-f','lavfi','-i','color=orange:s=90x160:r=25:d=1','-an','-c:v','libx264',str(support)],check=True)
        try:
            result=V.automatic(self.job(),self.out,str(self.assets),1);self.assertEqual(result['falas_cobertas'],0);self.assertEqual(result['takes_apoio'],0)
            s=V.load(self.out);stock=next(a for a in s['assets'] if a['name']==support.name);self.assertFalse(any(seg['asset']==stock['id'] for seg in s['segments']))
        finally:support.unlink()
    def test_rename_refreshes_cached_library(self):
        folder=self.out/'materials';folder.mkdir();src=folder/'sem_nome.mp4';shutil.copy(self.assets/'kit_1_red.mp4',src);shutil.copy(self.assets/'1_pote_green.mp4',folder/'1 POTE - V - 2.mp4')
        V.scan(self.job(),self.out,folder);src.rename(folder/'1 POTE - V - 1.mp4')
        # Só uma menção de kit 1 para isolar a releitura da pasta.
        V.detect(self.out);s=V.load(self.out);s['mentions']=[s['mentions'][0]];V.write(self.out,s)
        V.automatic(self.job(),self.out,str(folder),1);s=V.load(self.out)
        self.assertTrue(all(a['kit']==1 for a in s['assets']));self.assertFalse(any('sem_nome' in a['path'] for a in s['assets']))
    def test_manual_association_survives_rescan(self):
        folder=self.out/'stock';folder.mkdir();shutil.copy(self.assets/'kit_1_red.mp4',folder/'ESTOQUE - V.mp4');V.scan(self.job(),self.out,folder);s=V.load(self.out);rid=s['assets'][0]['id']
        V.save(self.out,{'assets':[{'id':rid,'kit':6}]});V.scan(self.job(),self.out,folder);self.assertEqual(V.load(self.out)['assets'][0]['kit'],6)

    def test_month_packages_only_after_explicit_mapping(self):
        text='One month package works. Six month study results. Three or six month package today.'
        words=[{'text':t,'start':1000+i*250,'end':1200+i*250,'speaker':'A'} for i,t in enumerate(text.split())]
        T.write(self.out/'transcricao_bruta.json',{'words':words})
        self.assertEqual(V.detect(self.out)['mentions'],[])
        V.save(self.out,{'mapa_meses':{'1':1,'3':3,'6':6}});s=V.detect(self.out)
        self.assertEqual([r['kit'] for r in s['mentions']],[1,3,6]);self.assertTrue(all('referencia_meses' in r for r in s['mentions']))
    def test_automatic_preserves_confirmed_month_mapping(self):
        V.save(self.out,{'mapa_meses':{'1':1,'3':3,'6':6}});V.automatic(self.job(),self.out,str(self.assets),1)
        self.assertEqual(V.load(self.out)['mapa_meses'],{'1':1,'3':3,'6':6})
        with self.assertRaises(ValueError):V.save(self.out,{'mapa_meses':{'6':'talvez'}})

    def test_audio_coverage_fills_gaps_and_preserves_quantity(self):
        state=self.setup_plan();plan=T.load(self.out);plan['itens'][0]['aprovado']=True;T.write(T.plan_path(self.out),plan)
        state['mentions'][0].update(start=1800,end=2200)
        state['cobrir_falas']=True;V.write(self.out,state)
        state=V.refresh_coverage(self.out,state);rows=V.covered_mentions(self.out,state)
        from plataforma.armazenamento import visual_margin_ms
        self.assertEqual([(r['start'],r['end'],r['kit']) for r in rows],[(0,1800,None),(1800,2200,1),(2200,3300+visual_margin_ms(),None)])
        for asset in list(state['assets']):
            if asset['kit']==3:asset['kit']=None
        V.write(self.out,state);state=V.schedule(self.out,seed=3)
        self.assertFalse(state['issues']);segments=state['segments']
        self.assertEqual(segments[0]['start_frame'],0);self.assertEqual(segments[-1]['end_frame'],round((3300+visual_margin_ms())/1000*25))
        for a,b in zip(segments,segments[1:]):self.assertEqual(a['end_frame'],b['start_frame']);self.assertNotEqual(a['asset'],b['asset'])
        V.prepare(self.job(),self.out);self.assertTrue(V.valid_prepared(self.out,False))
        plan['itens'][0]['fim_ms']=3400;T.write(T.plan_path(self.out),plan)
        with self.assertRaisesRegex(ValueError,'falas selecionadas mudaram'):V.valid_prepared(self.out,False)

    def test_audio_coverage_reports_missing_support(self):
        state=self.setup_plan();plan=T.load(self.out);plan['itens'][0]['aprovado']=True;T.write(T.plan_path(self.out),plan)
        state.update(cobrir_falas=True,mentions=[]);V.write(self.out,state)
        state=V.schedule(self.out,seed=1)
        self.assertTrue(state['issues']);self.assertIn('Apoio',state['issues'][0]['error'])

    def test_prepared_takes_reused_without_rendering_again(self):
        from unittest.mock import patch
        self.setup_plan();first=V.prepare(self.job(),self.out);files=[s['file'] for s in V.valid_prepared(self.out,False)]
        with patch.object(M,'run_proc',side_effect=AssertionError('Unchanged takes must not render again')):
            result=V.prepare(self.job(),self.out)
        self.assertEqual(result['reutilizados'],result['segmentos'])
        self.assertEqual(files,[s['file'] for s in V.valid_prepared(self.out,False)])
        self.assertTrue(all((self.out/f).exists() for f in files))
