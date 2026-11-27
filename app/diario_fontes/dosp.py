"""Adaptador DOSP (Imprensa Oficial Municipal, P&P Colibri).

A API não é documentada nem oficial: foi deduzida do próprio site e do projeto Querido Diário (okfn-brasil/querido-diario,
gazette/spiders/base/dosp.py). Conferida em 27/11/2026 com a página de Borá:
  1. código do município: na página https://www.imprensaoficialmunicipal.com.br/{slug}, regex urlapi+'.js/(\\d+)/'+idsecao;
     fica guardado na configuração da fonte e só é descoberto de novo se a lista falhar;
  2. edições: https://dosp.com.br/api/index.php/dioe.js/{codigo}, em JSONP (parseResponse({...});), às vezes dentro de <p>;
     campos data (AAAA-MM-DD), edicao_do, flag_extra (>0 = extra), iddo, pgtotal e, nas recentes, link (PDF direto);
     devolve tudo: o filtro por data é feito aqui;
  3. link da edição: o "link" da própria DOSP quando vem; senão https://dosp.com.br/exibe_do.php?i={base64(iddo)}.
A página normal da DOSP carrega um script do Cloudflare (/cdn-cgi/challenge-platform/scripts/jsd/...): isso não é bloqueio.
Bloqueio é quando a resposta esperada não vem e, no lugar dela, aparece a página de verificação de navegador."""
import base64
import json
import re
from datetime import date
from urllib.parse import urlsplit

from . import Edicao, ErroFonte, Bloqueio, FonteDiario, registrar

PAGINA = 'https://www.imprensaoficialmunicipal.com.br/{slug}'
API = 'https://dosp.com.br/api/index.php/dioe.js/{codigo}'
EXIBE = 'https://dosp.com.br/exibe_do.php?i={i}'
HOSTS_PDF = ('dosp.com.br', 'www.dosp.com.br')

RE_CODIGO = re.compile(r"urlapi\+'\.js/(\d+)/'\+idsecao")
RE_SLUG = re.compile(r'^[a-z0-9][a-z0-9-]{1,59}$')
MARCAS_BLOQUEIO = ('cf-chl', 'cf_chl_opt', 'just a moment', 'challenge-platform/h/', 'challenge-form', 'attention required! | cloudflare')


def eh_bloqueio(status: int, texto: str) -> bool:
    """Página de verificação do Cloudflare no lugar do conteúdo (o script passivo jsd da página normal não conta)."""
    t = (texto or '')[:20000].lower()
    return any(m in t for m in MARCAS_BLOQUEIO) and ('parseresponse(' not in t and 'urlapi' not in t)


def ler_jsonp(texto: str) -> dict:
    """parseResponse({...}); → dict. Aceita a resposta dentro de <p>...</p> e espaços nas pontas."""
    t = (texto or '').strip()
    if 'parseResponse(' not in t:
        raise ValueError('sem parseResponse')
    t = re.sub(r'^.*?parseResponse\(', '', t, count=1, flags=re.S)
    t = re.sub(r'\)\s*;?\s*(</p>)?\s*$', '', t)
    return json.loads(t)


def link_edicao(d: dict) -> str:
    link = str(d.get('link') or '').strip()
    p = urlsplit(link)
    if p.scheme == 'https' and p.hostname in HOSTS_PDF and p.path.lower().endswith('.pdf'):
        return link
    return EXIBE.format(i=base64.b64encode(str(d['iddo']).encode()).decode())


def numero(v) -> str:
    s = str(v or '').strip()
    return str(int(s)) if s.isdigit() else s[:20]


@registrar
class Dosp(FonteDiario):
    tipo = 'dosp'
    plataforma = 'DOSP — Imprensa Oficial Municipal'
    campos = (('slug', 'Endereço do município na DOSP', 'A parte final de imprensaoficialmunicipal.com.br/… (ex.: bora)'),)

    @classmethod
    def validar_config(cls, cfg):
        slug = str(cfg.get('slug') or '').strip().lower().strip('/')
        slug = slug.rsplit('/', 1)[-1] if '/' in slug else slug
        if not RE_SLUG.match(slug):
            raise ValueError('Informe o endereço do município na DOSP: só letras minúsculas, números e hífen (ex.: bora).')
        return {'slug': slug}

    def descobrir_codigo(self) -> str:
        html = self.http.get(PAGINA.format(slug=self.config['slug']), bloqueio=eh_bloqueio)
        m = RE_CODIGO.search(html)
        if not m:
            if eh_bloqueio(200, html):
                raise Bloqueio('a plataforma pediu verificação de navegador (Cloudflare); a sincronização parou sem contornar o bloqueio')
            raise ErroFonte('não achei o código do município na página da DOSP (confira o endereço)')
        self.config['codigo'] = m.group(1)
        return m.group(1)

    def _lista(self, codigo):
        txt = self.http.get(API.format(codigo=codigo), bloqueio=eh_bloqueio)
        try:
            d = ler_jsonp(txt)
        except ValueError:
            if eh_bloqueio(200, txt) or ('challenge' in txt.lower() and 'cf-' in txt.lower()):
                raise Bloqueio('a plataforma pediu verificação de navegador (Cloudflare); a sincronização parou sem contornar o bloqueio')
            raise ErroFonte('a lista de edições da DOSP veio fora do formato esperado')
        if not isinstance(d, dict) or not isinstance(d.get('data'), list):
            raise ErroFonte('a lista de edições da DOSP veio sem o campo "data"')
        return d['data']

    def listar_edicoes(self, desde=None, ate=None):
        codigo = str(self.config.get('codigo') or '')
        if not codigo.isdigit():
            codigo = self.descobrir_codigo()
            itens = self._lista(codigo)
        else:
            try:
                itens = self._lista(codigo)
            except Bloqueio:
                raise
            except ErroFonte:
                antigo = codigo  # o código pode ter mudado: descobre de novo uma vez
                codigo = self.descobrir_codigo()
                if codigo == antigo:
                    raise
                itens = self._lista(codigo)
        out = []
        for d in itens:
            try:
                dt = date.fromisoformat(str(d['data'])[:10])
                iddo = int(d['iddo'])
            except (KeyError, TypeError, ValueError):
                continue  # registro incompleto: ignorado
            if (desde and dt < desde) or (ate and dt > ate):
                continue
            try:
                extra = int(d.get('flag_extra') or 0) > 0
            except (TypeError, ValueError):
                extra = False
            pg = d.get('pgtotal')
            out.append(Edicao(id_externo=str(iddo), numero=numero(d.get('edicao_do')), data=dt, extra=extra,
                              url=link_edicao(d), paginas=int(pg) if str(pg or '').isdigit() else None))
        return out
