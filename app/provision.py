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
from .catalogo import MODULOS, COMECA_OCULTO, LAYOUT_PADRAO, LAYOUT_PADRAO_V1, LAYOUT_PADRAO_V2, LAYOUT_PADRAO_V3, serve
from .security import hash_senha

AQUI = Path(__file__).parent
MIGRACOES = sorted((AQUI / 'migrations').glob('[0-9][0-9][0-9]_*.sql'))
MIG_PLAT = [m for m in MIGRACOES if 'plataforma' in m.stem]
MIG_ORGAO = [m for m in MIGRACOES if 'plataforma' not in m.stem]
MIG_LOCAL = sorted((Path(__file__).parent / 'migrations_local').glob('*.sql'))  # banco local do nó (papel "no")

def criar_banco(nome: str):
    with psycopg.connect(config.dsn('postgres'), autocommit=True) as c:
        if not c.execute('SELECT 1 FROM pg_database WHERE datname=%s', (nome,)).fetchone():
            c.execute(f'CREATE DATABASE "{nome}"')
            print('banco criado:', nome)

def aplicar(banco: str, migracoes):
    with psycopg.connect(config.dsn(banco), autocommit=True) as c:
        for m in migracoes:
            c.execute(m.read_text(encoding='utf-8'))

# Identidade visual (Fase 3): valores padrão por tipo de órgão; cada órgão pode trocar tudo em /admin/identidade.
VISUAL_PADRAO = {
    'executivo': {'prefixo': 'Poder Executivo', 'cor_destaque': '#F0B429', 'hero_rotulo': 'Portal oficial da Prefeitura',
                  'hero_titulo': 'O que você precisa hoje?', 'hero_texto': 'Peça serviços, acompanhe seus pedidos e veja como a Prefeitura usa o dinheiro público.',
                  'busca_dica': 'Ex.: IPTU, creche, edital, diário oficial', 'mais_buscados': ['IPTU', 'Vacinação', 'Concurso', 'Nota fiscal']},
    'legislativo': {'prefixo': 'Poder Legislativo', 'cor_destaque': '#F7C948', 'hero_rotulo': 'Portal oficial da Câmara Municipal',
                    'hero_titulo': 'Acompanhe o trabalho dos vereadores', 'hero_texto': 'Sessões, projetos, votações e gastos da Câmara, num só lugar e em linguagem simples.',
                    'busca_dica': 'Busque projeto, indicação ou vereador', 'mais_buscados': []},
}
# Cabeçalho no padrão da Câmara (12/11/2026): linha pequena com o Poder e o nome COMPLETO em destaque.
# Órgão que ainda tem o prefixo antigo padrão passa para o novo; prefixo escolhido pelo órgão não muda.
PREFIXO_ANTIGO = {'executivo': 'Prefeitura Municipal de'}
# Dados do piloto (Prefeitura e Câmara de Borá): ficam em seeds/piloto_bora.json, não no código.
# O código é neutro: um órgão novo nasce só com o que vier do cadastro no console e com os padrões por tipo de órgão.
PILOTO = json.loads((AQUI / 'seeds' / 'piloto_bora.json').read_text(encoding='utf-8'))['orgaos']
IDENT = {o['slug']: o['identidade'] for o in PILOTO}
IDENT_VISUAL = {o['slug']: o['identidade_visual'] for o in PILOTO}
FONTES_PADRAO = {o['slug']: o['fontes'] for o in PILOTO}
DIARIO_PADRAO = {o['slug']: o['diario'] for o in PILOTO if o.get('diario')}

def completar_diario(banco, slug):
    """Lei de instituição e base legal do Diário do piloto (arquivo de dados), sem sobrescrever o que o órgão salvou."""
    novo = DIARIO_PADRAO.get(slug)
    if not novo:
        return
    conf = db.cfg(banco, 'diario', {}) or {}
    falta = {k: v for k, v in novo.items() if not conf.get(k)}
    if falta:
        db.set_cfg(banco, 'diario', dict(conf, **falta))

