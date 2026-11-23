"""Monetary amounts, including the spoken English forms returned by ASR."""
import re
from decimal import Decimal
ONES=dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen'.split(),range(20)))
TENS=dict(zip('twenty thirty forty fifty sixty seventy eighty ninety'.split(),range(20,100,10)))
TOKENS='|'.join(sorted([*ONES,*TENS,'hundred','thousand'],key=len,reverse=True))
SPOKEN_PATTERN=r'\b(?P<spoken>(?:'+TOKENS+r')(?:(?:[ -]+and)?[ -]+(?:'+TOKENS+r')){0,9})\s+(?P<spoken_currency>dollars?|bucks|USD)\b'

def spoken_number(text):
    total=current=0
    for word in re.split(r'[\s-]+',text.lower()):
        if word=='and':continue
        if word in ONES:current+=ONES[word]
        elif word in TENS:current+=TENS[word]
        elif word=='hundred':current*=100
        elif word=='thousand':total+=current*1000;current=0
        else:raise ValueError('Número por extenso não reconhecido.')
    return str(total+current)

NUMERIC_PATTERN=(r'(?P<brl>R\$)\s*(?P<brl_int>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<brl_cent>\d{1,2}))?(?!\d|,\d)'
                 r'|(?P<cur>US\$|(?<![\w])\$)\s*(?P<int>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<cent>\d{1,2}))?(?!\d|[.,]\d)'
                 r'|(?P<brl_int2>\d{1,3}(?:\.\d{3})+|\d+)(?:,(?P<brl_cent2>\d{1,2}))?\s*(?P<brl_word>reais)\b'
                 r'|(?P<int2>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<cent2>\d{1,2}))?\s*(?P<word>dollars?|bucks|USD)\b')
RX_PRICE=re.compile(NUMERIC_PATTERN+'|'+SPOKEN_PATTERN,re.I)

def price_key(match):
    if match.group('spoken'):return spoken_number(match.group('spoken'))
    if match.group('brl_int') or match.group('brl_int2'):
        integer=(match.group('brl_int') or match.group('brl_int2')).replace('.','')
        cents=match.group('brl_cent') or match.group('brl_cent2')
    else:
        integer=(match.group('int') or match.group('int2')).replace(',','')
        cents=match.group('cent') or match.group('cent2')
    return f"{int(integer)}.{cents.ljust(2,'0')}" if cents and int(cents) else str(int(integer))


INPUT_AMOUNT_VALUE = (
    r'[0-9]{1,3}(?:\.[0-9]{3}){1,2}(?:,[0-9]{1,2})?'
    r'|[0-9]{1,3}(?:,[0-9]{3}){1,2}(?:\.[0-9]{1,2})?'
    r'|[0-9]{1,7}(?:[.,][0-9]{1,2})?'
)
INPUT_AMOUNT_PATTERN = rf'(?:(?:US\$|R\$|\$)\s*)?(?:{INPUT_AMOUNT_VALUE})'
INPUT_AMOUNT = re.compile(rf'(?:(?P<symbol>US\$|R\$|\$)\s*)?(?P<value>{INPUT_AMOUNT_VALUE})', re.I)

def input_amount(value):
    match=INPUT_AMOUNT.fullmatch(str(value).strip())
    if not match:
        raise ValueError('Informe um preço positivo com até duas casas decimais, como $59 ou R$ 59,90.')
    amount = match['value']
    last_separator = max(amount.rfind('.'), amount.rfind(','))
    digits = amount.replace('.', '').replace(',', '')
    decimal_places = len(amount) - last_separator - 1 if last_separator >= 0 else 0
    # A validação já distingue centavos de grupos de três dígitos.
    number = Decimal(digits).scaleb(-decimal_places if decimal_places in (1, 2) else 0)
    if not 0<number<=1000000:
        raise ValueError('Informe um preço entre 0,01 e 1.000.000.')
    symbol=match['symbol']
    return format(number.normalize(),'f'),('R$' if symbol and symbol.upper()=='R$' else '$' if symbol else None)

def currency(match):
    label=(match.group('brl') or match.group('brl_word') or match.group('cur') or match.group('word') or match.group('spoken_currency') or '').upper()
    return 'R$' if label in ('R$','REAIS') else '$'

def format_amount(value,symbol):
    if '.' in value:
        whole,cents=value.split('.')
        return whole+(',' if symbol=='R$' else '.')+cents.ljust(2,'0')
    return value
