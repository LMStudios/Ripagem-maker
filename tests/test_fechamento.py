import unittest,xml.etree.ElementTree as E
from unittest.mock import patch
from plataforma import fechamento as F,montagem as MT

class ClosingTests(unittest.TestCase):
 def test_positions_and_kept_ranges_at_both_edges(self):
  cuts=[(20,25),(120,125)]
  self.assertEqual([F.position(x,cuts) for x in [0,20,23,25,120,125,150]],[0,20,20,20,115,115,140])
  self.assertEqual(F.kept(0,150,cuts),[(0,20),(25,120),(125,150)])
 def test_xml_ripples_all_tracks_preserving_new_audio_and_source_rate(self):
  seq=E.fromstring('''<sequence><duration>150</duration><media><video><track><clipitem id="v"><start>0</start><end>150</end><in>0</in><out>144</out><rate><timebase>24</timebase></rate></clipitem></track></video><audio><track><clipitem id="old"><start>0</start><end>20</end><in>0</in><out>20</out></clipitem></track><track><clipitem id="disabled"><start>20</start><end>75</end><in>20</in><out>75</out><enabled>FALSE</enabled></clipitem></track><track><clipitem id="new"><start>25</start><end>75</end><in>0</in><out>50</out></clipitem></track></audio></media><marker><in>25</in><out>75</out></marker></sequence>''')
  F.xml(seq,[(20,25)],25)
  self.assertEqual(seq.findtext('duration'),'145');a=seq.findall('./media/audio/track');new=a[2].find('clipitem')
  self.assertEqual([new.findtext(k) for k in ['start','end','in','out']],['20','70','0','50'])
  self.assertEqual(a[0].findtext('clipitem/end'),new.findtext('start'));self.assertEqual(a[1].findtext('clipitem/enabled'),'FALSE')
  video=seq.findall('./media/video/track/clipitem');self.assertEqual(video[0].findtext('end'),video[1].findtext('start'));self.assertEqual(video[1].findtext('in'),'24');self.assertEqual(seq.findtext('marker/in'),'20')
  self.assertEqual(len({c.get('id') for c in seq.findall('.//clipitem')}),len(seq.findall('.//clipitem')))
 def test_nearby_replacements_close_only_original_gap(self):
  changes=[{'a':25,'b':75,'start':25,'extra':0},{'a':82,'b':110,'start':82,'extra':0}]
  with patch.object(MT,'margin_ms',return_value=200):cuts=F.windows(changes,25)
  self.assertEqual(cuts,[(20,25),(75,82)])
  self.assertEqual(F.position(75,cuts),F.position(82,cuts))
 def test_no_margin_does_not_move_anything(self):
  with patch.object(MT,'margin_ms',return_value=0):self.assertEqual(F.windows([{'a':25,'b':75,'start':25,'extra':0}],25),[])
