"""Busca no portal antigo do próprio órgão (24/11/2026).

O endereço é cadastrado no painel (Dados antigos › Portal antigo); a varredura roda no worker, aos poucos, e guarda textos,
fotos e arquivos numa ÁREA DE REVISÃO. Só a confirmação de quem revisa cria RASCUNHOS na seção certa (notícia, página,
álbum, comunicado com anexo, documento da sessão ou da proposição). Nada é publicado sozinho.

Cuidados (valem para qualquer órgão; nada de endereço fixo no código):
- só o domínio informado e os subdomínios dele; só endereços públicos da internet (nada de IP interno, localhost ou portas
  estranhas), conferidos também em cada redirecionamento;
- robots.txt respeitado (inclusive o Crawl-delay, até 10 s); no mínimo 1 s entre pedidos;
- sem login, sem formulário, sem contornar captcha ou bloqueio: página que pede senha ou recusa o acesso fica de fora;
- limites de páginas, de tamanho por arquivo e de disco; CPF mascarado no texto; avisos de dado pessoal para quem revisa.
"""
import hashlib, html as H, ipaddress, re, shutil, socket, time, unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from urllib.robotparser import RobotFileParser
import httpx
from psycopg.types.json import Jsonb
from . import config, db

ASSUNTOS = {'tudo': 'Tudo o que for encontrado', 'noticias': 'Notícias', 'paginas': 'Páginas institucionais', 'sessoes': 'Sessões, pautas e atas',
            'proposicoes': 'Proposições, leis e atos', 'documentos': 'Documentos e arquivos (PDF, DOCX…)', 'fotos': 'Fotos e álbuns'}
DESTINOS = {'noticia': 'Notícia (rascunho)', 'pagina': 'Página (rascunho)', 'album': 'Álbum de fotos (não publicado)', 'comunicado': 'Comunicado com anexo (rascunho)',
            'sessao': 'Documento de uma sessão', 'proposicao': 'Documento de uma proposição',
            'nova_proposicao': 'Criar a proposição (conferir os dados)', 'nova_sessao': 'Criar a sessão (conferir os dados)'}
DESTINOS_PAGINA = ('noticia', 'pagina', 'album', 'comunicado', 'nova_proposicao', 'nova_sessao')
DESTINOS_ARQUIVO = ('comunicado', 'sessao', 'proposicao', 'nova_proposicao', 'nova_sessao')
SO_LEGISLATIVO = ('sessao', 'proposicao', 'nova_proposicao', 'nova_sessao')
CRIAR = ('nova_proposicao', 'nova_sessao')   # só pelo formulário de conferência (criar_proposicao / criar_sessao)

PADRAO = {'paginas_max': 2000, 'cota_mb': 2048}   # por órgão, em config 'portal_antigo' (pode ser mudado sem código)
DISCO_MIN = 3 * 1024 ** 3                          # com menos de 3 GB livres a busca pausa sozinha
PROF_MAX = 8
LIM_HTML = 3 * 1024 * 1024
LIM_IMG = 8 * 1024 * 1024
LIM_DOC = 20 * 1024 * 1024
IMG_MIN_BYTES = 8 * 1024
IMG_MIN_LADO = 200
FOTOS_POR_PAGINA = 12
USOS_LAYOUT = 3                                    # foto que aparece em 3 páginas ou mais é logo/cabeçalho: fica de fora
EXT_PAGINA = ('', '.htm', '.html', '.php', '.asp', '.aspx', '.jsp', '.cfm', '.shtml')
EXT_DOC = ('.pdf', '.docx', '.xlsx', '.odt', '.ods', '.csv', '.doc', '.xls')
EXT_IMG = ('.jpg', '.jpeg', '.png', '.webp', '.gif')
EXT_FORA = ('.css', '.js', '.ico', '.svg', '.zip', '.rar', '.7z', '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.exe', '.xml', '.json', '.rss', '.woff', '.woff2', '.ttf', '.eot')
NAO_SEGUIR = re.compile(r'(login|logout|entrar|sair|admin|wp-admin|wp-login|painel|carrinho|cart|checkout|senha|password|cadastr|minha-conta|account|'
                        r'imprimir|print|share|compartilh|whatsapp|mailto|javascript|calendar|calendario|feed|\?replytocom=)', re.I)

def dormir(s):  # substituível nos testes
    time.sleep(s)

TRANSPORTE = None  # nos testes: httpx.MockTransport com um site fictício

# ---------- endereço: só o domínio informado, só internet pública ----------
_HOST = re.compile(r'^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$')

