"""Provisionamento: cria o banco de controle, os bancos dos órgãos e os dados iniciais.

Uso:
  python -m app.provision init        # primeira instalação (idempotente)
  python -m app.provision atualizar   # aplica as migrações em todos os bancos e acrescenta blocos/identidade novos
  python -m app.provision orgao SLUG  # aplica o esquema de novo num órgão existente

Migrações: app/migrations/NNN_*.sql em ordem; as que têm "plataforma" no nome vão para o banco de
controle, as demais para o banco de cada órgão. Todas precisam ser idempotentes.
"""
import json, sys
from datetime import date
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from . import config, db
from .catalogo import MODULOS, LAYOUT_PADRAO, LAYOUT_PADRAO_V1, serve
from .security import hash_senha

AQUI = Path(__file__).parent
MIGRACOES = sorted((AQUI / 'migrations').glob('[0-9][0-9][0-9]_*.sql'))
MIG_PLAT = [m for m in MIGRACOES if 'plataforma' in m.stem]
MIG_ORGAO = [m for m in MIGRACOES if 'plataforma' not in m.stem]

def criar_banco(nome: str):
    with psycopg.connect(config.dsn('postgres'), autocommit=True) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (nome,)).fetchone():
            c.execute(f'CREATE DATABASE "{nome}"')
            print('banco criado:', nome)

def aplicar(banco: str, migracoes):
    with psycopg.connect(config.dsn(banco), autocommit=True) as c:
        for m in migracoes:
            c.execute(m.read_text(encoding='utf-8'))

IDENT = {
    'pm-bora': {'nome': 'Prefeitura Municipal de Borá', 'endereco': 'Praça Santo Antonio, 10 · Borá (SP) · CEP 19740-005', 'telefone': '(18) 3367-1103', 'email': 'pmbora@bora.sp.gov.br', 'cnpj': '44.544.906/0001-42', 'horario': 'Segunda a sexta, 8h às 17h', 'encarregado': '[nome do encarregado de dados]', 'encarregado_email': '[e-mail do encarregado]', 'cor': '#1D4E89'},
    'cm-bora': {'nome': 'Câmara Municipal de Borá', 'endereco': 'Rua Vereador Herculano Azevedo, 10 · Centro · Borá (SP) · CEP 19740-000', 'telefone': '(18) 3367-1146', 'email': 'camara@camarabora.sp.gov.br', 'cnpj': '[CNPJ da Câmara]', 'horario': 'Segunda a sexta, 9h às 11h e 13h às 17h', 'encarregado': '[nome do encarregado de dados]', 'encarregado_email': '[e-mail do encarregado]', 'cor': '#2F5233'},
}

