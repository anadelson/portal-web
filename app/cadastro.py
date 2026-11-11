"""Cadastro de órgão novo pelo console (etapa 1 do modelo multi-órgão, 10/11/2026).

A partir do formulário do console monta tudo o que o órgão precisa para nascer, sem nada fixo no código:
identidade (nome, contatos, cores), integrações (Siconfi, PNCP, TCESP, sistema contábil) e o administrador inicial.
O município e a UF vêm do IBGE pelo código de 7 dígitos (servicodados.ibge.gov.br); sem acesso à API, valem os digitados."""
import re, secrets, string, unicodedata
from . import config

UFS = {'AC': 'Acre', 'AL': 'Alagoas', 'AP': 'Amapá', 'AM': 'Amazonas', 'BA': 'Bahia', 'CE': 'Ceará', 'DF': 'Distrito Federal', 'ES': 'Espírito Santo',
       'GO': 'Goiás', 'MA': 'Maranhão', 'MT': 'Mato Grosso', 'MS': 'Mato Grosso do Sul', 'MG': 'Minas Gerais', 'PA': 'Pará', 'PB': 'Paraíba', 'PR': 'Paraná',
       'PE': 'Pernambuco', 'PI': 'Piauí', 'RJ': 'Rio de Janeiro', 'RN': 'Rio Grande do Norte', 'RS': 'Rio Grande do Sul', 'RO': 'Rondônia', 'RR': 'Roraima',
       'SC': 'Santa Catarina', 'SP': 'São Paulo', 'SE': 'Sergipe', 'TO': 'Tocantins'}
# sistemas da transparência com coletor pronto; os demais ficam "sem integração" até ganharem adaptador (etapa 4)
SISTEMAS = {'fiorilli': 'Fiorilli (API pública VersaoJson)', 'govbr': 'GOVBR — TransparênciaBR / Pronim TB (exportação XML)',
            'nenhum': 'Outro sistema / ainda sem integração'}
BASES_FIORILLI = {'executivo': ['receitas', 'despesas_unidade', 'empenhos', 'diarias', 'restos_pagar', 'ordem_cronologica', 'licitacoes', 'contratos', 'transferencias', 'servidores'],
                  'legislativo': ['transferencias', 'emendas']}
COR_PADRAO = {'executivo': '#1D4E89', 'legislativo': '#2F5233'}
DOMINIO = re.compile(r'^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$')
COR = re.compile(r'^#[0-9A-Fa-f]{6}$')

def sem_acento(t):
    return ''.join(c for c in unicodedata.normalize('NFD', t or '') if unicodedata.category(c) != 'Mn')

def slug_municipio(municipio):
    """Nome do município em minúsculas, sem acento, com hífen (ex.: 'Águas de Lindóia' → 'aguas-de-lindoia')."""
    return re.sub(r'[^a-z0-9]+', '-', sem_acento(municipio).lower()).strip('-')

def slug_sugerido(tipo, municipio):
    return ('pm-' if tipo == 'executivo' else 'cm-') + slug_municipio(municipio)[:27].strip('-')

def nome_sugerido(tipo, municipio):
    return ('Prefeitura Municipal de ' if tipo == 'executivo' else 'Câmara Municipal de ') + municipio

def cnpj_valido(c):
    d = re.sub(r'\D', '', c or '')
    if len(d) != 14 or d == d[0] * 14:
        return False
    def dv(base, pesos):
        s = sum(int(a) * b for a, b in zip(base, pesos)) % 11
        return '0' if s < 2 else str(11 - s)
    return d[12] == dv(d[:12], [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]) and d[13] == dv(d[:13], [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])

def cnpj_formatado(c):
    d = re.sub(r'\D', '', c)
    return f'{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}'

