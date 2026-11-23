"""Modelo único, explícito e com faixa gratuita; nunca faz fallback pago."""
MODEL='gemini-3.5-flash-lite'
MODEL_LABEL='Gemini 3.5 Flash-Lite'
BASE_URL='https://generativelanguage.googleapis.com/v1beta/models/'
def unavailable():
 return 'O modelo '+MODEL+' não está disponível para esta chave/projeto do Google (HTTP 404). Confira o projeto em Ajustes → Integrações e APIs. Nenhum texto foi alterado.'
