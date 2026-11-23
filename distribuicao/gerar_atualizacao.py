"""Gera o mesmo ZIP de atualização para Windows e Mac, sem dependências ou dados."""
import importlib.util,hashlib,json,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location('pack',ROOT/'distribuicao/empacotar.py');P=importlib.util.module_from_spec(spec);spec.loader.exec_module(P)
def build():
 version=(ROOT/'VERSION').read_text().strip()
 files={p.relative_to(ROOT).as_posix():p.read_bytes() for p in P.files()}
 for name in ('iniciar.py','requirements.txt'):files[name]=(ROOT/'distribuicao'/name).read_bytes()
 for name in ('desktop_boot.py','desktop_win.py','prepare_windows.py'):files[name]=(ROOT/'distribuicao/windows'/name).read_bytes()
 manifest={'formato':'ripagem-update-v1','versao':version,'arquivos':{name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()}}
 dest=ROOT/'distribuicao/pacotes'/('Ripagem-Maker-Atualizacao-'+version+'.zip');dest.parent.mkdir(exist_ok=True)
 with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
  for name,raw in files.items():z.writestr(name,raw)
  z.writestr('atualizacao.json',json.dumps(manifest,ensure_ascii=False))
 digest=hashlib.sha256(dest.read_bytes()).hexdigest()
 dest.with_suffix('.sha256').write_text(digest+'  '+dest.name+'\n')
 notes=(ROOT/'CHANGELOG.md').read_text(encoding='utf-8') if (ROOT/'CHANGELOG.md').is_file() else ''
 section=notes.split(f'## {version}\n',1)
 summary=section[1].split('\n## ',1)[0].strip() if len(section)==2 else ''
 dest.with_suffix('.latest.json').write_text(json.dumps({'versao':version,'sha256':digest,'notas':summary[:2000]},ensure_ascii=False),encoding='utf-8')
 print(dest)
 return dest
if __name__=='__main__':build()
