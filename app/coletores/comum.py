"""Peças comuns dos coletores: HTTP respeitoso, conversões, LGPD, upsert e registro de coletas."""
import hashlib, json, re, time
from datetime import date, datetime
import httpx
from psycopg.types.json import Jsonb
from .. import db

# ---------- HTTP: no máximo 1 requisição por segundo por fonte, timeout e novas tentativas com espera ----------
_ultimo: dict[str, float] = {}
INTERVALO = 1.0

def buscar(fonte: str, url: str, params=None, headers=None, tentativas=3, timeout=120):
    """GET com intervalo mínimo por fonte. Devolve o JSON (ou levanta a última exceção)."""
    erro = None
    for i in range(tentativas):
        espera = INTERVALO - (time.monotonic() - _ultimo.get(fonte, 0))
        if espera > 0:
            time.sleep(espera)
        _ultimo[fonte] = time.monotonic()
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers={'User-Agent': 'PortaisBora-coletor/1.0', 'Accept': 'application/json', **(headers or {})}) as c:
                r = c.get(url, params=params)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError) as e:
            erro = e
            time.sleep(3 * (i + 1))
    raise erro

# ---------- conversões ----------
def num(v):
    """'26574852,37' → 26574852.37; '1.234,5' → 1234.5; '' → None."""
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip()
    if not s:
        return None
    if ',' in s:
        s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None

def data_br(v):
    """'30/01/2026 00:00:00' ou '2026-01-30T..' → date."""
    s = str(v or '').strip()
    m = re.match(r'(\d{2})/(\d{2})/(\d{4})', s)
    if m:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    m = re.match(r'(\d{4})-(\d{2})-(\d{2})', s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None

def txt(v, n=500):
    return re.sub(r'\s+', ' ', str(v or '')).strip()[:n]

# ---------- LGPD ----------
CPF = re.compile(r'\b\d{3}\.?[\dXx*]{3}\.?[\dXx*]{3}-?\d{2}\b')
CPF_PURO = re.compile(r'^\D*\d{3}\D?\d{3}\D?\d{3}\D?\d{2}\D*$')
CNPJ = re.compile(r'^\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}$')

def sem_cpf(nome: str) -> str:
    """Remove dígitos de CPF que venham no nome (ex.: MEI 'NOME 09630942895')."""
    s = CPF.sub('', str(nome or ''))
    return re.sub(r'\s{2,}', ' ', s).strip(' -·')

def doc_pj(doc: str) -> str:
    """Só guarda documento de pessoa jurídica (CNPJ). CPF nunca é guardado."""
    d = str(doc or '').strip()
    return d if CNPJ.match(d) else ''

def eh_pessoa_fisica(doc: str) -> bool:
    return bool(doc and CPF_PURO.match(str(doc)) and not CNPJ.match(str(doc)))

# ---------- gravação ----------
def chave(*partes) -> str:
    return hashlib.sha1('|'.join(str(p) for p in partes).encode()).hexdigest()

def chaves_unicas(linhas):
    """Garante chaves distintas no lote (linhas idênticas na fonte viram #2, #3...)."""
    vistos = {}
    for l in linhas:
        k = l['chave']
        if k in vistos:
            vistos[k] += 1
            l['chave'] = f'{k}#{vistos[k]}'
        else:
            vistos[k] = 1
    return linhas

def gravar(banco: str, tabela: str, linhas: list[dict], substituir: dict | None = None, fonte: str = '') -> int:
    """Upsert pela chave natural. Se `substituir` (ex.: {'ano': 2026}) for dado e a coleta trouxe linhas,
    apaga as linhas antigas desse recorte que não vieram nesta coleta (anulações e correções na fonte)."""
    if not linhas:
        return 0
    chaves_unicas(linhas)
    cols = list(linhas[0].keys())
    sets = ', '.join(f'{c}=EXCLUDED.{c}' for c in cols if c != 'chave')
    sql = f"INSERT INTO {tabela} ({', '.join(cols)}, coletado_em) VALUES ({', '.join(['%s'] * len(cols))}, now()) ON CONFLICT (chave) DO UPDATE SET {sets}, coletado_em=now()"
    with db.conn(banco) as c:
        with c.transaction():
            inicio = c.execute('SELECT now() t').fetchone()['t']
            with c.cursor() as cur:
                cur.executemany(sql, [tuple(l[k] for k in cols) for l in linhas])
            if substituir:
                cond = ' AND '.join(f'{k}=%s' for k in substituir)
                extra = ' AND fonte=%s' if fonte else ''
                c.execute(f'DELETE FROM {tabela} WHERE {cond}{extra} AND coletado_em < %s', tuple(substituir.values()) + ((fonte,) if fonte else ()) + (inicio,))
    return len(linhas)

def registrar(orgao_slug, fonte, ok, n, msg, inicio=None):
    db.exe(db.PLATAFORMA, 'INSERT INTO coletas (orgao_slug, fonte, inicio, fim, ok, registros, mensagem) VALUES (%s,%s,coalesce(%s, now()),now(),%s,%s,%s)',
           (orgao_slug, fonte, inicio, ok, n, (msg or '')[:500]))

def guardar_publico(ibge, fonte, chave_, payload):
    db.exe(db.PLATAFORMA, "INSERT INTO dados_publicos (ibge, fonte, chave, payload, coletado_em) VALUES (%s,%s,%s,%s,now()) ON CONFLICT (ibge, fonte, chave) DO UPDATE SET payload=EXCLUDED.payload, coletado_em=now()",
           (ibge, fonte, str(chave_), Jsonb(payload)))

def agora():
    return datetime.now()
