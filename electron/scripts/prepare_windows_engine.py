"""Constrói um runtime Windows x64 separado: Python oficial, wheels Windows e FFmpeg.
Pode ser preparado no Mac; nenhum executável Mac é incluído no instalador Windows.
"""
import hashlib,importlib.util,json,re,shutil,struct,subprocess,sys,zipfile
from pathlib import Path
import requests
HERE=Path(__file__).resolve().parents[1];ROOT=HERE.parent;DEST=HERE/'engine-windows';CACHE=HERE/'.windows-downloads'

def fetch(url,name):
    target=CACHE/name
    if target.exists():return target
    print('Baixando '+name,flush=True)
    temporary=target.with_suffix(target.suffix+'.part')
    with requests.get(url,stream=True,timeout=(30,180)) as response:
        response.raise_for_status()
        with temporary.open('wb') as f:
            for block in response.iter_content(1024*1024):f.write(block)
    temporary.replace(target);return target

def pe_machine(path):
    with Path(path).open('rb') as f:
        assert f.read(2)==b'MZ',str(path)+' não é executável Windows'
        f.seek(0x3c);offset=struct.unpack('<I',f.read(4))[0];f.seek(offset);assert f.read(4)==b'PE\0\0';return struct.unpack('<H',f.read(2))[0]

def safe_extract(z,destination):
    for entry in z.infolist():
        target=(destination/entry.filename).resolve()
        if not target.is_relative_to(destination.resolve()):raise ValueError('Caminho inválido no arquivo baixado.')
        z.extract(entry,destination)

def main():
    CACHE.mkdir(exist_ok=True);DEST.mkdir(exist_ok=True);(DEST/'bin').mkdir(exist_ok=True)
    page=requests.get('https://www.python.org/downloads/windows/',timeout=30);page.raise_for_status()
    links=re.findall(r'href="(https://www.python.org/ftp/python/3\.13\.[^"/]+/python-3\.13\.[^"/]+-embed-amd64\.zip)"',page.text)
    if not links:raise RuntimeError('Python Windows 3.13 não localizado no site oficial.')
    python_url=max(set(links),key=lambda x:tuple(map(int,re.search(r'/python/(3\.13\.\d+)/',x)[1].split('.'))));python_version=re.search(r'/python/(3\.13\.\d+)/',python_url)[1]
    archive=fetch(python_url,python_url.rsplit('/',1)[1]);python=DEST/'bin/python';python.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:safe_extract(z,python)
    (python/'python313._pth').write_text('python313.zip\n.\nLib/site-packages\nimport site\n')
    shutil.copy2(HERE/'scripts/engine_entry.py',python/'engine_entry.py')
    site=python/'Lib/site-packages'
    if site.exists():shutil.rmtree(site)
    site.mkdir(parents=True)
    wheels=CACHE/'wheels'
    if wheels.exists():shutil.rmtree(wheels)
    wheels.mkdir()
    subprocess.run([sys.executable,'-m','pip','download','--disable-pip-version-check','--only-binary=:all:','--platform','win_amd64','--implementation','cp','--python-version','313','--abi','cp313','--dest',str(wheels),'-r',str(ROOT/'distribuicao/requirements.txt'),'-c',str(HERE/'windows-runtime-constraints.txt'),'pywin32-ctypes','colorama'],check=True)
    wheel_records=[]
    for whl in sorted(wheels.glob('*.whl')):
        if not any(tag in whl.name for tag in ('win_amd64','none-any')):raise ValueError('Wheel fora da plataforma alvo: '+whl.name)
        with zipfile.ZipFile(whl) as z:
            for entry in z.infolist():
                if entry.is_dir():continue
                parts=Path(entry.filename).parts
                if parts[0].endswith('.data'):
                    if len(parts)>2 and parts[1] in ('purelib','platlib'):relative=Path(*parts[2:])
                    else:continue
                else:relative=Path(*parts)
                target=(site/relative).resolve()
                if not target.is_relative_to(site.resolve()):raise ValueError('Wheel inválido')
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(z.read(entry))
        wheel_records.append({'file':whl.name,'sha256':hashlib.file_digest(whl.open('rb'),'sha256').hexdigest()})
    ffmpeg_url='https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip';ffarchive=fetch(ffmpeg_url,'ffmpeg-release-essentials.zip')
    digest=fetch(ffmpeg_url+'.sha256','ffmpeg-release-essentials.zip.sha256').read_text().split()[0].lower();assert hashlib.file_digest(ffarchive.open('rb'),'sha256').hexdigest()==digest,'Checksum FFmpeg divergente'
    ffdir=DEST/'bin/ffmpeg';ffdir.mkdir(exist_ok=True)
    with zipfile.ZipFile(ffarchive) as z:
        for name in z.namelist():
            if name.endswith(('/bin/ffmpeg.exe','/bin/ffprobe.exe','/LICENSE','/LICENSE.txt')):(ffdir/Path(name).name).write_bytes(z.read(name))
        readme=next((name for name in z.namelist() if name.endswith('/README.txt')),None)
        if readme:(ffdir/'README.txt').write_bytes(z.read(readme))
    vc_url='https://aka.ms/vs/17/release/vc_redist.x64.exe';vc=fetch(vc_url,'vc_redist.x64.exe');shutil.copy2(vc,DEST/'bin/vc_redist.x64.exe')
    spec=importlib.util.spec_from_file_location('cleanpack',ROOT/'distribuicao/empacotar.py');pack=importlib.util.module_from_spec(spec);spec.loader.exec_module(pack)
    code=DEST/'code'
    if code.exists():shutil.rmtree(code)
    code.mkdir()
    for source in pack.files():
        target=code/source.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
    for name in ('iniciar.py','requirements.txt'):shutil.copy2(ROOT/'distribuicao'/name,code/name)
    for binary in [python/'python.exe',ffdir/'ffmpeg.exe',ffdir/'ffprobe.exe']:
        if pe_machine(binary)!=0x8664:raise ValueError('Executável não é Windows x64: '+str(binary))
    runtime={'kind':'python-embedded','platform':'win32','machine':'AMD64','python':python_version,'python_url':python_url,'python_sha256':hashlib.file_digest(archive.open('rb'),'sha256').hexdigest(),'ffmpeg_url':ffmpeg_url,'ffmpeg_sha256':digest,'vc_runtime_url':vc_url,'wheels':wheel_records}
    (DEST/'runtime.json').write_text(json.dumps(runtime,indent=2));(DEST/'manifest.json').write_text(json.dumps({p.relative_to(DEST).as_posix():hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in DEST.rglob('*') if p.is_file() and p.name!='manifest.json'},indent=2))
    print('Runtime Windows x64 pronto. Python '+python_version+'; '+str(len(wheel_records))+' wheels; nenhum dado pessoal.',flush=True)
if __name__=='__main__':main()