# Identidade visual (Fase 3): valores padrão por tipo de órgão; cada órgão pode trocar tudo em /admin/identidade.
VISUAL_PADRAO = {
    'executivo': {'prefixo': 'Prefeitura Municipal de', 'cor_destaque': '#F0B429', 'hero_rotulo': 'Portal oficial da Prefeitura',
                  'hero_titulo': 'O que você precisa hoje?', 'hero_texto': 'Peça serviços, acompanhe seus pedidos e veja como a Prefeitura usa o dinheiro público.',
                  'busca_dica': 'Ex.: IPTU, creche, edital, diário oficial', 'mais_buscados': ['IPTU', 'Vacinação', 'Concurso', 'Nota fiscal']},
    'legislativo': {'prefixo': 'Poder Legislativo', 'cor_destaque': '#F7C948', 'hero_rotulo': 'Portal oficial da Câmara Municipal',
                    'hero_titulo': 'Acompanhe o trabalho dos vereadores', 'hero_texto': 'Sessões, projetos, votações e gastos da Câmara, num só lugar e em linguagem simples.',
                    'busca_dica': 'Busque projeto, indicação ou vereador', 'mais_buscados': []},
}
_CREDITO_PM = 'Foto: Prefeitura Municipal de Borá'
IDENT_VISUAL = {
    'pm-bora': {
        'nome_curto': 'Borá', 'subtitulo': 'Estado de São Paulo', 'cor_antiga': '#1D4E89', 'cor': '#0E4D64',
        'brasao': {'url': '/static/img/brasao.webp', 'alt': 'Brasão do Município de Borá'},
        'hero': {'url': '/static/img/vista-aerea.webp', 'alt': 'Vista aérea de Borá, com a praça central, a Igreja Matriz e as ruas arborizadas', 'credito': _CREDITO_PM},
        'conheca': {'rotulo': 'Conheça Borá', 'titulo': 'Pequena, tranquila e acolhedora',
                    'texto': 'O segundo menor município do Brasil em população (IBGE, Censo 2022), com praça arborizada no centro, a Igreja Matriz como cartão-postal e a agroindústria da cana-de-açúcar movimentando a economia.',
                    'numeros': [['Habitantes (Censo 2022)', '907'], ['Área territorial', '119 km²'], ['Distância da capital', '~500 km'], ['IDHM (2010)', '0,746']],
                    'fonte': 'IBGE: Censo 2022, área territorial e IDHM 2010.',
                    'fotos': [{'url': '/static/img/praca-aerea.webp', 'alt': 'Vista aérea da praça central com a Igreja Matriz, o chafariz, o coreto e as ruas arborizadas', 'legenda': 'Praça e Igreja Matriz, vistas do alto', 'credito': _CREDITO_PM},
                              {'url': '/static/img/igreja-matriz.webp', 'alt': 'Igreja Matriz branca de torre pontiaguda, cercada de palmeiras e árvores', 'legenda': 'Igreja Matriz', 'credito': _CREDITO_PM},
                              {'url': '/static/img/usina.webp', 'alt': 'Portaria de uma usina de açúcar e etanol, com caminhão na entrada', 'legenda': 'Agroindústria da cana-de-açúcar', 'credito': _CREDITO_PM}]},
        'sede': {'titulo': 'Paço Municipal', 'foto': {'url': '/static/img/paco-municipal.webp', 'alt': 'Fachada do Paço Municipal, prédio branco arredondado com jardim de roseiras na frente', 'credito': _CREDITO_PM}},
        'creditos': 'Fotos da cidade: Prefeitura Municipal de Borá. Fotos dos cartões de serviços: Unsplash e Rawpixel, CC0, via Wikimedia Commons.',
    },
    'cm-bora': {
        'nome_curto': 'Câmara Municipal de Borá', 'subtitulo': 'Estado de São Paulo',
        'brasao': {'url': '/static/img/brasao.webp', 'alt': 'Brasão do Município de Borá'},
        'hero': {'url': '/static/img/paco-municipal.webp', 'alt': 'Fachada do Paço Municipal de Borá, prédio branco arredondado com jardim na frente', 'credito': _CREDITO_PM},
        'sede': {'titulo': 'Sede da Câmara', 'foto': {}},
        'creditos': 'Foto do destaque: Prefeitura Municipal de Borá.',
    },
}

# Fontes de dados por órgão (Fase 4). Só valores padrão de configuração: ficam na tabela `fontes` e podem ser trocados.
FIORILLI_BORA = 'https://borasp.dcfiorilli.com.br:879/transparencia/VersaoJson/'
FONTES_PADRAO = {
    'pm-bora': {'fiorilli': {'base': FIORILLI_BORA, 'empresa': '2', 'bases': ['receitas', 'despesas_unidade', 'empenhos', 'diarias', 'restos_pagar', 'ordem_cronologica', 'licitacoes', 'contratos', 'transferencias', 'servidores']},
                'pncp': {'ibge': '3507209', 'cnpj': '44.544.906/0001-42'},
                'siconfi': {'ibge': '3507209', 'rreo': True, 'rgf_poder': 'E'},
                'tcesp': {'municipio': 'bora', 'anos': [2025]}},
    'cm-bora': {'fiorilli': {'base': FIORILLI_BORA, 'empresa': '2', 'bases': ['transferencias', 'emendas'], 'recebedora': 'Câmara Municipal'},
                'siconfi': {'ibge': '3507209', 'rgf_poder': 'L'}},
}

