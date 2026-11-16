"""Geração da edição do Diário Oficial (Lei 910/2026 e decreto de 25/03/2026).

- capa conforme a Lei 910, art. 6º (brasão, título, lei de instituição, data, número, responsável) e miolo em 2 colunas: diario_layout.py;
- página onde cada ato começa (retorno da remessa da Câmara);
- MODO TESTE: marca d'água "EDIÇÃO TESTE — NÃO HOMOLOGADA — SEM VALIDADE" em todas as páginas (LEGENDA_TESTE);
- PDF/A-2b para arquivo permanente (Lei 910, art. 8º; decreto, art. 5º, VI), convertido ANTES de assinar;
- calendário: sem edição em fins de semana, feriados e dias sem expediente; ponto facultativo conta como dia útil; corte no horário do órgão (padrão 16h).
"""
import hashlib, shutil, subprocess, tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from . import config, db

# Edições de TESTE (16/11/2026): podem aparecer no portal, sempre com esta legenda (no portal e no PDF), para o órgão ver como fica.
# Nunca são apresentadas como oficiais; ao passar para DIARIO_MODO=oficial, são apagadas (diario_servico.limpar_teste).
LEGENDA_TESTE = 'Edição teste — não homologada — sem validade'

def mostrar_teste(banco) -> bool:
    """Opção do órgão (Diário Oficial → Signatários, calendário e lei): mostrar no portal as edições de teste, com a legenda. Padrão: sim."""
    return bool((db.cfg(banco, 'diario', {}) or {}).get('mostrar_teste', True))

LEI_PADRAO = 'lei municipal'  # o órgão informa a lei em Diário Oficial → Signatários, calendário e lei

# ---------- calendário ----------
def dia_util(b, d: date) -> bool:
    if d.weekday() >= 5:
        return False
    f = db.um(b, 'SELECT tipo FROM feriados WHERE data=%s', (d,))
    return not f or f['tipo'] == 'ponto_facultativo'

def proximo_dia_util(b, d: date) -> date:
    d = d + timedelta(days=1)
    while not dia_util(b, d):
        d += timedelta(days=1)
    return d

# ---------- regras do órgão (etapa 3 do modelo multi-órgão): lei, decreto e horários ----------
# Sem configuração própria, valem os horários do .env (padrão 16h, 16h30 e 17h), os mesmos de antes.
HORARIOS = ('corte', 'alerta', 'publicacao')

def _padrao():
    return {'corte': f'{config.DIARIO_CORTE_HORA:02d}:00', 'alerta': config.DIARIO_ALERTA, 'publicacao': f'{config.DIARIO_PUBLICACAO_HORA:02d}:00'}

def _hora(txt):
    h, m = txt.split(':')
    return time(int(h), int(m))

def hora_txt(txt):
    """'16:00' → '16h'; '16:30' → '16h30'."""
    h, m = txt.split(':')
    return f'{int(h)}h' + ('' if m == '00' else m)

def regras(b):
    """Regras do Diário do órgão: lei, decreto, base legal e horários (corte do envio, alerta de assinatura, publicação automática)."""
    conf = db.cfg(b, 'diario', {}) or {}
    pad = _padrao()
    r = {k: conf.get(k) or pad[k] for k in HORARIOS}
    r.update({f't_{k}': _hora(r[k]) for k in HORARIOS})
    r.update({f'{k}_txt': hora_txt(r[k]) for k in HORARIOS})
    r.update(lei=conf.get('lei', ''), decreto=conf.get('decreto', ''), base_legal=conf.get('base_legal', ''), proprios=any(conf.get(k) for k in HORARIOS), padrao=pad)
    return r

def validar_regras(f):
    """Lê o formulário de lei, decreto e horários. Devolve (valores, erros)."""
    erros, v = [], {}
    for k, rot in (('corte', 'Corte do envio'), ('alerta', 'Alerta de assinatura'), ('publicacao', 'Publicação automática')):
        t = (f.get(k) or '').strip()
        try:
            v[k] = _hora(t).strftime('%H:%M')
        except (ValueError, AttributeError):
            erros.append(f'{rot}: use o formato HH:MM.')
    if not erros:
        c, a, p = (_hora(v[k]) for k in HORARIOS)
        if not (time(6, 0) <= c < a < p <= time(23, 0)):
            erros.append('Os horários precisam estar nesta ordem, entre 6h e 23h: corte do envio, depois o alerta de assinatura, depois a publicação automática.')
    v.update(lei=(f.get('lei') or '').strip()[:200], decreto=(f.get('decreto') or '').strip()[:200], base_legal=(f.get('base_legal') or '').strip()[:600])
    return v, erros

def base_legal(r, generica):
    """Base legal do Diário do órgão: a informada; ou montada com a lei e o decreto; ou a genérica."""
    if r['base_legal']:
        return r['base_legal']
    if r['lei'] or r['decreto']:
        return '; '.join(x for x in (r['lei'], r['decreto']) if x) + '; MP 2.200-2/2001 (ICP-Brasil); Lei 14.063/2020.'
    return generica

