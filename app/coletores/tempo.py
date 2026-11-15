"""Previsão do tempo (15/11/2026): Open-Meteo (https://open-meteo.com, dados sob CC BY 4.0, sem chave de acesso).

O ponto consultado é o centro do município informado pelo IBGE (API de malhas, pelo código IBGE do órgão), guardado
em `dados_publicos` para não repetir a consulta. Nada é específico de um órgão: Prefeitura e Câmara do mesmo município
usam a mesma previsão. Fonte fora do ar = o portal esconde o quadro (nunca mostra previsão velha como atual)."""
from .comum import buscar, guardar_publico
from .. import db

URL = 'https://api.open-meteo.com/v1/forecast'
URL_IBGE = 'https://servicodados.ibge.gov.br/api/v3/malhas/municipios/{ibge}/metadados'
DIAS = 4
FRESCA_MIN = 45  # Prefeitura e Câmara do mesmo município: a segunda coleta dentro deste prazo não consulta de novo

def coordenadas(ibge, p=None):
    """(lat, lon) do município: o informado na fonte (params lat/lon) ou o centróide do IBGE (guardado)."""
    p = p or {}
    try:
        if p.get('lat') not in (None, '') and p.get('lon') not in (None, ''):
            return float(p['lat']), float(p['lon'])
    except (TypeError, ValueError):
        pass
    r = db.um(db.LOCAL, "SELECT payload FROM dados_publicos WHERE ibge=%s AND fonte='ibge_centroide' AND chave='centroide'", (str(ibge),))
    if r and r['payload'].get('lat') is not None:
        return r['payload']['lat'], r['payload']['lon']
    d = buscar('tempo', URL_IBGE.format(ibge=ibge), tentativas=2, timeout=30)
    c = (d[0] if isinstance(d, list) and d else {}).get('centroide') or {}
    if c.get('latitude') is None:
        raise ValueError('o IBGE não informou o centro do município')
    lat, lon = round(float(c['latitude']), 4), round(float(c['longitude']), 4)
    guardar_publico(str(ibge), 'ibge_centroide', 'centroide', {'lat': lat, 'lon': lon})
    return lat, lon

def interpretar(d):
    """Resposta do Open-Meteo -> payload guardado (só números e códigos; o texto é montado na exibição)."""
    cur, dia = d.get('current') or {}, d.get('daily') or {}
    datas = dia.get('time') or []
    def col(k, i):
        v = dia.get(k) or []
        return v[i] if i < len(v) else None
    dias = [{'data': datas[i], 'max': col('temperature_2m_max', i), 'min': col('temperature_2m_min', i), 'codigo': col('weather_code', i),
             'chuva_prob': col('precipitation_probability_max', i), 'chuva_mm': col('precipitation_sum', i)} for i in range(len(datas))]
    if not dias or cur.get('temperature_2m') is None:
        raise ValueError('resposta sem previsão')
    return {'atual': {'hora': cur.get('time'), 'temp': cur.get('temperature_2m'), 'codigo': cur.get('weather_code'), 'umidade': cur.get('relative_humidity_2m'),
                      'vento': cur.get('wind_speed_10m'), 'dia': cur.get('is_day')},
            'dias': dias, 'fonte': 'Open-Meteo', 'licenca': 'CC BY 4.0'}

def coletar(o, p, agora=None):
    ibge = str((p or {}).get('ibge') or o.get('ibge') or '')
    if not ibge:
        return [('previsao', False, 0, 'órgão sem código IBGE')]
    if db.ENSAIO.get() is None:
        r = db.um(db.LOCAL, f"SELECT 1 FROM dados_publicos WHERE ibge=%s AND fonte='tempo' AND chave='previsao' AND coletado_em > now() - interval '{FRESCA_MIN} minutes'", (ibge,))
        if r:
            return [('previsao', True, 0, 'previsão já atualizada nesta hora (mesmo município)')]
    lat, lon = coordenadas(ibge, p)
    d = buscar('tempo', URL, {'latitude': lat, 'longitude': lon, 'timezone': 'America/Sao_Paulo', 'forecast_days': DIAS,
                              'current': 'temperature_2m,weather_code,relative_humidity_2m,wind_speed_10m,is_day',
                              'daily': 'temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max,precipitation_sum'},
               tentativas=2, timeout=30)
    payload = interpretar(d)
    payload.update(lat=lat, lon=lon)
    guardar_publico(ibge, 'tempo', 'previsao', payload)  # no ensaio a escrita é pulada (db.ENSAIO)
    return [('previsao', True, len(payload['dias']), f"{payload['atual']['temp']} °C agora; {len(payload['dias'])} dia(s) de previsão")]