def configurar_fontes(oid, slug):
    """Cadastra as fontes padrão do órgão se ainda não existirem (nunca sobrescreve a configuração feita)."""
    n = 0
    for fonte, params in FONTES_PADRAO.get(slug, {}).items():
        r = db.exe(db.PLATAFORMA, 'INSERT INTO fontes (orgao_id, fonte, params) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1', (oid, fonte, Jsonb(params)))
        n += 1 if r else 0
    return n

# Fontes do painel de indicadores (Fase 7): genéricas para todo órgão do Executivo, pelo código IBGE do município.
# MDS e vacinação (PNI) nascem desligados: fonte fora do ar / pendente de fonte estável.
FONTES_PAINEL = {'painel': True, 'ibge': True, 'cnes': True, 'inep': True, 'iegm': True, 'financas': True, 'mds': False, 'pni': False}
# iegm: só coleta com IEGM_USUARIO/IEGM_SENHA no .env e o IEG-M em modo automático no painel administrativo

def configurar_painel(o):
    """Semeia o catálogo de indicadores e cadastra as fontes do painel (nunca sobrescreve o que já existe)."""
    if o['tipo'] != 'executivo':
        return 0, 0
    from . import painel
    novos = painel.semear(o['banco'])
    nf = 0
    for fonte, ativo in FONTES_PAINEL.items():
        params = {'ibge': o['ibge']}
        if fonte == 'financas':  # usa a mesma API e entidade da fonte fiorilli do órgão
            fio = db.um(db.PLATAFORMA, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='fiorilli'", (o['id'],))
            if not fio:
                continue
            params = {k: fio['params'][k] for k in ('base', 'empresa') if k in fio['params']}
        r = db.exe(db.PLATAFORMA, 'INSERT INTO fontes (orgao_id, fonte, params, ativo) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1', (o['id'], fonte, Jsonb(params), ativo))
        nf += 1 if r else 0
    return novos, nf

def completar_identidade(banco, slug, tipo):
    """Acrescenta à identidade do órgão as chaves visuais que ainda não existem (nunca sobrescreve o que o órgão definiu)."""
    ident = db.cfg(banco, 'identidade', {}) or {}
    novo = dict(VISUAL_PADRAO.get(tipo, {}))
    novo.update(IDENT_VISUAL.get(slug, {}))
    antiga = novo.pop('cor_antiga', None)
    mudou = False
    for k, v in novo.items():
        if k == 'cor':
            if antiga and ident.get('cor') == antiga:  # ainda na cor padrão da Fase 2: troca pela cor do protótipo
                ident['cor'] = v; mudou = True
            continue
        if k not in ident:
            ident[k] = v; mudou = True
    ident.setdefault('revisado_em', date.today().isoformat())
    if mudou:
        db.set_cfg(banco, 'identidade', ident)
    return mudou

def atualizar_layout(banco, tipo):
    """Acrescenta blocos novos ao layout sem apagar os existentes. Se o órgão nunca mexeu no layout
    (ainda igual ao padrão da Fase 2), aplica o novo padrão inteiro."""
    atual = [(b['chave'], b['regiao']) for b in db.todos(banco, "SELECT chave, regiao FROM blocos WHERE pagina='home' ORDER BY ordem, id")]
    alvo = LAYOUT_PADRAO[tipo]
    if atual == LAYOUT_PADRAO_V1.get(tipo):
        for i, (k, reg) in enumerate(alvo):
            db.exe(banco, "INSERT INTO blocos (pagina, chave, regiao, ordem) VALUES ('home',%s,%s,%s) ON CONFLICT (pagina, chave) DO UPDATE SET regiao=EXCLUDED.regiao, ordem=EXCLUDED.ordem", (k, reg, i))
        return 'padrão novo aplicado'
    usados = {k for k, _ in atual}
    novos = [(k, reg) for k, reg in alvo if k not in usados]
    for k, reg in novos:
        mx = db.um(banco, "SELECT coalesce(max(ordem),0)+1 n FROM blocos WHERE pagina='home' AND regiao<>'rodape'")['n']
        db.exe(banco, "INSERT INTO blocos (pagina, chave, regiao, ordem) VALUES ('home',%s,%s,%s) ON CONFLICT DO NOTHING", (k, reg, mx))
    return f"{len(novos)} bloco(s) novo(s) acrescentado(s)" if novos else 'sem blocos novos'

ORGAOS = [
    ('pm-bora', 'Prefeitura Municipal de Borá', 'executivo', lambda: config.DOMINIO_PM, 'bd_pm_bora', 'Executivo', '#1D4E89', {'diario': True, 'bi': False, 'tema3': False}),
    ('cm-bora', 'Câmara Municipal de Borá', 'legislativo', lambda: config.DOMINIO_CM, 'bd_cm_bora', 'Legislativo', '#2F5233', {'integpref': True, 'emend': True, 'tema3': False}),
]

def registrar_orgao(slug, nome, tipo, dominio, banco, plano, cor, opcionais, municipio='Borá (SP)', ibge=config.IBGE_BORA, inicio=None, fim=None):
    r = db.um(db.PLATAFORMA, 'SELECT id FROM orgaos WHERE slug=%s', (slug,))
    if r:
        db.exe(db.PLATAFORMA, 'UPDATE orgaos SET dominio=%s WHERE id=%s', (dominio, r['id']))
        oid = r['id']
    else:
        oid = db.exe(db.PLATAFORMA, 'INSERT INTO orgaos (slug,nome,tipo,dominio,banco,municipio,ibge,plano,cor) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id', (slug, nome, tipo, dominio, banco, municipio, ibge, plano, cor))['id']
        db.exe(db.PLATAFORMA, 'INSERT INTO contratos (orgao_id, inicio, fim) VALUES (%s,%s,%s)', (oid, inicio or date(2026, 12, 1), fim or date(2027, 11, 30)))
    for m in MODULOS:
        if m[3] == 'opc' and serve(m[0], tipo):
            db.exe(db.PLATAFORMA, 'INSERT INTO orgao_modulos (orgao_id, chave, contratado) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (oid, m[0], bool(opcionais.get(m[0]))))
    criar_banco(banco)
    aplicar(banco, MIG_ORGAO)
    if not db.cfg(banco, 'identidade'):
        db.set_cfg(banco, 'identidade', IDENT.get(slug, {'nome': nome, 'cor': cor}))
    completar_identidade(banco, slug, tipo)
    configurar_fontes(oid, slug)
    configurar_painel(db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,)))
    if not db.um(banco, 'SELECT 1 FROM blocos LIMIT 1'):
        for i, (k, reg) in enumerate(LAYOUT_PADRAO[tipo]):
            db.exe(banco, 'INSERT INTO blocos (pagina, chave, regiao, ordem) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING', ('home', k, reg, i))
    if not db.um(banco, 'SELECT 1 FROM usuarios LIMIT 1'):
        email = f'admin@{dominio}'
        db.exe(banco, "INSERT INTO usuarios (nome, email, setor, perfil, escopo, senha_hash) VALUES (%s,%s,%s,'admin','Órgão inteiro',%s)", ('Administrador do órgão', email, 'Administração', hash_senha(config.SENHA_INICIAL_ADMIN)))
        print(f'  usuário inicial: {email} (senha = SENHA_INICIAL_ADMIN; troque no primeiro acesso)')
    return oid

