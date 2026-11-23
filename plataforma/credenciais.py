"""Integrações persistentes, com leitura compatível da configuração antiga."""
import os,re,threading,uuid
from pathlib import Path
import requests
from . import segredos as store
ENV=Path(__file__).resolve().parent.parent/'.env'
LOCK=threading.RLock()
NAME='ASSEMBLYAI_API_KEY'
PROVIDERS=('assemblyai','elevenlabs','minimax','gemini')
def validate_provider(provider):
 if provider not in PROVIDERS:raise ValueError('Serviço de API inválido.')
def legacy():
 value=os.environ.get(NAME,'').strip()
 if not value and ENV.exists():
  for line in ENV.read_text(encoding='utf-8').splitlines():
   if line.startswith(NAME+'='):value=line.split('=',1)[1].strip()
 return value

def key(provider='assemblyai'):
 validate_provider(provider)
 with LOCK:
  try:value=store.get(provider)
  except RuntimeError:
   value=legacy() if provider=='assemblyai' else None
   if not value:raise
  if not value and provider=='assemblyai':
   value=legacy()
   if value:
    try:store.set(provider,value);clear_legacy()
    except (RuntimeError,OSError):pass  # configuração antiga continua disponível se o cofre estiver bloqueado
  if not value:raise RuntimeError('Configure a chave de '+provider+' em Ajustes → Integrações e APIs.')
  return value

def status(provider='assemblyai'):
 validate_provider(provider)
 try:configured=bool(key(provider));error=''
 except RuntimeError as e:configured=False;error=str(e)
 return {'configurada':configured}

def overview():
 result={}
 for p in PROVIDERS:
  try:
   secured=bool(store.get(p));result[p]={'configurada':secured or (p=='assemblyai' and bool(legacy())),'armazenamento':'Cofre do sistema' if secured else ('Configuração antiga; salve novamente para migrar ao cofre' if p=='assemblyai' and legacy() else 'Cofre do sistema')}
  except RuntimeError as e:result[p]={'configurada':p=='assemblyai' and bool(legacy()),'armazenamento':'Configuração antiga' if p=='assemblyai' and legacy() else 'Indisponível','aviso':str(e)}
 return result

def clear_legacy():
 if ENV.exists():
  lines=[line for line in ENV.read_text(encoding='utf-8').splitlines() if not line.startswith(NAME+'=')]
  temporary=ENV.with_name('.env.'+uuid.uuid4().hex+'.tmp')
  try:
   fd=os.open(temporary,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
   with os.fdopen(fd,'w',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
   temporary.replace(ENV)
  finally:temporary.unlink(missing_ok=True)
 os.environ.pop(NAME,None)

def save(value,provider='assemblyai'):
 validate_provider(provider)
 if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_.-]{8,512}',value.strip()):raise ValueError('Cole somente a chave da API, sem espaços ou quebras de linha.')
 with LOCK:
  store.set(provider,value.strip())
  if provider=='assemblyai':clear_legacy()
 return status(provider)

def remove(provider):
 validate_provider(provider)
 with LOCK:
  store.delete(provider)
  if provider=='assemblyai':clear_legacy()
 return status(provider)

def test(provider):
 value=key(provider)
 if provider=='assemblyai':url='https://api.assemblyai.com/v2/transcript?limit=1';headers={'authorization':value}
 elif provider=='elevenlabs':url='https://api.elevenlabs.io/v1/user';headers={'xi-api-key':value}
 elif provider=='gemini':
  from .gemini_config import MODEL,BASE_URL
  url=BASE_URL+MODEL;headers={'x-goog-api-key':value}
 else:raise ValueError('O teste de conexão não está disponível para este serviço.')
 try:response=requests.get(url,headers=headers,timeout=(5,15))
 except requests.RequestException:raise ValueError('Não foi possível conectar ao serviço. Confira a internet e tente novamente.') from None
 if response.status_code in (401,403):raise ValueError('A chave foi recusada ou não tem permissão para consultar a conta.')
 if provider=='gemini' and response.status_code==404:
  from .gemini_config import unavailable
  raise ValueError(unavailable())
 if not response.ok:raise ValueError('O serviço respondeu HTTP '+str(response.status_code)+'. Tente novamente mais tarde.')
 return {'ok':True,'mensagem':'Chave aceita e modelo localizado. Isso não confirma acesso à geração: disponibilidade, cota e faturamento dependem do projeto no Google. Nenhum texto foi gerado.' if provider=='gemini' else 'Conexão confirmada. Nenhuma transcrição ou fala foi gerada.'}
