"""Coletor do Siconfi (Tesouro Nacional): RGF do Poder Legislativo de Borá."""
from datetime import date
import httpx
from psycopg.types.json import Jsonb
from .. import db

API = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/'

def coletar_rgf_camara():
    ano = date.today().year
    with httpx.Client(timeout=60) as c:
        r = c.get(API + 'extrato_entregas', params={'id_ente': '3507209', 'an_referencia': ano})
        r.raise_for_status()
        itens = r.json().get('items', [])
    rgf_l = [i for i in itens if 'RGF' in (i.get('entregavel') or '') and (i.get('co_poder') or '') in ('L', '')]
    db.exe(db.PLATAFORMA, "INSERT INTO dados_publicos (ibge, fonte, chave, payload, coletado_em) VALUES ('3507209','siconfi_entregas',%s,%s,now()) ON CONFLICT (ibge, fonte, chave) DO UPDATE SET payload=EXCLUDED.payload, coletado_em=now()", (str(ano), Jsonb(itens)))
    return ('cm-bora', len(rgf_l), f'{len(itens)} entregas do município; {len(rgf_l)} de RGF')
