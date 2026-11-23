# Ripagem Maker 3.0.5

- Cobertura automática com potes somente a partir da primeira menção literal ao produto ou aos aliases configurados, na transcrição disponível.
- Trechos anteriores ficam apenas marcados para adaptação visual do modo de uso; os áudios aprovados permanecem na montagem.
- Janelas que cruzam a primeira menção são divididas nesse limite. O XML recebe os marcadores ADAPTAR MODO DE USO antes dele.
- Se a primeira menção não for localizada, o app informa isso e não aplica potes automaticamente. Transcrições parciais limitam a detecção ao trecho disponível.
- Depois do limite, falas sem quantidade continuam sorteando os takes de produto entre kits; quantidades explícitas mantêm seu kit.
- Planos preparados com a regra anterior precisam ser preparados novamente. Chaves e materiais são preservados.