def consultar_ibge(codigo):
    """Município e UF pelo código IBGE. Devolve dict ou None (código inexistente ou API fora do ar)."""
    if not re.fullmatch(r'\d{7}', codigo or ''):
        return None
    import httpx
    try:
        with httpx.Client(timeout=10, headers={'User-Agent': config.USER_AGENT, 'Accept': 'application/json'}) as c:
            r = c.get(f'https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{codigo}')
        d = r.json() if r.status_code == 200 else None
        if not d or not isinstance(d, dict) or not d.get('nome'):
            return None
        uf = (((d.get('microrregiao') or {}).get('mesorregiao') or {}).get('UF') or {}).get('sigla') or ((d.get('regiao-imediata') or {}).get('regiao-intermediaria') or {}).get('UF', {}).get('sigla')
        return {'municipio': d['nome'], 'uf': uf or '', 'uf_nome': UFS.get(uf or '', '')}
    except Exception:
        return None

def senha_inicial():
    """Senha provisória forte e única do administrador do órgão (mostrada uma vez no console; troca obrigatória no 1º acesso)."""
    alfa = string.ascii_letters + string.digits
    while True:
        s = ''.join(secrets.choice(alfa) for _ in range(16))
        if any(c.islower() for c in s) and any(c.isupper() for c in s) and any(c.isdigit() for c in s):
            return s

