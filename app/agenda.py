"""Agenda de execução das integrações (10/11/2026): cada órgão escolhe, no painel, os dias, os horários e quantas vezes cada fonte roda.

Formato guardado em `fontes.agenda` (JSONB; NULL = padrão do sistema, igual ao que já rodava):
  {"modo": "horarios",  "dias": [0..6], "horarios": ["06:00", "18:30"]}
  {"modo": "intervalo", "dias": [0..6], "cada_min": 360, "inicio": 7, "fim": 20}   # fim exclusivo, 1..24
Dias seguem o Python: 0 = segunda … 6 = domingo.
Cada fonte tem um intervalo MÍNIMO entre execuções, para não sobrecarregar os sistemas de onde os dados vêm."""
from datetime import datetime, timedelta

DIAS = ['Seg', 'Ter', 'Qua', 'Qui', 'Sex', 'Sáb', 'Dom']
DIAS_LONGOS = ['segunda', 'terça', 'quarta', 'quinta', 'sexta', 'sábado', 'domingo']
TODOS = list(range(7))

# padrão do sistema (o mesmo que o worker usava fixo no código): fonte -> (a cada N minutos, hora inicial, hora final exclusiva)
PADRAO = {'fiorilli': (60, 7, 20), 'govbr': (180, 6, 22), 'pncp': (360, 0, 24), 'siconfi': (24 * 60, 0, 24), 'tcesp': (24 * 60, 0, 24),
          'ibge': (7 * 24 * 60, 2, 6), 'cnes': (7 * 24 * 60, 2, 6), 'mds': (7 * 24 * 60, 2, 6), 'pni': (7 * 24 * 60, 2, 6),
          'painel': (60, 7, 20), 'inep': (30 * 24 * 60, 2, 6), 'iegm': (30 * 24 * 60, 2, 6), 'financas': (20 * 60, 1, 5),
          'youtube': (2, 0, 24), 'redes': (6 * 60, 6, 23)}
# intervalo mínimo (minutos) entre execuções que o órgão pode escolher
MINIMO = {'fiorilli': 30, 'govbr': 60, 'painel': 15, 'pncp': 60, 'redes': 60, 'financas': 6 * 60, 'siconfi': 6 * 60, 'tcesp': 6 * 60,
          'ibge': 24 * 60, 'cnes': 24 * 60, 'mds': 24 * 60, 'pni': 24 * 60, 'inep': 24 * 60, 'iegm': 24 * 60}
# fontes com agenda própria (não editável): o YouTube só consulta dentro da janela de cada transmissão agendada
FIXAS = {'youtube': 'automática: a cada 2 minutos só dentro da janela de cada transmissão agendada, e uma varredura por dia'}
MAX_HORARIOS = 24
RECUPERA_MIN = 60  # horário fixo perdido é recuperado até 60 min depois

def padrao(fonte):
    cada, ini, fim = PADRAO.get(fonte, (24 * 60, 0, 24))
    return {'modo': 'intervalo', 'dias': TODOS, 'cada_min': cada, 'inicio': ini, 'fim': fim}

def editavel(fonte):
    return fonte in PADRAO and fonte not in FIXAS

def da_fonte(f):
    """Agenda em vigor para uma linha de `fontes` (a do órgão ou, se não houver, o padrão)."""
    a = (f or {}).get('agenda')
    return a if a and f.get('fonte') not in FIXAS else padrao((f or {}).get('fonte'))

def _hm(txt):
    h, m = txt.split(':')
    h, m = int(h), int(m)
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError
    return h, m

def _txt_min(n):
    if n % (24 * 60) == 0:
        d = n // (24 * 60); return f'{d} dia' + ('s' if d > 1 else '')
    if n % 60 == 0:
        h = n // 60; return f'{h} hora' + ('s' if h > 1 else '')
    return f'{n} minutos'

