"""Credenciais persistentes no cofre nativo; nunca em pacotes ou parâmetros de tarefas."""
SERVICE='Ripagem Maker'
def backend():
 try:
  import keyring
  if keyring.get_keyring().priority<1:raise RuntimeError()
  return keyring
 except Exception:raise RuntimeError('O cofre de credenciais não está disponível. Abra o app pelo iniciador atualizado para instalar o componente keyring.') from None

def get(provider):
 try:return backend().get_password(SERVICE,provider)
 except RuntimeError:raise
 except Exception:raise RuntimeError('Não foi possível ler o cofre do sistema. Confira a permissão do Ripagem Maker.') from None

def set(provider,value):
 try:backend().set_password(SERVICE,provider,value)
 except RuntimeError:raise
 except Exception:raise RuntimeError('Não foi possível salvar no cofre do sistema. Nenhuma chave foi gravada em texto simples.') from None

def delete(provider):
 try:
  b=backend()
  if b.get_password(SERVICE,provider) is not None:b.delete_password(SERVICE,provider)
 except RuntimeError:raise
 except Exception:raise RuntimeError('Não foi possível remover a chave do cofre do sistema.') from None
