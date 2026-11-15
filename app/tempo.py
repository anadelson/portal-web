"""Previsão do tempo no portal (15/11/2026): lê o que o coletor `tempo` guardou (Open-Meteo) e prepara para exibir.
Previsão com mais de VALIDADE_H horas não aparece (o quadro some em vez de mostrar dado velho como atual)."""
from datetime import date, datetime, timedelta
from . import config, db

VALIDADE_H = 6
DIAS_SEMANA = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
DIAS_LONGOS = ['segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado', 'domingo']

# código WMO (Open-Meteo) -> (descrição, ícone)
def condicao(codigo, dia=True):
    c = int(codigo) if codigo is not None else -1
    if c == 0:
        return ('Céu limpo', 'sol' if dia else 'lua')
    if c == 1:
        return ('Predomínio de sol', 'sol_nuvem' if dia else 'lua')
    if c == 2:
        return ('Parcialmente nublado', 'sol_nuvem')
    if c == 3:
        return ('Nublado', 'nuvem')
    if c in (45, 48):
        return ('Nevoeiro', 'nevoeiro')
    if c in (51, 53, 55, 56, 57):
        return ('Garoa', 'garoa')
    if c == 61:
        return ('Chuva fraca', 'chuva')
    if c in (63, 66):
        return ('Chuva moderada', 'chuva')
    if c in (65, 67):
        return ('Chuva forte', 'chuva')
    if c in (71, 73, 75, 77, 85, 86):
        return ('Neve', 'nuvem')
    if c == 80:
        return ('Pancadas de chuva fracas', 'chuva')
    if c == 81:
        return ('Pancadas de chuva', 'chuva')
    if c == 82:
        return ('Pancadas de chuva fortes', 'chuva')
    if c == 95:
        return ('Trovoadas', 'tempestade')
    if c in (96, 99):
        return ('Trovoadas com granizo', 'tempestade')
    return ('Condição não informada', 'nuvem')

def _n(v):
    return None if v is None else int(round(float(v)))

def previsao(ibge, agora=None):
    """Dicionário pronto para o template, ou None (sem coleta, coleta velha ou órgão sem IBGE)."""
    if not ibge:
        return None
    try:
        r = db.um(db.LOCAL, "SELECT payload, coletado_em FROM dados_publicos WHERE ibge=%s AND fonte='tempo' AND chave='previsao'", (str(ibge),))
    except Exception:
        return None
    if not r:
        return None
    agora = (agora or datetime.now()).astimezone()  # validade pelo relógio real (a coleta também é real)
    col = r['coletado_em']
    if agora - col > timedelta(hours=VALIDADE_H):
        return None
    p = r['payload']
    hoje = agora.date()
    dias = []
    for d in p.get('dias', []):
        try:
            dt = date.fromisoformat(d['data'])
        except (KeyError, ValueError):
            continue
        if dt < hoje:
            continue
        txt, ic = condicao(d.get('codigo'))
        rot = 'Hoje' if dt == hoje else ('Amanhã' if dt == hoje + timedelta(days=1) else DIAS_SEMANA[dt.weekday()])
        dias.append({'data': dt, 'rotulo': rot, 'longo': DIAS_LONGOS[dt.weekday()], 'max': _n(d.get('max')), 'min': _n(d.get('min')), 'texto': txt, 'icone': ic,
                     'chuva_prob': _n(d.get('chuva_prob')), 'chuva_mm': d.get('chuva_mm')})
    if not dias:
        return None
    a = p.get('atual') or {}
    txt, ic = condicao(a.get('codigo'), bool(a.get('dia', 1)))
    loc = col.astimezone() if col.tzinfo else col
    return {'temp': _n(a.get('temp')), 'texto': txt, 'icone': ic, 'umidade': _n(a.get('umidade')), 'vento': _n(a.get('vento')),
            'dias': dias, 'atualizado': loc.strftime('%d/%m/%Y, %Hh%M'), 'fonte': p.get('fonte', 'Open-Meteo'), 'licenca': p.get('licenca', 'CC BY 4.0')}