def montar(f, ibge_api=None, ocupados=()):
    """Valida o formulário do console. Devolve (dados, erros); `dados` tem o necessário para provision.registrar_orgao."""
    erros = []
    tipo = f.get('tipo')
    if tipo not in ('executivo', 'legislativo'):
        erros.append('Escolha o tipo do órgão (Prefeitura ou Câmara).')
        tipo = 'executivo'
    ibge = re.sub(r'\D', '', f.get('ibge', ''))
    if len(ibge) != 7:
        erros.append('Informe o código IBGE do município (7 dígitos).')
    municipio, uf = (f.get('municipio') or '').strip(), (f.get('uf') or '').strip().upper()
    if ibge_api:  # o IBGE manda: nome e UF oficiais
        municipio, uf = ibge_api['municipio'], ibge_api['uf'] or uf
    if not municipio or uf not in UFS:
        erros.append('Município e UF não encontrados: confira o código IBGE ou preencha o município e a UF.')
    nome = (f.get('nome') or '').strip() or (nome_sugerido(tipo, municipio) if municipio else '')
    slug = (f.get('slug') or '').strip().lower() or (slug_sugerido(tipo, municipio) if municipio else '')
    if not re.fullmatch(r'[a-z0-9-]{3,30}', slug):
        erros.append('O identificador precisa ter de 3 a 30 letras minúsculas, números ou hífen (ex.: pm-nome-do-municipio).')
    dominio = (f.get('dominio') or '').strip().lower().rstrip('.')
    if not DOMINIO.match(dominio):
        erros.append('Domínio inválido (ex.: portal.municipio.sp.gov.br ou pmexemplo.conectatech.tech).')
    for campo, valor in (('identificador', slug), ('domínio', dominio)):
        if valor and valor in ocupados:
            erros.append(f'Já existe um órgão com este {campo}.')
    cnpj = (f.get('cnpj') or '').strip()
    if cnpj and not cnpj_valido(cnpj):
        erros.append('CNPJ inválido (confira os dígitos).')
    email_admin = (f.get('email_admin') or '').strip().lower()
    if not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email_admin):
        erros.append('Informe o e-mail do administrador do órgão (quem vai entrar primeiro no painel).')
    cor = (f.get('cor') or '').strip() or COR_PADRAO[tipo]
    if not COR.match(cor):
        erros.append('Cor principal inválida: use o formato #RRGGBB.')
    sistema = f.get('sistema') or 'nenhum'
    if sistema not in SISTEMAS:
        erros.append('Sistema da transparência inválido.')
    fio_base, fio_emp = (f.get('fio_base') or '').strip(), (f.get('fio_empresa') or '').strip()
    if sistema == 'fiorilli':
        if not re.match(r'^https://[^\s/]+(:\d+)?/', fio_base):
            erros.append('Fiorilli: informe o endereço https da API (ex.: https://<municipio>.dcfiorilli.com.br:879/transparencia/VersaoJson/).')
        if not re.fullmatch(r'\d{1,4}', fio_emp):
            erros.append('Fiorilli: informe o código da entidade (número, ex.: 2).')
    gov_base, gov_unid = (f.get('gov_base') or '').strip(), (f.get('gov_unidades') or '').strip()
    if sistema == 'govbr':
        if not re.match(r'^https://[^\s/]+(:\d+)?/[\w./-]*$', gov_base):
            erros.append('GOVBR: informe o endereço https do portal (ex.: https://<municipio>.cidade360.cloud/pronimtb/).')
        if len(gov_unid) > 300:
            erros.append('GOVBR: nome da unidade gestora longo demais.')
    if erros:
        return None, erros
    if gov_base and not gov_base.endswith('/'):
        gov_base += '/'
    if not fio_base.endswith('/') and fio_base:
        fio_base += '/'
    nome_curto = municipio if tipo == 'executivo' else nome
    ident = {'nome': nome, 'nome_curto': nome_curto, 'subtitulo': f'Estado de {UFS[uf]}', 'cor': cor,
             'cnpj': cnpj_formatado(cnpj) if cnpj else '', 'endereco': (f.get('endereco') or '').strip()[:300], 'telefone': (f.get('telefone') or '').strip()[:60],
             'email': (f.get('email') or '').strip()[:120], 'horario': (f.get('horario') or '').strip()[:120]}
    if tipo == 'executivo':
        ident['conheca'] = {'rotulo': f'Conheça {municipio}', 'titulo': '', 'texto': ''}
    # integrações: só as que fazem sentido com os dados informados
    fontes = {'siconfi': {'ibge': ibge, 'rgf_poder': 'E' if tipo == 'executivo' else 'L', **({'rreo': True} if tipo == 'executivo' else {})}}
    if tipo == 'executivo' and cnpj:
        fontes['pncp'] = {'ibge': ibge, 'cnpj': cnpj_formatado(cnpj)}
    if tipo == 'executivo' and uf == 'SP':
        fontes['tcesp'] = {'municipio': (f.get('tcesp') or '').strip().lower() or slug_municipio(municipio), 'anos': [config.hoje().year - 1]}
    if sistema == 'fiorilli':
        fontes['fiorilli'] = {'base': fio_base, 'empresa': fio_emp, 'bases': BASES_FIORILLI[tipo],
                              **({'recebedora': (f.get('fio_recebedora') or 'Câmara Municipal').strip()} if tipo == 'legislativo' else {})}
    if sistema == 'govbr':
        from .coletores.govbr import PADRAO_BASES
        fontes['govbr'] = {'base': gov_base, 'unidades': gov_unid or ('PREFEITURA' if tipo == 'executivo' else 'CAMARA'), 'bases': PADRAO_BASES[tipo],
                           'meses_recentes': 2, 'pessoal': '', **({'recebedora': (f.get('gov_recebedora') or 'PODER LEGISLATIVO').strip()} if tipo == 'legislativo' else {})}
    from .catalogo import MODULOS, serve
    opcionais = {m[0]: f.get(f'mod_{m[0]}') == '1' for m in MODULOS if m[3] == 'opc' and serve(m[0], tipo)}
    return {'slug': slug, 'nome': nome, 'tipo': tipo, 'dominio': dominio, 'banco': 'bd_' + slug.replace('-', '_'), 'plano': 'Executivo' if tipo == 'executivo' else 'Legislativo',
            'cor': cor, 'opcionais': opcionais, 'municipio': f'{municipio} ({uf})', 'ibge': ibge, 'uf': uf, 'identidade': ident, 'fontes': fontes,
            'email_admin': email_admin, 'sistema': sistema}, []
