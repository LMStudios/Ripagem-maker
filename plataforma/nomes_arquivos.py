"""Nomes de entrega legíveis, portáveis e sem sobrescrever versões anteriores."""
from datetime import date
from pathlib import Path
import re
import unicodedata
import xml.etree.ElementTree as ET


def clean(value,limit=100):
    value=unicodedata.normalize('NFC',str(value or ''))
    value=re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]',' ',value)
    value=re.sub(r'\s+',' ',value).strip(' ._-') or 'Ripagem'
    # Limite em bytes para funcionar também com nomes acentuados em APFS/NTFS.
    return value.encode('utf-8')[:limit].decode('utf-8','ignore').rstrip(' .')


def write_xml(root,destination,label,kind,*,sequence_name=None):
    """Reserva V01, V02… de forma atômica, inclusive em exportações simultâneas."""
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    prefix=clean(sequence_name.replace(':','-'),200) if sequence_name else f'{clean(label)} - {clean(kind,55)} - {date.today().isoformat()}'
    version=1
    while True:
        path=destination/f'{prefix} - V{version:02d}.xml'
        try:fp=path.open('xb')
        except FileExistsError:version+=1;continue
        try:
            sequence=root.find('sequence')
            if sequence is not None:
                name=sequence.find('name')
                if name is None:name=ET.SubElement(sequence,'name')
                name.text=sequence_name if sequence_name else path.stem
            ET.indent(root)
            with fp:fp.write(ET.tostring(root,encoding='utf-8',xml_declaration=True))
            return path
        except Exception:
            fp.close();path.unlink(missing_ok=True);raise
