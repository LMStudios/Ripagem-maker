import tempfile,unittest
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET
from plataforma.nomes_arquivos import write_xml

class NamesTests(unittest.TestCase):
    def tree(self):
        root=ET.Element('xmeml');ET.SubElement(ET.SubElement(root,'sequence'),'name').text='antigo';return root
    def test_readable_sequential_names_and_sequence_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=write_xml(self.tree(),tmp,'P Protect para SizeFix','Troca de potes');data=first.read_bytes()
            second=write_xml(self.tree(),tmp,'P Protect para SizeFix','Troca de potes')
            self.assertRegex(first.name,r'^P Protect para SizeFix - Troca de potes - \d{4}-\d{2}-\d{2} - V01.xml$');self.assertTrue(second.name.endswith('V02.xml'));self.assertEqual(first.read_bytes(),data)
            self.assertEqual(ET.parse(first).findtext('sequence/name'),first.stem)
    def test_windows_characters_unicode_and_length(self):
        with tempfile.TemporaryDirectory() as tmp:
            file=write_xml(self.tree(),tmp,'../Gótas: "Teste" / ? * | '+'é'*400,'Troca: ML')
            self.assertEqual(file.parent,Path(tmp));self.assertLess(len(file.name.encode()),255);self.assertFalse(any(c in file.name for c in '<>:"/\\|?*'));ET.parse(file)
    def test_concurrent_exports_never_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp,ThreadPoolExecutor(max_workers=4) as pool:
            files=list(pool.map(lambda _:write_xml(self.tree(),tmp,'SizeFix','Takes visuais'),range(8)))
            self.assertEqual(len(set(files)),8);self.assertTrue(any(p.name.endswith('V08.xml') for p in files))