def publico(host: str) -> bool:
    """Todos os endereços do nome são públicos (nada de rede interna, loopback, link-local…)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    ips = {i[4][0] for i in infos}
    return bool(ips) and all(ipaddress.ip_address(ip.split('%')[0]).is_global for ip in ips)

def base_do(host):
    return host[4:] if host.startswith('www.') else host

def no_dominio(host: str, dominio: str) -> bool:
    b = base_do(dominio)
    return host == b or host.endswith('.' + b)

def _eh_ip(host):
    try:
        ipaddress.ip_address(host.strip('[]'))
        return True
    except ValueError:
        return False

def validar_endereco(url: str, proprios=()) -> tuple[str, str]:
    """Devolve (url normalizada, host) ou levanta ValueError com a explicação para quem cadastra."""
    url = (url or '').strip()
    if not re.match(r'^https?://', url, re.I):
        url = 'https://' + url
    p = urlsplit(url)
    host = (p.hostname or '').lower().rstrip('.')
    if _eh_ip(host):
        raise ValueError('Informe o endereço pelo nome (ex.: www.exemplo.sp.gov.br), não por número IP.')
    if p.scheme.lower() not in ('http', 'https') or not _HOST.match(host) or p.username or p.password:
        raise ValueError('Endereço inválido. Informe o domínio do portal antigo, como www.exemplo.sp.gov.br.')
    if p.port not in (None, 80, 443):
        raise ValueError('Use o endereço normal do portal (sem porta especial).')
    for d in proprios:
        d = (d or '').lower()
        if d and (no_dominio(host, d) or no_dominio(d, host)):
            raise ValueError('Esse é o endereço deste próprio portal. Informe o endereço do portal ANTIGO.')
    if not publico(host):
        raise ValueError('Não foi possível encontrar esse endereço na internet pública (confira o domínio).')
    return urlunsplit((p.scheme.lower(), host, p.path or '/', p.query, '')), host

def normalizar(url: str) -> str:
    p = urlsplit(url)
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True) if not re.match(r'^(utm_|fbclid|gclid|sessionid|phpsessid|jsessionid)', k, re.I)]
    host = (p.hostname or '').lower()
    porta = f':{p.port}' if p.port and p.port not in (80, 443) else ''
    return urlunsplit((p.scheme.lower(), host + porta, re.sub(r'/{2,}', '/', p.path or '/'), urlencode(q), ''))

def extensao(url):
    caminho = urlsplit(url).path.lower()
    m = re.search(r'(\.[a-z0-9]{2,5})$', caminho)
    return m.group(1) if m else ''

def tipo_link(url):
    e = extensao(url)
    if e in EXT_DOC:
        return 'doc'
    if e in EXT_IMG:
        return 'img'
    if e in EXT_FORA:
        return 'fora'
    return 'pagina' if e in EXT_PAGINA or len(e) > 5 else 'fora'

# ---------- leitura (com limite de tamanho e conferência de cada redirecionamento) ----------
class Recusado(Exception):
    pass

def baixar(c: httpx.Client, url, dominio, limite, publicos: dict):
    """GET seguro: segue até 5 redirecionamentos, todos no domínio e em endereço público. Devolve (url_final, status, tipo, dados)."""
    for _ in range(6):
        p = urlsplit(url)
        host = (p.hostname or '').lower()
        if p.scheme not in ('http', 'https') or not no_dominio(host, dominio) or p.port not in (None, 80, 443):
            raise Recusado('fora do domínio informado')
        if host not in publicos:
            publicos[host] = publico(host)
        if not publicos[host]:
            raise Recusado('endereço que não é da internet pública')
        with c.stream('GET', url) as r:
            if r.status_code in (301, 302, 303, 307, 308) and r.headers.get('location'):
                url = normalizar(urljoin(url, r.headers['location']))
                continue
            tipo = r.headers.get('content-type', '').split(';')[0].strip().lower()
            if r.status_code != 200:
                return url, r.status_code, tipo, b''
            n = r.headers.get('content-length')
            if n and n.isdigit() and int(n) > limite:
                raise Recusado('arquivo maior que o limite')
            buf = bytearray()
            for parte in r.iter_bytes():
                buf += parte
                if len(buf) > limite:
                    raise Recusado('arquivo maior que o limite')
            return url, 200, tipo, bytes(buf)
    raise Recusado('redirecionamentos demais')

def cliente():
    return httpx.Client(timeout=httpx.Timeout(20.0, connect=10.0), follow_redirects=False, transport=TRANSPORTE,
                        headers={'User-Agent': config.USER_AGENT + ' (migracao de conteudo do proprio orgao)', 'Accept-Language': 'pt-BR,pt;q=0.9'})

# ---------- extração de texto, data, fotos e links ----------
VAZIAS = {'img', 'br', 'hr', 'meta', 'link', 'input', 'source', 'wbr', 'area', 'base', 'col', 'embed', 'param', 'track'}
PULAR = {'script', 'style', 'noscript', 'nav', 'header', 'footer', 'aside', 'form', 'svg', 'button', 'select', 'iframe', 'template', 'object'}
BLOCOS = {'p', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr', 'blockquote', 'section', 'article', 'td', 'dd', 'dt', 'figcaption', 'br', 'table', 'ul', 'ol'}
CLASSE_PULAR = re.compile(r'(^|[\s_-])(menu|nav|navbar|rodape|footer|header|cabecalho|topo|sidebar|lateral|breadcrumb|cookie|compartilh|share|social|banner-topo|acessibilidade|busca|search|widget|related|relacionad)', re.I)
CLASSE_MIOLO = re.compile(r'(content|conteudo|noticia|news|post|entry|materia|texto|artigo|article|corpo|interna|single)', re.I)
IMG_LAYOUT = re.compile(r'(logo|icon|icone|brasao|sprite|loading|placeholder|banner|bandeira|selo|botao|button|seta|arrow|avatar|spacer|pixel|blank|facebook|instagram|twitter|youtube|whatsapp)', re.I)

class Extrator(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base; self.pilha = []; self.titulo = ''; self.h1 = ''; self.meta = {}; self.datas = []
        self.todo = []; self.miolo = []; self.links = []; self.imgs = []; self._a = None; self._em_titulo = False; self._em_h1 = False
    def _pulando(self):
        return any(p[1] for p in self.pilha)
    def _no_miolo(self):
        return any(p[2] for p in self.pilha)
    def handle_starttag(self, tag, attrs):
        a = {k: (v or '') for k, v in attrs}
        if tag == 'meta':
            k = (a.get('property') or a.get('name') or a.get('itemprop') or '').lower()
            if k and a.get('content'):
                self.meta[k] = a['content']
            return
        if tag == 'base' and a.get('href'):
            self.base = urljoin(self.base, a['href']); return
        if tag == 'time' and a.get('datetime'):
            self.datas.append(a['datetime'])
        if tag == 'img':
            src = a.get('data-src') or a.get('data-lazy-src') or a.get('src') or ''
            if src and not src.startswith('data:') and not self._pulando():
                self.imgs.append({'url': urljoin(self.base, src), 'alt': a.get('alt', '').strip()[:300], 'miolo': self._no_miolo(),
                                  'w': int(a['width']) if a.get('width', '').isdigit() else 0, 'h': int(a['height']) if a.get('height', '').isdigit() else 0})
            return
        if tag in VAZIAS:
            if tag == 'br':
                self._quebra()
            return
        cls = f"{a.get('class', '')} {a.get('id', '')} {a.get('role', '')}"
        pular = tag in PULAR or bool(CLASSE_PULAR.search(cls)) or a.get('aria-hidden') == 'true'
        miolo = tag in ('article', 'main') or (tag in ('div', 'section') and bool(CLASSE_MIOLO.search(cls)) and not pular)
        self.pilha.append((tag, pular, miolo))
        if tag == 'title':
            self._em_titulo = True
        if tag == 'h1' and not self._pulando():
            self._em_h1 = True
        if tag == 'a' and a.get('href'):
            self._a = {'url': a['href'], 'texto': ''}
        if tag in BLOCOS:
            self._quebra()
    def handle_endtag(self, tag):
        if tag in VAZIAS:
            return
        if tag == 'title':
            self._em_titulo = False
        if tag == 'h1':
            self._em_h1 = False
        if tag == 'a' and self._a:
            self.links.append(self._a); self._a = None
        for i in range(len(self.pilha) - 1, -1, -1):
            if self.pilha[i][0] == tag:
                del self.pilha[i:]
                break
        if tag in BLOCOS:
            self._quebra()
    def _quebra(self):
        for l in (self.todo, self.miolo):
            if l and l[-1] != '\n':
                l.append('\n')
    def handle_data(self, d):
        if self._em_titulo:
            self.titulo += d
        if self._a is not None:
            self._a['texto'] += d
        if self._pulando():
            return
        if self._em_h1:
            self.h1 += d
        self.todo.append(d)
        if self._no_miolo():
            self.miolo.append(d)

def _paragrafos(partes):
    t = ''.join(partes)
    linhas = [re.sub(r'[ \t\r\f\v ]+', ' ', l).strip() for l in t.split('\n')]
    return [l for l in linhas if len(l) > 1]

MESES = {'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4, 'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8, 'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12}

def sem_acento(s):
    return ''.join(c for c in unicodedata.normalize('NFD', s or '') if unicodedata.category(c) != 'Mn').lower()

def _valida(a, m, d):
    try:
        x = date(int(a), int(m), int(d))
    except ValueError:
        return None
    return x if date(1990, 1, 1) <= x <= config.hoje() else None

def achar_data(*textos):
    """Primeira data plausível (1990 até hoje): ISO, dd/mm/aaaa, “12 de março de 2024” ou /2024/03/12/ no endereço."""
    for t in textos:
        if not t:
            continue
        s = sem_acento(t)
        for m in re.finditer(r'(\d{4})-(\d{2})-(\d{2})', s):
            x = _valida(*m.groups())
            if x:
                return x
        for m in re.finditer(r'\b(\d{1,2})[/.](\d{1,2})[/.](\d{4})\b', s):
            x = _valida(m.group(3), m.group(2), m.group(1))
            if x:
                return x
        for m in re.finditer(r'\b(\d{1,2})o? de (' + '|'.join(MESES) + r') de (\d{4})\b', s):
            x = _valida(m.group(3), MESES[m.group(2)], m.group(1))
            if x:
                return x
        for m in re.finditer(r'/(\d{4})/(\d{1,2})/(\d{1,2})(?:/|$)', s):
            x = _valida(*m.groups())
            if x:
                return x
    return None

def extrair(html_bytes: bytes, url: str):
    """Título, data, parágrafos do texto principal, fotos e links de uma página."""
    texto = None
    m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', html_bytes[:4096], re.I)
    for cod in ([m.group(1).decode('ascii', 'ignore')] if m else []) + ['utf-8', 'cp1252']:
        try:
            texto = html_bytes.decode(cod); break
        except (UnicodeDecodeError, LookupError):
            continue
    if texto is None:
        texto = html_bytes.decode('utf-8', 'replace')
    e = Extrator(url)
    try:
        e.feed(texto); e.close()
    except Exception:
        pass
    miolo = _paragrafos(e.miolo)
    pars = miolo if sum(len(p) for p in miolo) >= 200 else _paragrafos(e.todo)
    titulo = (e.meta.get('og:title') or e.h1 or e.titulo or '').strip()
    titulo = re.sub(r'\s+', ' ', H.unescape(titulo))[:300]
    if titulo and pars and pars[0].strip().lower() == titulo.lower():
        pars = pars[1:]
    data = achar_data(e.meta.get('article:published_time', ''), e.meta.get('datepublished', ''), e.meta.get('date', ''), ' '.join(e.datas),
                      titulo, '\n'.join(pars[:6]), url)
    imgs = [i for i in e.imgs if i['miolo']] or e.imgs
    if e.meta.get('og:image'):
        imgs = [{'url': urljoin(url, e.meta['og:image']), 'alt': '', 'miolo': True, 'w': 0, 'h': 0}] + imgs
    vistos, fotos = set(), []
    for i in imgs:
        if i['url'] in vistos or IMG_LAYOUT.search(i['url'].rsplit('/', 1)[-1]) or (0 < i['w'] < IMG_MIN_LADO) or (0 < i['h'] < IMG_MIN_LADO * 0.6):
            continue
        vistos.add(i['url']); fotos.append(i)
    links = [{'url': urljoin(e.base, l['url'].strip()), 'texto': re.sub(r'\s+', ' ', l['texto']).strip()[:300]} for l in e.links if l['url'].strip()]
    return {'titulo': titulo, 'data': data, 'paragrafos': pars, 'fotos': fotos[:FOTOS_POR_PAGINA * 2], 'links': links}

# ---------- assunto, palavras-chave e LGPD ----------
PADROES = {
    'noticias': r'noticia|news|imprensa|materia|/blog|/post|comunicado|reportagem',
    'sessoes': r'sess(ao|oes)|\bata(s)?\b|ordem.do.dia|pauta|plenari|camara/sess',
    'proposicoes': r'projeto|\blei(s)?\b|decreto|resolu|portaria|moc(ao|oes)|requerimento|indicac|proposic|emenda|legislac|norma',
    'fotos': r'galeria|foto|album|imagens|fotografia',
}
CPF = re.compile(r'\b\d{3}\.\d{3}\.\d{3}-\d{2}\b|\b(?<![\d/.-])\d{11}(?![\d/.-])\b')
EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+')
FONE = re.compile(r'\(?\b\d{2}\)?\s?9?\d{4}-\d{4}\b')

def casa(assunto, *textos):
    return bool(re.search(PADROES[assunto], sem_acento(' '.join(t or '' for t in textos))))

def palavras_ok(palavras, *textos):
    ps = [sem_acento(p.strip()) for p in (palavras or '').split(',') if p.strip()]
    if not ps:
        return True
    s = sem_acento(' '.join(t or '' for t in textos))
    return any(p in s for p in ps)

def mascarar(t):
    """CPF nunca completo: vira ***.***.***-** no texto guardado."""
    return CPF.sub('***.***.***-**', t or '')

def avisos_lgpd(t):
    av = []
    if CPF.search(t or ''):
        av.append('Tinha número com formato de CPF: foi mascarado.')
    if EMAIL.search(t or ''):
        av.append('Tem e-mail no texto: confira se é institucional antes de publicar (LGPD).')
    if FONE.search(t or ''):
        av.append('Tem telefone no texto: confira se é institucional antes de publicar (LGPD).')
    return av

# ---------- sugestão de destino ----------
PROP = re.compile(r'(projeto de lei complementar|projeto de lei|projeto de resolucao|projeto de decreto legislativo|mocao|requerimento|indicacao|emenda)\D{0,25}?(\d{1,4})\s*/\s*(\d{4})')
PROP_TIPO = {'projeto de lei complementar': 'Projeto de Lei Complementar', 'projeto de lei': 'Projeto de Lei', 'projeto de resolucao': 'Projeto de Resolução',
             'projeto de decreto legislativo': 'Projeto de Decreto Legislativo', 'mocao': 'Moção', 'requerimento': 'Requerimento', 'indicacao': 'Indicação', 'emenda': 'Emenda'}

# ---------- dados de proposição e de sessão (Legislativo) ----------
# Só o que está ESCRITO no título, no endereço ou no texto; o que não aparece fica em branco para quem confere preencher.
PROP_CAB = re.compile(r'(projeto de lei complementar|projeto de lei|projeto de resolucao|projeto de decreto legislativo|mocao|requerimento|indicacao|emenda)'
                      r'\D{0,25}?(\d{1,3}(?:\.\d{3})?|\d{1,4})\s*(?:/|-|_|\s+de\s+|\s+)\s*((?:19|20)\d{2})\b')
SESSAO_A = re.compile(r'\b(\d{1,3})\s*[aoªº°]?\.?\s*sessao\s+(ordinaria|extraordinaria|solene|especial)')
SESSAO_B = re.compile(r'\bsessao\s+(ordinaria|extraordinaria|solene|especial)\s*(?:n\s*[o.]?\s*)?(\d{1,3})\b')
TIPO_SESSAO_TXT = {'ordinaria': 'Ordinária', 'extraordinaria': 'Extraordinária', 'solene': 'Solene', 'especial': 'Especial'}
HORA = re.compile(r'\b(?:as|a partir das|horario:?|inicio:?)\s*(\d{1,2})\s*(?:h|:|horas)\s*(\d{2})?')
ROT_EMENTA = re.compile(r'\bementa\s*[:–-]\s*(.{10,2000}?)(?:\n|$)', re.I)
ROT_AUTOR = re.compile(r'\baut(?:or|ora|ores|oria)(?:\s*\((?:a|es)\))?\s*[:–-]\s*([^\n]{3,300}?)(?:\s+(?:data|ementa|situa[cç][aã]o|apresenta)\b|\n|$)', re.I)
ROT_APRES = re.compile(r'(?:data\s+de\s+apresenta[cç][aã]o|apresentad[oa]\s+em|protocolad[oa]\s+em|data\s+do\s+protocolo)\s*:?\s*([^\n]{6,40})', re.I)
EMENTA_INICIO = re.compile(r'^(Disp[õo]e sobre|Institui|Autoriza|Denomina|D[áa] denomina|Altera|Declara|Concede|Cria|Revoga|Fixa|Estabelece|Aprova|Requer|Indica|Mo[çc][ãa]o de)\b')

def _sessao_txt(s):
    m = SESSAO_A.search(s)
    if m:
        return TIPO_SESSAO_TXT[m.group(2)], int(m.group(1))
    m = SESSAO_B.search(s)
    if m:
        return TIPO_SESSAO_TXT[m.group(1)], int(m.group(2))
    return None

def _hora_txt(s):
    m = HORA.search(sem_acento(s))
    if not m or int(m.group(1)) > 23 or (m.group(2) and int(m.group(2)) > 59):
        return ''
    return f"{int(m.group(1))}h{m.group(2) if m.group(2) and m.group(2) != '00' else ''}"

def _autor_limpo(a):
    a = re.sub(r'^(?:o |a )?(?:vereador(?:a|es)?|ver\.|vereadora?\(a\))\s+', '', a.strip(), flags=re.I)
    return mascarar(a.strip(' .;,'))[:300]

def _prop_txt(texto, prop):
    """Completa ementa, autor e data de apresentação a partir de um texto (página da proposição)."""
    if not texto:
        return
    if not prop['ementa']:
        m = ROT_EMENTA.search(texto)
        if m:
            prop['ementa'] = m.group(1).strip()[:2000]
        else:
            for par in texto.split('\n\n')[:8]:
                par = par.strip()
                if EMENTA_INICIO.match(par) and 10 <= len(par) <= 2000:
                    prop['ementa'] = par; break
    if not prop['autor']:
        m = ROT_AUTOR.search(texto)
        if m:
            prop['autor'] = _autor_limpo(m.group(1))
    if not prop['apresentada']:
        m = ROT_APRES.search(texto)
        if m:
            prop['apresentada'] = achar_data(m.group(1))

def campos_leg(b, it):
    """{'proposicao': {...} | None, 'sessao': {...} | None} lidos no título e no endereço do item (e no texto dele, ou da página onde o
    arquivo estava, se ela for da mesma proposição). Nada é deduzido: o que não aparece fica vazio."""
    from urllib.parse import unquote
    titulo = it.get('titulo') or ''
    caminho = re.sub(r'[-_+]+', ' ', unquote(urlsplit(it['url']).path))
    cab = sem_acento(f'{titulo} {caminho}')
    texto = it.get('texto') or ''
    origem = None
    if it['tipo'] == 'arquivo' and it.get('origem') and it.get('varredura_id'):
        origem = db.um(b, "SELECT titulo, texto FROM migracao_itens WHERE varredura_id=%s AND url=%s AND tipo='pagina'", (it['varredura_id'], it['origem']))
    prop = None
    m = PROP_CAB.search(cab)
    if m and 1900 <= int(m.group(3)) <= config.hoje().year:
        prop = {'tipo': PROP_TIPO[m.group(1)], 'numero': int(m.group(2).replace('.', '')), 'ano': int(m.group(3)), 'ementa': '', 'autor': '', 'apresentada': None}
        _prop_txt(texto, prop)
        if origem:
            mo = PROP_CAB.search(sem_acento(origem['titulo'] or ''))
            if mo and PROP_TIPO[mo.group(1)] == prop['tipo'] and int(mo.group(2).replace('.', '')) == prop['numero'] and int(mo.group(3)) == prop['ano']:
                _prop_txt(origem['texto'], prop)
    ses = None
    st = _sessao_txt(cab)
    if st:
        ses = {'tipo': st[0], 'numero': st[1], 'data': achar_data(titulo, caminho), 'hora': _hora_txt(f"{titulo}\n{texto[:1500]}")}
    return {'proposicao': prop, 'sessao': ses}

FALTA_PROP = {'tipo': 'tipo', 'numero': 'número', 'ano': 'ano', 'ementa': 'ementa', 'autor': 'autor'}
FALTA_SESSAO = {'tipo': 'tipo', 'numero': 'número', 'data': 'data', 'hora': 'hora'}

def faltando(destino, c):
    """Campos obrigatórios que a leitura não encontrou (a situação é sempre escolhida por quem confere)."""
    d = (c or {}).get('proposicao' if destino == 'nova_proposicao' else 'sessao')
    regras = FALTA_PROP if destino == 'nova_proposicao' else FALTA_SESSAO
    if not d:
        return list(regras.values())
    return [t for k, t in regras.items() if not d.get(k)]

def _prop_existente(b, p):
    return db.um(b, 'SELECT id, tipo, numero, ano FROM proposicoes WHERE tipo=%s AND numero=%s AND ano=%s', (p['tipo'], p['numero'], p['ano']))

def _sessao_existente(b, s):
    return db.um(b, 'SELECT id, nome FROM sessoes WHERE data=%s AND tipo=%s ORDER BY id LIMIT 1', (s['data'], s['tipo'])) if s.get('data') else None

def _sugerir_leg(b, it, alvo_txt):
    c = campos_leg(b, it)
    p, s = c['proposicao'], c['sessao']
    if p:
        ja = _prop_existente(b, p)
        if ja:
            if it['tipo'] == 'arquivo':
                return {'destino': 'proposicao', 'alvo': ja['id'], 'rotulo': f"{ja['tipo']} nº {ja['numero']}/{ja['ano']}"}
        else:
            return {'destino': 'nova_proposicao', 'rotulo': f"{p['tipo']} nº {p['numero']}/{p['ano']}"}
    if it['tipo'] == 'arquivo':
        m = PROP.search(sem_acento(alvo_txt))
        if m:
            ja = db.um(b, 'SELECT id, tipo, numero, ano FROM proposicoes WHERE tipo=%s AND numero=%s AND ano=%s', (PROP_TIPO[m.group(1)], int(m.group(2)), int(m.group(3))))
            if ja:
                return {'destino': 'proposicao', 'alvo': ja['id'], 'rotulo': f"{ja['tipo']} nº {ja['numero']}/{ja['ano']}"}
        ja = _sessao_existente(b, s) if s else None
        if not ja and it.get('data_original') and casa('sessoes', alvo_txt):
            ja = db.um(b, 'SELECT id, nome FROM sessoes WHERE data=%s ORDER BY id LIMIT 1', (it['data_original'],))
        if ja:
            return {'destino': 'sessao', 'alvo': ja['id'], 'rotulo': ja['nome']}
    if s and s['data'] and not _sessao_existente(b, s):
        return {'destino': 'nova_sessao', 'rotulo': f"{s['numero']}ª Sessão {s['tipo']} de {s['data'].strftime('%d/%m/%Y')}"}
    return None

def sugerir(b, tipo_orgao, it):
    alvo_txt = f"{it['titulo']} {it.get('origem_txt', '')} {it['url']}"
    if tipo_orgao == 'legislativo':
        s = _sugerir_leg(b, it, alvo_txt)
        if s:
            return s
    if it['tipo'] == 'arquivo':
        return {'destino': 'comunicado'}
    n_fotos = len(it.get('imagens') or [])
    if n_fotos >= 3 and len(it.get('texto') or '') < 600:
        return {'destino': 'album'}
    if casa('noticias', it['url'], it['titulo']) or (it.get('data_original') and len(it.get('texto') or '') >= 300):
        return {'destino': 'noticia'}
    return {'destino': 'pagina'}

# ---------- arquivos da área de revisão ----------
def pasta(o, vid):
    p = Path(config.DADOS_DIR) / o['slug'] / 'portal-antigo' / str(int(vid))
    p.mkdir(parents=True, exist_ok=True)
    return p

def tipo_real(dados: bytes):
    if dados.startswith(b'\x89PNG\r\n\x1a\n'):
        return 'png'
    if dados[:3] == b'\xff\xd8\xff':
        return 'jpg'
    if dados[:4] == b'RIFF' and dados[8:12] == b'WEBP':
        return 'webp'
    if dados[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    if dados.startswith(b'%PDF-'):
        return 'pdf'
    return ''

def guardar_arquivo(o, v, url, dados, eh_img):
    """Confere o tipo real e guarda; devolve (arquivo, ext, erro)."""
    b = o['banco']
    if eh_img:
        ext = tipo_real(dados)
        if ext not in ('png', 'jpg', 'webp', 'gif'):
            return None, '', 'não é imagem'
        if len(dados) < IMG_MIN_BYTES:
            return None, ext, 'imagem pequena (ícone ou miniatura)'
        try:
            from PIL import Image
            import io
            with Image.open(io.BytesIO(dados)) as im:
                if im.width < IMG_MIN_LADO or im.height < IMG_MIN_LADO * 0.6:
                    return None, ext, 'imagem pequena (ícone ou miniatura)'
        except Exception:
            return None, ext, 'imagem que não abre'
    else:
        from . import anexos as AX
        try:
            ext = AX.detectar(dados, url)
        except ValueError as e:
            return None, '', str(e)
    usado = db.um(b, 'SELECT coalesce(sum(bytes),0) n FROM migracao_arquivos')['n']
    cota = (db.cfg(b, 'portal_antigo', {}) or {}).get('cota_mb', PADRAO['cota_mb']) * 1024 * 1024
    if usado + len(dados) > cota:
        raise Pausar(f'Cota de armazenamento da busca atingida ({cota // 1024 // 1024} MB). Migre ou apague buscas antigas para continuar.')
    sha = hashlib.sha256(dados).hexdigest()
    nome = f'{sha[:32]}.{ext}'
    alvo = pasta(o, v['id']) / nome
    if not alvo.exists():
        alvo.write_bytes(dados)
    return nome, ext, ''

class Pausar(Exception):
    pass

# ---------- a varredura, em etapas curtas (o worker chama a cada minuto) ----------
def _fila(b, vid, url, prof, rotulo='', origem='', data_origem=None):
    db.exe(b, 'INSERT INTO migracao_fila (varredura_id, url, prof, rotulo, origem, data_origem) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (varredura_id, url) DO NOTHING',
           (vid, url[:2000], prof, rotulo[:300], origem[:2000], data_origem))

def _robots(c, v, publicos):
    """Lê o robots.txt uma vez; 401/403 = tudo proibido; ausente = tudo permitido."""
    p = urlsplit(v['url_inicial'])
    try:
        _, st, _, dados = baixar(c, f'{p.scheme}://{p.hostname}/robots.txt', v['dominio'], 512 * 1024, publicos)
    except (Recusado, httpx.HTTPError):
        st, dados = 0, b''
    if st in (401, 403):
        return 'User-agent: *\nDisallow: /'
    return dados.decode('utf-8', 'replace') if st == 200 else ''

def _parser(robots_txt):
    rp = RobotFileParser(); rp.parse((robots_txt or '').splitlines()); return rp

def _sitemaps(c, v, rp, publicos, b):
    p = urlsplit(v['url_inicial'])
    fila = list(rp.site_maps() or []) or [f'{p.scheme}://{p.hostname}/sitemap.xml']
    vistos, n = set(), 0
    while fila and len(vistos) < 20 and n < 5000:
        sm = fila.pop(0)
        if sm in vistos:
            continue
        vistos.add(sm)
        try:
            _, st, _, dados = baixar(c, normalizar(sm), v['dominio'], 10 * 1024 * 1024, publicos)
        except (Recusado, httpx.HTTPError):
            continue
        if st != 200:
            continue
        for loc in re.findall(rb'<loc>\s*([^<\s]+)\s*</loc>', dados)[:5000]:
            u = normalizar(H.unescape(loc.decode('utf-8', 'ignore')))
            if u.endswith('.xml') or 'sitemap' in u.rsplit('/', 1)[-1]:
                fila.append(u)
            elif no_dominio((urlsplit(u).hostname or '').lower(), v['dominio']) and tipo_link(u) in ('pagina', 'doc'):
                _fila(b, v['id'], u, 1); n += 1
    return n

def iniciar(o, v):
    b = o['banco']
    with cliente() as c:
        publicos = {}
        txt = _robots(c, v, publicos)
        rp = _parser(txt)
        atraso = rp.crawl_delay(config.USER_AGENT) or rp.crawl_delay('*') or 1
        db.exe(b, "UPDATE migracao_varreduras SET robots=%s, intervalo=%s, situacao='rodando', iniciado_em=coalesce(iniciado_em, now()), msg='' WHERE id=%s",
               (txt[:20000], min(max(float(atraso), 1.0), 10.0), v['id']))
        _fila(b, v['id'], v['url_inicial'], 0)
        n = _sitemaps(c, v, rp, publicos, b)
    return n

def _qualifica_pagina(v, ex, url):
    textos = (url, ex['titulo'], '\n'.join(ex['paragrafos'][:40]))
    a = v['assunto']
    if a in ('documentos',):
        return False
    if a in PADROES and not casa(a, url, ex['titulo']):
        return False
    if not palavras_ok(v['palavras'], *textos):
        return False
    if (v['desde'] or v['ate']) and ex['data'] and ((v['desde'] and ex['data'] < v['desde']) or (v['ate'] and ex['data'] > v['ate'])):
        return False
    if (v['desde'] or v['ate']) and not ex['data']:
        return False
    tam = sum(len(p) for p in ex['paragrafos'])
    return tam >= 200 or len(ex['fotos']) >= 2

def _qualifica_doc(v, f, url):
    a = v['assunto']
    t = (url, f['rotulo'], f['origem'])
    if a in ('noticias', 'paginas', 'fotos'):
        return False
    if a in ('sessoes', 'proposicoes') and not casa(a, *t):
        return False
    if not palavras_ok(v['palavras'], *t):
        return False
    d = achar_data(f['rotulo'], url) or f['data_origem']
    if (v['desde'] and (not d or d < v['desde'])) or (v['ate'] and (not d or d > v['ate'])):
        return False
    return True

def _fotos(c, o, v, ex, publicos):
    b = o['banco']; saida = []
    for i in ex['fotos']:
        if len(saida) >= FOTOS_POR_PAGINA:
            break
        u = normalizar(i['url'])
        if not no_dominio((urlsplit(u).hostname or '').lower(), v['dominio']):
            continue
        ja = db.um(b, 'SELECT * FROM migracao_arquivos WHERE varredura_id=%s AND url=%s', (v['id'], u))
        if ja:
            db.exe(b, 'UPDATE migracao_arquivos SET usos=usos+1 WHERE id=%s', (ja['id'],))
            if ja['arquivo']:
                saida.append({'arquivo_id': ja['id'], 'alt': i['alt']})
            continue
        dormir(_espera(b, v))
        try:
            _, st, _, dados = baixar(c, u, v['dominio'], LIM_IMG, publicos)
            nome, ext, erro = guardar_arquivo(o, v, u, dados, True) if st == 200 else (None, '', f'HTTP {st}')
        except (Recusado, httpx.HTTPError) as e:
            nome, ext, erro, dados = None, '', str(e)[:200] or type(e).__name__, b''
        a = db.exe(b, 'INSERT INTO migracao_arquivos (varredura_id, url, arquivo, ext, bytes, sha256, erro) VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (varredura_id, url) DO UPDATE SET usos=migracao_arquivos.usos+1 RETURNING id',
                   (v['id'], u, nome, ext, len(dados) if nome else 0, hashlib.sha256(dados).hexdigest() if nome else '', erro))
        if nome:
            saida.append({'arquivo_id': a['id'], 'alt': i['alt']})
    return saida

def _espera(b, v):
    """Segundos até o próximo pedido permitido (intervalo da busca)."""
    x = db.um(b, "SELECT greatest(0, %s - extract(epoch FROM (now() - coalesce(ultimo_pedido, now() - interval '1 hour')))) s FROM migracao_varreduras WHERE id=%s", (float(v['intervalo']), v['id']))
    db.exe(b, 'UPDATE migracao_varreduras SET ultimo_pedido=now() + make_interval(secs => %s) WHERE id=%s', (float(x['s']), v['id']))
    return float(x['s'])

def _item(o, v, d):
    b = o['banco']
    d['varredura_id'] = v['id']
    d['sugestao'] = sugerir(b, o['tipo'], d)
    r = db.exe(b, '''INSERT INTO migracao_itens (varredura_id, url, tipo, titulo, data_original, texto, imagens, arquivo_id, origem, avisos, sugestao)
                     VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (varredura_id, url) DO NOTHING RETURNING id''',
               (v['id'], d['url'], d['tipo'], d['titulo'][:300], d.get('data_original'), d.get('texto', ''), Jsonb(d.get('imagens', [])), d.get('arquivo_id'),
                d.get('origem', '')[:2000], Jsonb(d.get('avisos', [])), Jsonb(d['sugestao'])))
    if r:
        db.exe(b, 'UPDATE migracao_varreduras SET itens=itens+1 WHERE id=%s', (v['id'],))

def processar(o, vid, segundos=40):
    """Avança a busca por até `segundos`. Devolve o número de endereços lidos nesta etapa."""
    b = o['banco']
    v = db.um(b, 'SELECT * FROM migracao_varreduras WHERE id=%s', (vid,))
    if not v or v['situacao'] not in ('aguardando', 'rodando'):
        return 0
    fim = time.monotonic() + segundos; lidos = 0
    lim_cfg = (db.cfg(b, 'portal_antigo', {}) or {}).get('paginas_max', PADRAO['paginas_max'])
    limite = min(v['limite_paginas'], lim_cfg)
    try:
        if shutil.disk_usage(config.DADOS_DIR).free < DISCO_MIN:
            raise Pausar('Pouco espaço livre no servidor: a busca foi pausada. Avise o suporte.')
        if v['robots'] is None:
            iniciar(o, v)
            v = db.um(b, 'SELECT * FROM migracao_varreduras WHERE id=%s', (vid,))
        rp = _parser(v['robots'])
        publicos = {}
        with cliente() as c:
            while time.monotonic() < fim:
                v = db.um(b, 'SELECT * FROM migracao_varreduras WHERE id=%s', (vid,))
                if v['situacao'] != 'rodando':
                    break
                if v['paginas_lidas'] >= limite:
                    db.exe(b, "UPDATE migracao_varreduras SET situacao='concluida', concluido_em=now(), msg=%s WHERE id=%s", (f'Limite de {limite} endereços lidos. Para ir além, faça outra busca com mais páginas ou um assunto mais específico.', vid))
                    break
                f = db.um(b, "SELECT * FROM migracao_fila WHERE varredura_id=%s AND situacao='pendente' ORDER BY prof, id LIMIT 1", (vid,))
                if not f:
                    lida = db.um(b, "SELECT 1 FROM migracao_fila WHERE varredura_id=%s AND situacao='lida' LIMIT 1", (vid,))
                    m = ('Varredura completa: todos os endereços encontrados foram lidos.' if lida else
                         'Nenhuma página pôde ser lida. Confira o endereço; se o site antigo não abre com https://, cadastre de novo começando com http://.')
                    db.exe(b, "UPDATE migracao_varreduras SET situacao='concluida', concluido_em=now(), msg=%s WHERE id=%s", (m, vid))
                    break
                _ler(c, o, v, f, rp, publicos)
                lidos += 1
    except Pausar as e:
        db.exe(b, "UPDATE migracao_varreduras SET situacao='pausada', msg=%s WHERE id=%s", (str(e), vid))
    except Exception as e:
        db.exe(b, "UPDATE migracao_varreduras SET situacao='erro', msg=%s WHERE id=%s", (f'{type(e).__name__}: {str(e)[:300]}', vid))
        raise
    return lidos

def _marca(b, f, sit, motivo=''):
    db.exe(b, 'UPDATE migracao_fila SET situacao=%s, motivo=%s WHERE id=%s', (sit, motivo[:200], f['id']))

def _ler(c, o, v, f, rp, publicos):
    b = o['banco']; url = f['url']
    if not rp.can_fetch(config.USER_AGENT, url):
        return _marca(b, f, 'ignorada', 'proibido pelo robots.txt')
    tl = tipo_link(url)
    eh_doc = tl == 'doc'
    if eh_doc and not _qualifica_doc(v, f, url):
        return _marca(b, f, 'ignorada', 'fora do assunto ou do período')
    if extensao(url) in ('.doc', '.xls'):
        return _marca(b, f, 'ignorada', 'formato antigo do Office (.doc/.xls) não é aceito: pode conter macro')
    dormir(_espera(b, v))
    db.exe(b, 'UPDATE migracao_varreduras SET paginas_lidas=paginas_lidas+1 WHERE id=%s', (v['id'],))
    try:
        final, st, tipo, dados = baixar(c, url, v['dominio'], LIM_DOC if eh_doc else max(LIM_HTML, LIM_DOC), publicos)
    except Recusado as e:
        return _marca(b, f, 'ignorada', str(e))
    except httpx.HTTPError as e:
        return _marca(b, f, 'erro', type(e).__name__)
    if st in (401, 403):
        return _marca(b, f, 'ignorada', f'HTTP {st}: pede login ou recusa o acesso (não contornado)')
    if st != 200:
        return _marca(b, f, 'erro', f'HTTP {st}')
    db.exe(b, 'UPDATE migracao_varreduras SET bytes=bytes+%s WHERE id=%s', (len(dados), v['id']))
    if eh_doc or tipo in ('application/pdf',) or dados.startswith(b'%PDF-'):
        if not eh_doc and not _qualifica_doc(v, f, url):
            return _marca(b, f, 'ignorada', 'fora do assunto ou do período')
        nome, ext, erro = guardar_arquivo(o, v, url, dados, False)
        if not nome:
            return _marca(b, f, 'ignorada', erro)
        a = db.exe(b, 'INSERT INTO migracao_arquivos (varredura_id, url, arquivo, ext, bytes, sha256) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (varredura_id, url) DO UPDATE SET arquivo=EXCLUDED.arquivo RETURNING id',
                   (v['id'], url, nome, ext, len(dados), hashlib.sha256(dados).hexdigest()))
        titulo = f['rotulo'] if len(f['rotulo']) >= 4 and not re.fullmatch(r'(baixar|download|clique aqui|aqui|ver|abrir|arquivo|pdf)\W*', f['rotulo'], re.I) else \
            re.sub(r'[-_]+', ' ', urlsplit(url).path.rsplit('/', 1)[-1].rsplit('.', 1)[0])[:200] or 'Documento'
        _item(o, v, {'url': url, 'tipo': 'arquivo', 'titulo': titulo, 'data_original': achar_data(f['rotulo'], url) or f['data_origem'], 'arquivo_id': a['id'],
                     'origem': f['origem'], 'origem_txt': f['rotulo']})
        return _marca(b, f, 'lida')
    if 'html' not in tipo and not dados.lstrip()[:200].lower().startswith((b'<!doctype html', b'<html')):
        return _marca(b, f, 'ignorada', f'conteúdo {tipo or "desconhecido"}')
    ex = extrair(dados, final)
    if re.search(r'captcha|recaptcha|cf-challenge|verifique se voce e humano', sem_acento(' '.join(ex['paragrafos'][:10]) + ex['titulo'])):
        return _marca(b, f, 'ignorada', 'página com verificação anti-robô (não contornada)')
    # links: páginas e arquivos do mesmo domínio entram na fila
    if f['prof'] < PROF_MAX:
        n_fila = db.um(b, 'SELECT count(*) n FROM migracao_fila WHERE varredura_id=%s', (v['id'],))['n']
        for l in ex['links']:
            if n_fila > v['limite_paginas'] * 5:
                break
            u = l['url']
            if not u.lower().startswith(('http://', 'https://')) or NAO_SEGUIR.search(u):
                continue
            u = normalizar(u)
            if not no_dominio((urlsplit(u).hostname or '').lower(), v['dominio']) or tipo_link(u) not in ('pagina', 'doc'):
                continue
            _fila(b, v['id'], u, f['prof'] + 1, l['texto'] or ex['titulo'], final, ex['data']); n_fila += 1
    if not _qualifica_pagina(v, ex, final):
        return _marca(b, f, 'lida', 'lida (links seguidos), sem item para o assunto')
    fotos = _fotos(c, o, v, ex, publicos) if v['assunto'] != 'documentos' else []
    corpo = '\n\n'.join(ex['paragrafos'])
    _item(o, v, {'url': final, 'tipo': 'pagina', 'titulo': ex['titulo'] or final, 'data_original': ex['data'], 'texto': mascarar(corpo)[:100000],
                 'imagens': fotos, 'avisos': avisos_lgpd(corpo)})
    _marca(b, f, 'lida')

# ---------- worker ----------
def tick(orcamento=45):
    """Chamado pelo worker a cada minuto: avança as buscas em andamento de todos os órgãos desta instalação, uma por vez."""
    from . import orgaos
    fim = time.monotonic() + orcamento
    for o in orgaos.todos():
        try:
            vs = db.todos(o['banco'], "SELECT id FROM migracao_varreduras WHERE situacao IN ('aguardando','rodando') ORDER BY id")
        except Exception:
            continue
        for v in vs:
            resta = fim - time.monotonic()
            if resta < 5:
                return
            try:
                processar(o, v['id'], segundos=resta)
            except Exception:
                import traceback; traceback.print_exc()

# ---------- migração para a seção certa (sempre rascunho / não publicado) ----------
def _fotos_validas(b, it):
    ids = [i['arquivo_id'] for i in (it['imagens'] or [])]
    if not ids:
        return []
    arqs = {a['id']: a for a in db.todos(b, 'SELECT * FROM migracao_arquivos WHERE id = ANY(%s) AND arquivo IS NOT NULL AND usos < %s', (ids, USOS_LAYOUT))}
    return [(arqs[i['arquivo_id']], i.get('alt', '')) for i in it['imagens'] if i['arquivo_id'] in arqs]

def _para_midia(o, v_id, arq, uso, alt, quem):
    """Converte a foto da área de revisão em WEBP (até 1920 px) na pasta de mídia do órgão. Devolve a URL pública."""
    from . import imagens
    import secrets
    origem = pasta(o, v_id) / arq['arquivo']
    destino_pasta = Path(config.DADOS_DIR) / o['slug'] / 'midia'
    destino_pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.webp'
    n = imagens.para_webp(origem, destino_pasta / nome)
    db.exe(o['banco'], 'INSERT INTO midias (arquivo, uso, alt, credito, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s)', (nome, uso, (alt or '')[:300], 'Portal anterior do órgão', n, quem))
    return f'/midia/{nome}'

def _html(it):
    pars = [p for p in (it['texto'] or '').split('\n\n') if p.strip()]
    corpo = ''.join(f'<p>{H.escape(p)}</p>' for p in pars)
    if it['data_original']:
        corpo += f"<p><em>Publicado originalmente em {it['data_original'].strftime('%d/%m/%Y')} no portal anterior.</em></p>"
    from .editor import limpar
    return limpar(corpo)[0]

def migrar(o, it_id, destino, alvo, quem):
    """Cria o rascunho (ou o documento vinculado) a partir do item revisado. Devolve a mensagem para quem migrou."""
    b = o['banco']
    it = db.um(b, 'SELECT * FROM migracao_itens WHERE id=%s', (it_id,))
    if not it or it['situacao'] != 'novo':
        raise ValueError('Item não encontrado ou já tratado.')
    if destino not in DESTINOS or (destino in SO_LEGISLATIVO and o['tipo'] != 'legislativo'):
        raise ValueError('Escolha para onde o item vai.')
    if (it['tipo'] == 'pagina' and destino not in DESTINOS_PAGINA) or (it['tipo'] == 'arquivo' and destino not in DESTINOS_ARQUIVO):
        raise ValueError('Esse destino não serve para esse tipo de item.')
    if destino in CRIAR:
        raise ValueError('Para criar a sessão ou a proposição, confira os dados no formulário do item.')
    titulo = (it['titulo'] or 'Sem título')[:300]
    arq = db.um(b, 'SELECT * FROM migracao_arquivos WHERE id=%s', (it['arquivo_id'],)) if it['arquivo_id'] else None
    nota = 'Migrado do portal anterior: confira texto, data, fotos e a classificação eleitoral antes de enviar para revisão.'
    if destino in ('noticia', 'pagina'):
        html = _html(it)
        from .editor import texto as txt
        fotos = _fotos_validas(b, it)
        img, alt = ('', '')
        if fotos:
            alt = fotos[0][1] or titulo
            img = _para_midia(o, it['varredura_id'], fotos[0][0], 'noticia', alt, quem)
        cid = db.exe(b, '''INSERT INTO conteudos (tipo, secao, titulo, resumo, texto, html, classe, situacao, autor, comentario, imagem, imagem_alt)
                          VALUES (%s,%s,%s,%s,%s,%s,'pub','rascunho',%s,%s,%s,%s) RETURNING id''',
                     ('Notícia' if destino == 'noticia' else 'Página', 'Notícias' if destino == 'noticia' else 'Serviços', titulo[:200], txt(html)[:300], txt(html), html, quem, nota, img, alt[:300]))['id']
        db.exe(b, 'INSERT INTO conteudo_versoes (conteudo_id, quem, obs) VALUES (%s,%s,%s)', (cid, quem, 'Criado a partir do portal anterior (rascunho)'))
        msg, did = f"{'Notícia' if destino == 'noticia' else 'Página'} criada como rascunho em Notícias e páginas.", cid
    elif destino == 'album':
        fotos = _fotos_validas(b, it)
        if not fotos:
            raise ValueError('Esse item não tem fotos aproveitáveis.')
        aid = db.exe(b, 'INSERT INTO albuns (titulo, descricao, publicado) VALUES (%s,%s,FALSE) RETURNING id',
                     (titulo[:160], ((it['texto'] or '')[:900] + ('\n\n' if it['texto'] else '') + 'Fotos migradas do portal anterior.')[:1000]))['id']
        for n, (a, alt_f) in enumerate(fotos):
            alt_f = alt_f if len(alt_f or '') >= 5 else f'Foto {n + 1} do álbum {titulo}'[:300]
            url = _para_midia(o, it['varredura_id'], a, 'album', alt_f, quem)
            db.exe(b, '''INSERT INTO album_fotos (album_id, url, credito, licenca, alt, tem_pessoas, autorizacao_imagem, principal, ordem)
                         VALUES (%s,%s,'Portal anterior do órgão','Todos os direitos reservados',%s,TRUE,FALSE,%s,%s)''', (aid, url, alt_f[:300], n == 0, n + 1))
        msg, did = f'Álbum criado com {len(fotos)} foto(s), fora do ar. Confira as fotos, a licença e a autorização de uso de imagem antes de publicar.', aid
    elif destino == 'comunicado':
        from . import anexos as AX
        import secrets
        html = _html(it) if it['tipo'] == 'pagina' else ''
        from .editor import texto as txt
        cid = db.exe(b, "INSERT INTO comunicados (tipo, titulo, texto, html, situacao, autor, comentario) VALUES ('Comunicado',%s,%s,%s,'rascunho',%s,%s) RETURNING id",
                     (titulo[:200], txt(html), html, quem, nota))['id']
        if arq and arq['arquivo']:
            nome = f"{secrets.token_hex(16)}.{arq['ext']}"
            shutil.copyfile(pasta(o, it['varredura_id']) / arq['arquivo'], AX.pasta(o) / nome)
            db.exe(b, 'INSERT INTO comunicado_anexos (comunicado_id, arquivo, nome_original, titulo, ext, bytes, enviado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                   (cid, nome, urlsplit(it['url']).path.rsplit('/', 1)[-1][:120], titulo[:200], arq['ext'], arq['bytes'], quem))
        msg, did = 'Comunicado criado como rascunho' + (', com o arquivo anexado.' if arq else '.'), cid
    else:  # sessao | proposicao: documento PDF vinculado
        if not arq or arq['ext'] != 'pdf':
            raise ValueError('Só PDF pode ser vinculado a uma sessão ou proposição.')
        if not alvo:
            raise ValueError('Escolha a sessão ou a proposição.')
        tab = 'sessoes' if destino == 'sessao' else 'proposicoes'
        if not db.um(b, f'SELECT 1 FROM {tab} WHERE id=%s', (alvo,)):
            raise ValueError('Sessão ou proposição não encontrada.')
        did, tipo = _vincular_pdf(o, it, arq, destino, alvo, quem)
        msg = 'PDF vinculado à ' + ('sessão' if destino == 'sessao' else 'proposição') + (' como ata (aparece no portal quando a ata for publicada).' if tipo == 'ata' else '.')
    db.exe(b, "UPDATE migracao_itens SET situacao='migrado', destino=%s, destino_id=%s, migrado_por=%s, migrado_em=now() WHERE id=%s", (destino, did, quem, it_id))
    return msg

def _vincular_pdf(o, it, arq, destino, alvo, quem):
    """Copia o PDF da área de revisão para os documentos do órgão, ligado à sessão ou à proposição. Devolve (id, tipo)."""
    import secrets
    b = o['banco']; titulo = (it['titulo'] or 'Documento')[:300]
    d_pasta = Path(config.DADOS_DIR) / o['slug'] / 'docs'
    d_pasta.mkdir(parents=True, exist_ok=True)
    nome = f'{secrets.token_hex(16)}.pdf'
    shutil.copyfile(pasta(o, it['varredura_id']) / arq['arquivo'], d_pasta / nome)
    st = sem_acento(titulo)
    tipo = ('ata' if re.search(r'\bata\b', st) else 'outro') if destino == 'sessao' else ('parecer' if 'parecer' in st else 'texto')
    desc = f'{titulo} — documento migrado do portal anterior.'
    did = db.exe(b, f"INSERT INTO documentos (arquivo, tipo, titulo, descricao, bytes, enviado_por, {'sessao_id' if destino == 'sessao' else 'proposicao_id'}) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                 (nome, tipo, titulo[:200], desc[:1000], arq['bytes'], quem, alvo))['id']
    return did, tipo

def _item_para_criar(o, it_id):
    b = o['banco']
    if o['tipo'] != 'legislativo':
        raise ValueError('Só a Câmara cria sessões e proposições.')
    it = db.um(b, 'SELECT * FROM migracao_itens WHERE id=%s', (it_id,))
    if not it or it['situacao'] != 'novo':
        raise ValueError('Item não encontrado ou já tratado.')
    arq = db.um(b, 'SELECT * FROM migracao_arquivos WHERE id=%s', (it['arquivo_id'],)) if it['arquivo_id'] else None
    return it, (arq if arq and arq['ext'] == 'pdf' and arq['arquivo'] else None)

def _data_form(x, nome):
    if isinstance(x, date):
        return x
    try:
        return date.fromisoformat(x) if x else None
    except ValueError:
        raise ValueError(f'{nome}: data inválida.')

def _concluir(b, it, destino, did, quem):
    db.exe(b, "UPDATE migracao_itens SET situacao='migrado', destino=%s, destino_id=%s, migrado_por=%s, migrado_em=now() WHERE id=%s AND situacao='novo'", (destino, did, quem, it['id']))

def criar_proposicao(o, it_id, d, quem):
    """Cria a proposição com os dados CONFERIDOS por quem revisa (d = formulário) e liga o PDF do item, se houver.
    Sem votos, presenças nem tramitação deduzida: só a apresentação, quando a data foi informada."""
    from . import legislativo as L
    import psycopg
    b = o['banco']; it, arq = _item_para_criar(o, it_id)
    tipo = d.get('tipo') or ''
    if tipo not in L.TIPO_SIGLA:
        raise ValueError('Escolha o tipo da proposição.')
    num, ano = str(d.get('numero') or '').replace('.', ''), str(d.get('ano') or '')
    if not num.isdigit() or not int(num) or not ano.isdigit() or not 1900 <= int(ano) <= config.hoje().year:
        raise ValueError('Informe o número e o ano da proposição.')
    num, ano = int(num), int(ano)
    ementa = re.sub(r'[ \t]+', ' ', mascarar(d.get('ementa') or '')).strip()
    if len(ementa) < 10:
        raise ValueError('Escreva a ementa (pelo menos 10 caracteres), como está no documento original.')
    autores = [_autor_limpo(x) for x in (d.get('autor') or '').split(';') if x.strip()]
    if not autores:
        raise ValueError('Informe o autor (vereador, Poder Executivo, Mesa Diretora ou Comissão); separe vários com ponto e vírgula.')
    situacao = d.get('situacao') or ''
    if situacao not in L.SITUACOES_PROP:
        raise ValueError('Escolha a situação da proposição, conforme o documento original.')
    apres = _data_form(d.get('apresentada'), 'Apresentação')
    if apres and apres > config.hoje():
        raise ValueError('A data de apresentação não pode ser futura.')
    rot = f'{tipo} nº {num}/{ano}'
    if db.um(b, 'SELECT 1 FROM proposicoes WHERE tipo=%s AND numero=%s AND ano=%s', (tipo, num, ano)):
        raise ValueError(f'{rot} já existe no portal: escolha “Documento de uma proposição” para ligar o arquivo a ela.')
    try:
        pid = db.exe(b, "INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao, apresentada, origem) VALUES (%s,%s,%s,'',%s,%s,%s,'portal_antigo') RETURNING id",
                     (tipo, num, ano, ementa[:2000], situacao, apres))['id']
    except psycopg.errors.UniqueViolation:
        raise ValueError(f'{rot} já existe no portal.')
    L.definir_autores(b, pid, autores)
    if apres:
        L.tramitar(b, pid, apres, 'Apresentação', f'{rot}. Registro migrado do portal anterior.', quem=quem, origem='portal_antigo')
    extra = ''
    if arq:
        _vincular_pdf(o, it, arq, 'proposicao', pid, quem); extra = ', com o PDF anexado'
    _concluir(b, it, 'nova_proposicao', pid, quem)
    return f'{rot} criada{extra}. Ela já aparece no portal com os dados conferidos.'

def criar_sessao(o, it_id, d, quem):
    """Cria a sessão com os dados CONFERIDOS; pauta, ata, presença e votação ficam sem publicar. Liga o PDF do item, se houver."""
    from . import legislativo as L
    b = o['banco']; it, arq = _item_para_criar(o, it_id)
    tipo = d.get('tipo') or ''
    if tipo not in L.TIPOS_SESSAO:
        raise ValueError('Escolha o tipo da sessão.')
    data = _data_form(d.get('data'), 'Data da sessão')
    if not data:
        raise ValueError('Informe a data da sessão.')
    hora = L.hora(d.get('hora'))
    if not hora:
        raise ValueError('Informe o horário da sessão, como está no documento original (ex.: 19h).')
    num = str(d.get('numero') or '')
    num = int(num) if num.isdigit() and int(num) else None
    nome = re.sub(r'\s+', ' ', d.get('nome') or '').strip()[:160] or (L.nome_sessao(num, tipo, data.year) if num else '')
    if not nome:
        raise ValueError('Informe o número ou o nome da sessão.')
    realizada = str(d.get('realizada') or '') == '1'
    if realizada and data > config.hoje():
        raise ValueError('Uma sessão com data futura não pode ser marcada como realizada.')
    ja = db.um(b, 'SELECT id, nome FROM sessoes WHERE data=%s AND tipo=%s', (data, tipo))
    if ja:
        raise ValueError(f'Já existe a sessão “{ja["nome"]}” nessa data: escolha “Documento de uma sessão” para ligar o arquivo a ela.')
    sid = db.exe(b, "INSERT INTO sessoes (nome, data, hora, tipo, numero, situacao, origem) VALUES (%s,%s,%s,%s,%s,%s,'portal_antigo') RETURNING id",
                 (nome, data, hora, tipo, num, 'realizada' if realizada else 'agendada'))['id']
    extra = ''
    if arq:
        _, t = _vincular_pdf(o, it, arq, 'sessao', sid, quem)
        extra = ', com a ata anexada (aparece no portal quando a ata for publicada)' if t == 'ata' else ', com o PDF anexado'
    _concluir(b, it, 'nova_sessao', sid, quem)
    return f'Sessão criada: {nome}{extra}. Pauta, ata, presença e votação continuam sem publicar.'

def dados_iniciais(b, it, destino):
    """Valores para o formulário de conferência (o que a leitura encontrou; o resto em branco)."""
    c = campos_leg(b, it)
    if destino == 'nova_proposicao':
        return dict(c['proposicao'] or {'tipo': '', 'numero': '', 'ano': '', 'ementa': '', 'autor': '', 'apresentada': None}, situacao='')
    s = c['sessao'] or {'tipo': '', 'numero': '', 'data': None, 'hora': ''}
    return dict(s, nome='', realizada='')

def apagar(o, vid):
    """Apaga a busca, a fila e os arquivos da área de revisão (o que já foi migrado continua nas seções)."""
    db.exe(o['banco'], 'DELETE FROM migracao_varreduras WHERE id=%s', (vid,))
    p = Path(config.DADOS_DIR) / o['slug'] / 'portal-antigo' / str(int(vid))
    if p.is_dir():
        shutil.rmtree(p)