def seed_camara(banco):
    if db.um(banco, 'SELECT 1 FROM vereadores LIMIT 1'):
        return
    d = json.loads((AQUI / 'seeds' / 'camara_bora.json').read_text(encoding='utf-8'))
    for L in d['LEGIS']:
        db.exe(banco, 'INSERT INTO legislaturas VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING', (L['n'], L['anos'], L['prefeito'], L['vice']))
        for v in L['ver']:
            db.exe(banco, 'INSERT INTO vereadores (nome, apelido, partido, legislatura, votos) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (v[0], v[1], v[2], L['n'], v[3]))
        for m in L['mesas']:
            if m['m']:
                for cargo, nome in m['m']:
                    db.exe(banco, 'INSERT INTO mesas (legislatura, bienio, cargo, nome) VALUES (%s,%s,%s,%s)', (L['n'], m['b'], cargo, nome))
            else:
                for cargo in ('Presidente', 'Vice-presidente', '1º secretário', '2º secretário'):
                    db.exe(banco, 'INSERT INTO mesas (legislatura, bienio, cargo, nome) VALUES (%s,%s,%s,NULL)', (L['n'], m['b'], cargo))
    exe = d['EXEC_EMENDA']
    for e in d['EMENDAS_IMP']:
        det = exe.get(e[0])
        pago_emp = None
        empenho = ''
        if det:
            pago_emp = sum(p[1] for em in det['empenhos'] for p in em['pag'])
            empenho = ', '.join(em['num'] for em in det['empenhos'])
        conf = 'sem_execucao' if not det and not e[7] else ('conferido' if det and abs((pago_emp or 0) - e[7]) < 0.01 else 'divergente')
        db.exe(banco, 'INSERT INTO emendas (numero, autor, objeto, valor, pago_cadastro, pago_empenho, empenho, conferencia, fonte, detalhe) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
               (e[0], e[1], e[2], e[3], e[7], pago_emp, empenho, conf, 'Fiorilli (Prefeitura), leitura de 05/11/2026', Jsonb(det) if det else None))
    for ano, num, autor, ementa in d['INDIC']:
        db.exe(banco, 'INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
               ('Indicação', num, ano, autor, ementa or '[ementa a importar do sistema legislativo]', 'Encaminhada ao Executivo'))
    for tipo, numano, autores, ementa, data, sit in d['OUTRAS']:
        num, ano = numano.split('/')
        db.exe(banco, 'INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao) VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', (tipo, int(num), int(ano), '; '.join(autores), ementa, sit))
    for nome, data, hora, st in d['SESSOES']:
        if data == '—':
            continue
        dd, mm, aa = data.split('/')
        db.exe(banco, 'INSERT INTO sessoes (nome, data, hora, pauta_publicada) VALUES (%s,%s,%s,%s)', (nome, date(int(aa), int(mm), int(dd)), hora or '19h', st == 'pauta'))
    db.set_cfg(banco, 'financas', {'dtp': d['DTP_CM'], 'rgf': d['RGF_CM'], 'duodecimo_2026': 1458400, 'fonte': 'Siconfi (RGF do Legislativo) e cadastro da Câmara, consulta de 05/11/2026'})
    print('  dados reais da Câmara carregados')

def seed_prefeitura(banco):
    if db.um(banco, 'SELECT 1 FROM conteudos LIMIT 1'):
        return
    hoje = config.hoje()
    itens = [
        ('Aviso', 'Serviços', 'Vacinação contra a gripe nas unidades de saúde', 'Doses para idosos, gestantes e crianças, de segunda a sexta, 8h às 16h.', 'util', 'publicado'),
        ('Notícia', 'Notícias', '[Prefeito] entrega a reforma da quadra do Balneário', 'Exemplo de notícia com nome de agente político (sai no defeso).', 'agente', 'publicado'),
        ('Página', 'Serviços', 'IPTU 2027: como emitir a guia e pedir isenção', 'Prazos, documentos e canais de atendimento.', 'serv', 'rascunho'),
        ('Notícia', 'Notícias', 'Recapeamento da Rua 31 de Agosto começa em dezembro', 'Exemplo de divulgação de obra (publicidade institucional).', 'pub', 'revisao'),
        ('Documento', 'Transparência', 'Edital de concurso público nº [1]/2026', 'Edital, cronograma e anexos.', 'ato', 'publicado'),
    ]
    for tipo, sec, tit, res, cl, sit in itens:
        db.exe(banco, 'INSERT INTO conteudos (tipo, secao, titulo, resumo, texto, classe, situacao, exemplo, autor, publicar_em) VALUES (%s,%s,%s,%s,%s,%s,%s,TRUE,%s,%s)',
               (tipo, sec, tit, res, res, cl, sit, 'Administrador do órgão', hoje if sit == 'publicado' else None))
    print('  conteúdos de exemplo da Prefeitura carregados (marcados como exemplo)')

def init():
    criar_banco(db.PLATAFORMA)
    aplicar(db.PLATAFORMA, MIG_PLAT)
    for m in MODULOS:
        db.exe(db.PLATAFORMA, 'INSERT INTO modulos VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (chave) DO UPDATE SET nome=EXCLUDED.nome, descricao=EXCLUDED.descricao, oferta=EXCLUDED.oferta, serve=EXCLUDED.serve, depende=EXCLUDED.depende', m)
    if not db.um(db.PLATAFORMA, 'SELECT 1 FROM gestores LIMIT 1'):
        email = f'gestor@{config.DOMINIO_GESTAO}'
        db.exe(db.PLATAFORMA, 'INSERT INTO gestores (nome, email, senha_hash) VALUES (%s,%s,%s)', ('Gestor do projeto', email, hash_senha(config.SENHA_INICIAL_GESTOR)))
        print(f'gestor inicial: {email} (senha = SENHA_INICIAL_GESTOR; troque no primeiro acesso)')
    for slug, nome, tipo, dom, banco, plano, cor, opc in ORGAOS:
        print('órgão:', slug)
        registrar_orgao(slug, nome, tipo, dom(), banco, plano, cor, opc)
    seed_prefeitura('bd_pm_bora')
    seed_camara('bd_cm_bora')
    from . import remessa
    np = remessa.configurar_pares()
    if np:
        print(f'{np} integração(ões) entre órgãos criada(s) (token guardado no banco de controle)')
    print('pronto.')

def atualizar():
    """Atualização sem perda: migrações idempotentes em todos os bancos, catálogo de módulos,
    chaves novas da identidade e blocos novos da página inicial."""
    aplicar(db.PLATAFORMA, MIG_PLAT)
    print('plataforma: migrações', ', '.join(m.name for m in MIG_PLAT))
    for m in MODULOS:
        db.exe(db.PLATAFORMA, 'INSERT INTO modulos VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (chave) DO UPDATE SET nome=EXCLUDED.nome, descricao=EXCLUDED.descricao, oferta=EXCLUDED.oferta, serve=EXCLUDED.serve, depende=EXCLUDED.depende', m)
    for o in db.todos(db.PLATAFORMA, 'SELECT * FROM orgaos ORDER BY id'):
        aplicar(o['banco'], MIG_ORGAO)
        ident = 'identidade completada' if completar_identidade(o['banco'], o['slug'], o['tipo']) else 'identidade sem mudança'
        nf = configurar_fontes(o['id'], o['slug'])
        ni, nfp = configurar_painel(o)
        nf += nfp
        if ni:
            print(f"  painel de indicadores: {ni} indicador(es) novo(s) no catálogo")
        if o['tipo'] == 'legislativo':
            from . import legislativo
            na = legislativo.vincular_autores_antigos(o['banco'])
            if na:
                print(f"  {na} proposição(ões) antiga(s) com autoria vinculada aos vereadores")
        print(f"{o['slug']} ({o['banco']}): {nf} fonte(s) nova(s) · migrações {', '.join(m.name for m in MIG_ORGAO)} · {ident} · layout: {atualizar_layout(o['banco'], o['tipo'])}")
    from . import remessa
    np = remessa.configurar_pares()
    if np:
        print(f'{np} integração(ões) entre órgãos criada(s) (token guardado no banco de controle)')
    print('pronto.')

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'init'
    if cmd == 'init':
        init()
        db.fechar()
    elif cmd == 'atualizar':
        atualizar()
        db.fechar()
    elif cmd == 'orgao':
        o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE slug=%s', (sys.argv[2],))
        aplicar(o['banco'], MIG_ORGAO)
        print('esquema aplicado em', o['banco'])
        db.fechar()