def configurar_fontes(oid, slug, fontes=None):
    """Cadastra as fontes do órgão (as do cadastro no console ou, para o piloto, as do arquivo de dados) se ainda não
    existirem — nunca sobrescreve a configuração feita."""
    n = 0
    for fonte, params in (fontes if fontes is not None else FONTES_PADRAO.get(slug, {})).items():
        r = db.exe(db.LOCAL, 'INSERT INTO fontes (orgao_id, fonte, params) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1', (oid, fonte, Jsonb(params)))
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
            fio = db.um(db.LOCAL, "SELECT params FROM fontes WHERE orgao_id=%s AND fonte='fiorilli'", (o['id'],))
            if not fio:
                continue
            params = {k: fio['params'][k] for k in ('base', 'empresa') if k in fio['params']}
        r = db.exe(db.LOCAL, 'INSERT INTO fontes (orgao_id, fonte, params, ativo) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING 1', (o['id'], fonte, Jsonb(params), ativo))
        nf += 1 if r else 0
    return novos, nf

def configurar_youtube(o):
    """Fonte "youtube" para todo órgão (Fase 8). Sem módulo de transmissão, canal ou chave, o coletor não faz nada."""
    n = 0
    for fonte in ('youtube', 'redes'):  # Fase 9: redes sociais (últimas publicações) — sem conta/credencial não faz nada
        r = db.exe(db.LOCAL, "INSERT INTO fontes (orgao_id, fonte, params, ativo) VALUES (%s,%s,'{}',TRUE) ON CONFLICT DO NOTHING RETURNING 1", (o['id'], fonte))
        n += 1 if r else 0
    return n

def completar_identidade(banco, slug, tipo):
    """Acrescenta à identidade do órgão as chaves visuais que ainda não existem (nunca sobrescreve o que o órgão definiu)."""
    ident = db.cfg(banco, 'identidade', {}) or {}
    novo = dict(VISUAL_PADRAO.get(tipo, {}))
    novo.update(IDENT_VISUAL.get(slug, {}))
    antiga = novo.pop('cor_antiga', None)
    mudou = False
    if ident.get('prefixo') and ident.get('prefixo') == PREFIXO_ANTIGO.get(tipo) and novo.get('prefixo') and novo['prefixo'] != ident['prefixo']:
        ident['prefixo'] = novo['prefixo']; mudou = True
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
    if atual in (LAYOUT_PADRAO_V1.get(tipo), LAYOUT_PADRAO_V2.get(tipo), LAYOUT_PADRAO_V3.get(tipo)):
        db.exe(banco, "DELETE FROM blocos WHERE pagina='home' AND chave <> ALL(%s)", ([k for k, _ in alvo],))
        for i, (k, reg) in enumerate(alvo):
            db.exe(banco, "INSERT INTO blocos (pagina, chave, regiao, ordem, visivel) VALUES ('home',%s,%s,%s,%s) ON CONFLICT (pagina, chave) DO UPDATE SET regiao=EXCLUDED.regiao, ordem=EXCLUDED.ordem", (k, reg, i, k not in COMECA_OCULTO))
        return 'padrão novo aplicado'
    usados = {k for k, _ in atual}
    novos = [(k, reg) for k, reg in alvo if k not in usados]
    for k, reg in novos:
        mx = db.um(banco, "SELECT coalesce(max(ordem),0)+1 n FROM blocos WHERE pagina='home' AND regiao<>'rodape'")['n']
        db.exe(banco, "INSERT INTO blocos (pagina, chave, regiao, ordem, visivel) VALUES ('home',%s,%s,%s,%s) ON CONFLICT DO NOTHING", (k, reg, mx, k not in COMECA_OCULTO))
    return f"{len(novos)} bloco(s) novo(s) acrescentado(s)" if novos else 'sem blocos novos'