def data_alvo(b, agora: datetime) -> date:
    """Ato enviado até o corte do órgão (padrão 16h) de um dia útil vai para a edição do dia; depois do corte, para o próximo dia útil."""
    d = agora.date()
    if dia_util(b, d) and agora.time() < regras(b)['t_corte']:
        return d
    return proximo_dia_util(b, d)

# ---------- PDF ----------
def _esc(s):
    return (s or '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

def codigo_verificacao(edicao, n_atos):
    numero = f"{edicao['numero']}{edicao['letra']}"
    pre = hashlib.sha256(f"{numero}|{edicao['data'].isoformat()}|{n_atos}|{edicao.get('id')}|{config.SECRET_KEY}".encode()).hexdigest().upper()
    return f'{pre[:4]}-{pre[4:8]}-{pre[8:12]}'

def gerar_pdf(edicao: dict, atos: list[dict], ident: dict, destino_dir: str, teste: bool = False, brasao: str | None = None, lei: str | None = None,
              orgao: dict | None = None, ano_inicio: int | None = None) -> tuple[str, str, str, dict]:
    """Gera o PDF (capa nova + miolo em 2 colunas, diario_layout.py) e devolve (caminho, sha256, código, {ato_id: página})."""
    from . import diario_layout as L
    Path(destino_dir).mkdir(parents=True, exist_ok=True)
    numero = f"{edicao['numero']}{edicao['letra']}"
    codigo = codigo_verificacao(edicao, len(atos))
    caminho = str(Path(destino_dir) / f"diario-{edicao['data'].isoformat()}-{numero}{'-TESTE' if teste else ''}.pdf")
    o = orgao or {}
    mun_txt = o.get('municipio') or ''
    uf = mun_txt[mun_txt.rfind('(') + 1:mun_txt.rfind(')')] if '(' in mun_txt else ''
    inst = [ident.get('nome') or o.get('nome') or '', ident.get('endereco') or '']
    if ident.get('cnpj'):
        inst.append(f"CNPJ {ident['cnpj']}")
    meta = {'municipio': ident.get('nome_curto') or (mun_txt.split(' (')[0] if mun_txt else 'do Município'), 'uf': uf,
            'entidade': ident.get('nome') or o.get('nome') or '', 'lei': lei or LEI_PADRAO, 'dominio': ident.get('dominio') or o.get('dominio') or '',
            'cor': ident.get('cor') or o.get('cor'), 'ano_inicio': ano_inicio, 'teste': teste, 'codigo': codigo, 'legenda_teste': LEGENDA_TESTE,
            'brasao': brasao, 'institucional': ' · '.join(x for x in inst if x)}
    paginas, _, _ = L.gerar(caminho, edicao, atos, ident, meta)
    sha = hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    return caminho, sha, codigo, paginas

def para_pdfa(caminho: str) -> bool:
    """Converte para PDF/A-2b com o Ghostscript (antes de assinar: assinar depois mantém a assinatura válida).
    Devolve False (e mantém o original) se o Ghostscript ou o perfil de cor não estiverem disponíveis."""
    gs = shutil.which('gs')
    icc = next(iter(sorted(Path('/usr/share/ghostscript').glob('*/iccprofiles/srgb.icc'))), None) if Path('/usr/share/ghostscript').is_dir() else None
    if not gs or not icc:
        return False
    with tempfile.TemporaryDirectory() as tmp:
        defs = Path(tmp) / 'PDFA_def.ps'
        defs.write_text(f"""%!
/ICCProfile ({icc}) def
[/_objdef {{icc_PDFA}} /type /stream /OBJ pdfmark
[{{icc_PDFA}} << /N 3 >> /PUT pdfmark
[{{icc_PDFA}} ICCProfile (r) file /PUT pdfmark
[/_objdef {{OutputIntent_PDFA}} /type /dict /OBJ pdfmark
[{{OutputIntent_PDFA}} << /Type /OutputIntent /S /GTS_PDFA1 /DestOutputProfile {{icc_PDFA}} /OutputConditionIdentifier (sRGB) >> /PUT pdfmark
[{{Catalog}} << /OutputIntents [ {{OutputIntent_PDFA}} ] >> /PUT pdfmark
""")
        saida = Path(tmp) / 'saida.pdf'
        r = subprocess.run([gs, '-dPDFA=2', '-dBATCH', '-dNOPAUSE', '-dNOOUTERSAVE', '-dQUIET', '-sColorConversionStrategy=RGB', '-sProcessColorModel=DeviceRGB',
                            '-sDEVICE=pdfwrite', '-dPDFACompatibilityPolicy=1', f'--permit-file-read={icc}', f'-sOutputFile={saida}', str(defs), caminho],
                           capture_output=True, timeout=120)
        if r.returncode != 0 or not saida.is_file() or saida.stat().st_size < 1000:
            return False
        shutil.copyfile(saida, caminho)
    return True
