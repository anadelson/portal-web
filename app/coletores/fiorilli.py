"""Coletor do sistema contábil da Prefeitura (Fiorilli, API pública VersaoJson).

Atualiza, no banco da Câmara, o valor pago nos empenhos de cada emenda impositiva
(a Câmara lê a Prefeitura pela API pública, nunca pelo banco).
ATENÇÃO: a listagem exata do cadastro de emendas deve ser validada na VPS (ver README, Fase 3)."""
from datetime import date
import httpx
from psycopg.types.json import Jsonb
from .. import db

BASE = 'https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/'

def _get(caminho, params):
    with httpx.Client(timeout=60, verify=True) as c:
        r = c.get(BASE + caminho, params=params)
        r.raise_for_status()
        return r.json()

def coletar_emendas():
    ano = date.today().year
    params = {'Listagem': 'EmendasImpositivasArt166A', 'Empresa': '2', 'MostraDadosConsolidado': 'False', 'ConectarExercicio': str(ano)}
    dados = _get('Transferencias/', params)
    linhas = dados if isinstance(dados, list) else (dados.get('dados') or dados.get('Dados') or [])
    db.exe(db.PLATAFORMA, "INSERT INTO dados_publicos (ibge, fonte, chave, payload, coletado_em) VALUES ('3507209','fiorilli_emendas',%s,%s,now()) ON CONFLICT (ibge, fonte, chave) DO UPDATE SET payload=EXCLUDED.payload, coletado_em=now()", (str(ano), Jsonb(linhas)))
    return ('cm-bora', len(linhas), f'{len(linhas)} linhas guardadas em dados_publicos (mapeamento para a tabela emendas a validar)')