ORGAOS = [(o['slug'], o['nome'], o['tipo'], (lambda o=o: config.env(o['dominio_env'], o['dominio_padrao'])), o['banco'], o['plano'], o['cor'], o['opcionais'])
          for o in PILOTO]

def registrar_orgao(slug, nome, tipo, dominio, banco, plano, cor, opcionais, municipio, ibge, inicio=None, fim=None,
                    identidade=None, fontes=None, email_admin=None, senha_admin=None):
    """Cadastra o órgão no banco de controle e prepara o banco dele (esquema, identidade, fontes, menus, layout e
    usuário administrador inicial). Idempotente para o piloto; para órgão novo, os dados vêm do cadastro no console."""
    oid = registrar_controle(slug, nome, tipo, dominio, banco, plano, cor, opcionais, municipio, ibge, inicio, fim)
    preparar_orgao(db.um(db.PLATAFORMA, 'SELECT * FROM orgaos WHERE id=%s', (oid,)), identidade=identidade, fontes=fontes, email_admin=email_admin,
                   senha_hash=hash_senha(senha_admin or config.SENHA_INICIAL_ADMIN), avisar_senha=not senha_admin)
    return oid

def registrar_controle(slug, nome, tipo, dominio, banco, plano, cor, opcionais, municipio, ibge, inicio=None, fim=None):
    """Parte da GESTÃO: o órgão, o contrato e os módulos no banco de controle. Devolve o id."""
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
    return oid

def preparar_orgao(o, identidade=None, fontes=None, email_admin=None, senha_hash=None, avisar_senha=False):
    """Parte de QUEM HOSPEDA o órgão (esta VPS no papel "tudo"; o nó, pela ordem "criar_orgao"): banco do órgão,
    esquema, identidade, integrações, menus, layout e administrador inicial. Recebe só o HASH da senha inicial.
    Idempotente: não sobrescreve identidade, layout nem usuários que já existam."""
    oid, slug, nome, tipo, dominio, banco, cor = o['id'], o['slug'], o['nome'], o['tipo'], o['dominio'], o['banco'], o.get('cor')
    criar_banco(banco)
    aplicar(banco, MIG_ORGAO)
    if not db.cfg(banco, 'identidade'):
        db.set_cfg(banco, 'identidade', IDENT.get(slug) or identidade or {'nome': nome, 'cor': cor})
    completar_identidade(banco, slug, tipo)
    completar_diario(banco, slug)
    configurar_fontes(oid, slug, fontes)
    configurar_painel(o)
    configurar_youtube(o)
    from . import menus as MN, fase8 as F8
    MN.semear(banco, tipo, (db.cfg(banco, 'identidade', {}) or {}).get('nome_curto', ''))
    F8.migrar_conheca(banco, db.cfg(banco, 'identidade', {}))
    if not db.um(banco, 'SELECT 1 FROM blocos LIMIT 1'):
        for i, (k, reg) in enumerate(LAYOUT_PADRAO[tipo]):
            db.exe(banco, 'INSERT INTO blocos (pagina, chave, regiao, ordem, visivel) VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING', ('home', k, reg, i, k not in COMECA_OCULTO))
    if not db.um(banco, 'SELECT 1 FROM usuarios LIMIT 1'):
        email = email_admin or f'admin@{dominio}'
        db.exe(banco, "INSERT INTO usuarios (nome, email, setor, perfil, escopo, senha_hash) VALUES (%s,%s,%s,'admin','Órgão inteiro',%s)", ('Administrador do órgão', email, 'Administração', senha_hash or hash_senha(config.SENHA_INICIAL_ADMIN)))
        if avisar_senha:
            print(f'  usuário inicial: {email} (senha = SENHA_INICIAL_ADMIN; troque no primeiro acesso)')
    return oid

