"""Provisionamento: cria o banco de controle, os bancos dos órgãos e os dados iniciais.

Uso:
  python -m app.provision init        # primeira instalação (idempotente)
  python -m app.provision orgao SLUG  # aplica o esquema de novo num órgão existente
"""
import json, sys
from datetime import date
from pathlib import Path
import psycopg
from psycopg.types.json import Jsonb
from . import config, db
from .catalogo import MODULOS, LAYOUT_PADRAO, serve
from .security import hash_senha

AQUI = Path(__file__).parent
SQL_PLAT = (AQUI / 'migrations' / '001_plataforma.sql').read_text(encoding='utf-8')
SQL_ORGAO = (AQUI / 'migrations' / '002_orgao.sql').read_text(encoding='utf-8')

def criar_banco(nome: str):
    with psycopg.connect(config.dsn('postgres'), autocommit=True) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (nome,)).fetchone():
            c.execute(f'CREATE DATABASE "{nome}"')
            print('banco criado:', nome)

def aplicar(banco: str, sql: str):
    with psycopg.connect(config.dsn(banco), autocommit=True) as c:
        c.execute(sql)

IDENT = {
    'pm-bora': {'nome': 'Prefeitura Municipal de Borá', 'endereco': 'Praça Santo Antonio, 10 · Borá (SP) · CEP 19740-005', 'telefone': '(18) 3367-1103', 'email': 'pmbora@bora.sp.gov.br', 'cnpj': '44.544.906/0001-42', 'horario': 'Segunda a sexta, 8h às 17h', 'encarregado': '[nome do encarregado de dados]', 'encarregado_email': '[e-mail do encarregado]', 'cor': '#1D4E89'},
    'cm-bora': {'nome': 'Câmara Municipal de Borá', 'endereco': 'Rua Vereador Herculano Azevedo, 10 · Centro · Borá (SP) · CEP 19740-000', 'telefone': '(18) 3367-1146', 'email': 'camara@camarabora.sp.gov.br', 'cnpj': '[CNPJ da Câmara]', 'horario': 'Segunda a sexta, 9h às 11h e 13h às 17h', 'encarregado': '[nome do encarregado de dados]', 'encarregado_email': '[e-mail do encarregado]', 'cor': '#2F5233'},
}

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
    aplicar(banco, SQL_ORGAO)
    if not db.cfg(banco, 'identidade'):
        db.set_cfg(banco, 'identidade', IDENT.get(slug, {'nome': nome, 'cor': cor}))
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
    aplicar(db.PLATAFORMA, SQL_PLAT)
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
    print('pronto.')

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'init'
    if cmd == 'init':
        init()
        db.fechar()
    elif cmd == 'orgao':
        o = db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE slug=%s', (sys.argv[2],))
        aplicar(o['banco'], SQL_ORGAO)
        print('esquema aplicado em', o['banco'])
        db.fechar()