def validar(fonte, form):
    """Lê o formulário da tela de agenda. Devolve (agenda, erros)."""
    erros = []
    if not editavel(fonte):
        return None, ['A agenda desta fonte é automática e não pode ser alterada.']
    dias = sorted({int(d) for d in form.getlist('dias') if str(d).isdigit() and 0 <= int(d) <= 6}) if hasattr(form, 'getlist') else sorted({int(d) for d in form.get('dias', []) if 0 <= int(d) <= 6})
    if not dias:
        erros.append('Marque pelo menos um dia da semana.')
    minimo = MINIMO.get(fonte, 60)
    modo = form.get('modo')
    if modo == 'horarios':
        brutos = [x.strip() for x in (form.get('horarios') or '').replace(';', ',').split(',') if x.strip()]
        hs = []
        for x in brutos:
            try:
                hs.append(_hm(x))
            except (ValueError, TypeError):
                erros.append(f'Horário “{x}” inválido: use HH:MM (ex.: 06:00).')
        hs = sorted(set(hs))
        if not hs and not any('inválido' in e for e in erros):
            erros.append('Informe pelo menos um horário (ex.: 06:00, 18:00).')
        if len(hs) > MAX_HORARIOS:
            erros.append(f'No máximo {MAX_HORARIOS} horários por dia.')
        mins = [h * 60 + m for h, m in hs]
        gaps = [b - a for a, b in zip(mins, mins[1:])] + ([24 * 60 - mins[-1] + mins[0]] if len(mins) > 1 else [])
        if minimo >= 24 * 60 and len(hs) > 1:
            erros.append(f'Esta fonte roda no máximo uma vez por dia (os dados mudam pouco): informe um só horário.')
        elif gaps and min(gaps) < minimo:
            erros.append(f'Os horários precisam de pelo menos {_txt_min(minimo)} de distância entre si, para não sobrecarregar a fonte.')
        return {'modo': 'horarios', 'dias': dias, 'horarios': [f'{h:02d}:{m:02d}' for h, m in hs]}, erros
    if modo == 'intervalo':
        try:
            n = int(form.get('cada') or 0)
        except ValueError:
            n = 0
        mult = {'min': 1, 'h': 60, 'd': 24 * 60}.get(form.get('unidade'), 0)
        cada = n * mult
        try:
            ini, fim = int(form.get('inicio', 0)), int(form.get('fim', 24))
        except ValueError:
            ini, fim = -1, -1
        if cada <= 0:
            erros.append('Informe de quanto em quanto tempo a integração roda.')
        elif cada < minimo:
            erros.append(f'Esta fonte pode rodar no máximo a cada {_txt_min(minimo)}, para não sobrecarregar a fonte.')
        if cada > 60 * 24 * 60:
            erros.append('O intervalo máximo é de 60 dias.')
        if not (0 <= ini <= 23 and 1 <= fim <= 24 and ini < fim):
            erros.append('A faixa de horário precisa ter início antes do fim (ex.: das 7h às 20h).')
        return {'modo': 'intervalo', 'dias': dias, 'cada_min': cada, 'inicio': ini, 'fim': fim}, erros
    return None, ['Escolha como a integração vai rodar: em horários fixos ou repetindo em intervalo.']

def deve_rodar(ag, agora, ultimo):
    """A fonte deve rodar agora? `ultimo` = início da última coleta (ou None)."""
    if agora.weekday() not in ag.get('dias', TODOS):
        return False
    if ag.get('modo') == 'horarios':
        slots = [agora.replace(hour=int(h[:2]), minute=int(h[3:]), second=0, microsecond=0) for h in ag.get('horarios', [])]
        passados = [s for s in slots if s <= agora]
        if not passados:
            return False
        s = max(passados)
        # recupera um horário perdido só até 60 min depois (ex.: worker reiniciando); fora disso, espera o próximo horário
        return (ultimo is None or ultimo < s) and (agora - s).total_seconds() <= RECUPERA_MIN * 60
    if not (ag.get('inicio', 0) <= agora.hour < ag.get('fim', 24)):
        return False
    return ultimo is None or (agora - ultimo).total_seconds() >= ag.get('cada_min', 60) * 60

def proximas(ag, agora, ultimo=None, n=5, limite_dias=70):
    """Simula as próximas `n` execuções (minuto a minuto, até `limite_dias`)."""
    out, t = [], agora.replace(second=0, microsecond=0)
    fim = t + timedelta(days=limite_dias)
    passo = timedelta(minutes=1)
    while t <= fim and len(out) < n:
        if deve_rodar(ag, t, ultimo):
            out.append(t); ultimo = t
        t += passo
    return out

def vezes_por_dia(ag):
    if ag.get('modo') == 'horarios':
        return len(ag.get('horarios', []))
    janela = (ag.get('fim', 24) - ag.get('inicio', 0)) * 60
    cada = ag.get('cada_min', 60)
    return max(1, -(-janela // cada)) if cada <= janela else 0  # 0 = menos de uma por dia

def descrever(ag):
    d = ag.get('dias', TODOS)
    dias = 'todos os dias' if d == TODOS else ('de segunda a sexta' if d == [0, 1, 2, 3, 4] else ', '.join(DIAS_LONGOS[i] for i in d))
    if ag.get('modo') == 'horarios':
        return f"{dias}, às {', '.join(ag.get('horarios', []))}"
    cada = ag.get('cada_min', 60)
    faixa = '' if (ag.get('inicio', 0), ag.get('fim', 24)) == (0, 24) else f", entre {ag.get('inicio')}h e {ag.get('fim')}h"
    return f'{dias}, a cada {_txt_min(cada)}{faixa}'
