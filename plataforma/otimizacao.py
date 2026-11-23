"""Otimização de valores dos kits: o mesmo fluxo da troca, partindo da VSL finalizada.

O modo é exclusivo: somente preços e quantidades dos kits entram na lista.
Nomes de produto preenchidos na entrega não alteram este escopo.
"""
import json
from pathlib import Path

from . import trocas as T


def path(out): return Path(out) / 'otimizacao.json'


def active(out): return path(out).exists() and json.loads(path(out).read_text()).get('ativo', False)


def same_product(out):
    """Sem produto novo (ou igual ao atual): a otimização só muda valores."""
    for file in Path(out).glob('frases_*.json'):
        data = json.loads(file.read_text())
        new = str(data.get('produto_novo') or '').strip().casefold()
        if new and new != str(data.get('produto', '')).strip().casefold():
            return False
    return True


def state(out, body=None):
    if body and 'ativar' in body:
        # Só true/false: um valor qualquer não pode ligar a otimização e refazer a lista só com preços.
        if not isinstance(body['ativar'], bool):
            raise ValueError('Escolha ligar ou desligar a otimização.')
        if body['ativar']:
            T.write(path(out), {'ativo': True})
        elif path(out).exists():
            path(out).unlink()
    on = active(out)
    return {'ativo': on, 'somente_valores': on, 'precos_preparados': (Path(out) / 'precos_TROCA.json').exists()}


def prepare(out, product):
    """Store scope and metadata without detecting or cutting product-name mentions."""
    state(out, {'ativar': True})
    T.write(Path(out)/'frases_OTIMIZACAO.json', {
        'produto': product, 'produto_novo': product, 'produto_aliases': '',
        'frases': [], 'resumo': 'Somente preços e kits. Informe os valores novos na etapa Falas.'})