def seed_camara(banco, arquivo):
    """Dados reais da Câmara do piloto (legislaturas, vereadores, proposições, sessões), do arquivo em seeds/."""
    if db.um(banco, 'SELECT 1 FROM vereadores LIMIT 1'):
        return
    d = json.loads((AQUI / 'seeds' / arquivo).read_text(encoding='utf-8'))
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

def seed_prefeitura(banco, itens):
    """Conteúdos-exemplo do piloto (marcados como exemplo), do arquivo de dados."""
    if db.um(banco, 'SELECT 1 FROM conteudos LIMIT 1'):
        return
    hoje = config.hoje()
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
    for o in PILOTO:
        print('órgão:', o['slug'])
        registrar_orgao(o['slug'], o['nome'], o['tipo'], config.env(o['dominio_env'], o['dominio_padrao']), o['banco'], o['plano'], o['cor'], o['opcionais'], o['municipio'], o['ibge'])
        if o.get('conteudos_exemplo'):
            seed_prefeitura(o['banco'], o['conteudos_exemplo'])
        if o.get('dados_camara'):
            seed_camara(o['banco'], o['dados_camara'])
    from . import remessa
    np = remessa.configurar_pares()
    if np:
        print(f'{np} integração(ões) entre órgãos criada(s) (token guardado no banco de controle)')
    if config.PAPEL != 'no':
        from . import licenca
        print('licenças: chave da gestão', licenca.garantir_chaves()[0])  # só a impressão digital
    print('pronto.')

def atualizar():
    """Atualização sem perda: migrações idempotentes em todos os bancos, catálogo de módulos,
    chaves novas da identidade e blocos novos da página inicial.
    Papel "no" (nó de portais): não há banco de controle; prepara o banco local e os bancos dos órgãos das licenças recebidas."""
    from . import orgaos as ORG
    if config.PAPEL == 'no':
        criar_banco(db.LOCAL)
        aplicar(db.LOCAL, MIG_LOCAL)
        print(f'{db.LOCAL} (banco local do nó): migrações', ', '.join(m.name for m in MIG_LOCAL))
    else:
        aplicar(db.PLATAFORMA, MIG_PLAT)
        print('plataforma: migrações', ', '.join(m.name for m in MIG_PLAT))
        for m in MODULOS:
            db.exe(db.PLATAFORMA, 'INSERT INTO modulos VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT (chave) DO UPDATE SET nome=EXCLUDED.nome, descricao=EXCLUDED.descricao, oferta=EXCLUDED.oferta, serve=EXCLUDED.serve, depende=EXCLUDED.depende', m)
    for o in ORG.todos(ativos=False):
        aplicar(o['banco'], MIG_ORGAO)
        ident = 'identidade completada' if completar_identidade(o['banco'], o['slug'], o['tipo']) else 'identidade sem mudança'
        completar_diario(o['banco'], o['slug'])
        nf = configurar_fontes(o['id'], o['slug'])
        from . import menus as MN, fase8 as F8
        nm = MN.semear(o['banco'], o['tipo'], (db.cfg(o['banco'], 'identidade', {}) or {}).get('nome_curto', ''))
        npf = F8.migrar_conheca(o['banco'], db.cfg(o['banco'], 'identidade', {}))
        from . import municipio
        municipio.migrar(o['banco'], db.cfg(o['banco'], 'identidade', {}))
        nd1 = F8.mover_exemplos_para_comunicados(o['banco'])
        if nd1:
            print(f"  ajustes 8: {nd1} conteúdo(s)-exemplo que não eram notícia viraram comunicados-exemplo")
        if nm or npf:
            print(f"  fase 8: {nm} item(ns) de menu e {npf} perfil(is) do Conheça criados")
        ni, nfp = configurar_painel(o)
        nf += nfp + configurar_youtube(o)
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
    if config.PAPEL != 'no':
        from . import licenca
        print('licenças: chave da gestão', licenca.garantir_chaves()[0])  # só a impressão digital
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
