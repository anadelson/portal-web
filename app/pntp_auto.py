"""Verificações automáticas da autoavaliação PNTP (ver pntp.py): o que o portal consegue medir sozinho, com os dados publicados.

Cada função devolve {'itens': {item: bool}, 'det': texto, 'link': caminho} quando o portal mede o critério inteiro, ou
{'itens': None, 'dica': texto} quando o critério depende de marcação do controle interno (a dica mostra o que o portal já
sabe, para ajudar a marcar). Regra: só é "automático" o que o portal comprova inteiro; o resto vai para marcação.
Exigências conferidas na Cartilha PNTP 2026 (Atricon) e no material de apoio dos Tribunais de Contas."""
from datetime import timedelta
from . import db, legislativo as L

PROPRIOS = ('Decreto', 'Portaria', 'Resolução', 'Decreto Legislativo', 'Instrução Normativa', 'Ato da Mesa')


def _vazio(v):
    s = str(v or '').strip()
    return not s or s.startswith('[')  # "[nome do encarregado de dados]" e afins são marcadores do piloto, não dado real


def _anos(b, tabela, hoje, col='ano'):
    anos = {r['a'] for r in db.todos(b, f'SELECT DISTINCT {col} a FROM {tabela} WHERE {col} BETWEEN %s AND %s', (hoje.year - 3, hoje.year - 1))}
    return [a for a in range(hoje.year - 3, hoje.year) if a not in anos]


def _base(ctx, nome, tabela, data_sql, campos=None, filtro=True, filtro_falta=''):
    """Critério de uma base da transparência: disponibilidade (ano corrente com os campos exigidos), atualidade (≤ 30 dias),
    série (os 3 anos anteriores), gravação (CSV/JSON, sempre) e filtro."""
    b, hoje = ctx['banco'], ctx['hoje']
    if nome not in ctx['bases']:
        return dict(itens={i: False for i in ('disponibilidade', 'atualidade', 'serie', 'gravacao', 'filtro')},
                    det='O portal ainda não oferece esta base para este tipo de órgão.', link='/transparencia')
    r = db.um(b, f'SELECT count(*) n, max({data_sql}) d FROM {tabela} WHERE ano=%s', (hoje.year,))
    falta_ano = _anos(b, tabela, hoje)
    disp = bool(r['n']) and not campos
    atual = bool(r['d']) and r['d'] >= hoje - timedelta(days=30)
    partes = [f"{r['n']} registros de {hoje.year}" + (f", o mais recente de {r['d']:%d/%m/%Y}" if r['d'] else '')]
    if campos:
        partes.append(f'falta: {campos}')
    if falta_ano:
        partes.append('sem ' + ', '.join(map(str, falta_ano)) + ' (série histórica)')
    if not filtro:
        partes.append(f'filtro incompleto: {filtro_falta}')
    return dict(itens=dict(disponibilidade=disp, atualidade=atual, serie=not falta_ano, gravacao=True, filtro=filtro), det='; '.join(partes) + '.',
                link=f"/transparencia/{nome}")


def _dimensao20(ctx):
    """Critérios 20.1–20.11 a partir da autoavaliação legislativa que já existia (legislativo.pntp)."""
    res = {}
    for cod, _, sit, det, link in L.pntp(ctx['banco'], ctx['hoje']):
        ok = sit == 'atendido'
        res[cod] = dict(itens={i: ok for i in ('disponibilidade', 'atualidade', 'serie', 'gravacao', 'filtro')},
                        det=('' if ok else ('Parcial: ' if sit == 'parcial' else 'Pendente: ')) + det, link=link)
    return res


def medir(orgao, hoje, rotas=()):
    from . import transparencia as TR
    b = orgao['banco']
    ident = db.cfg(b, 'identidade', {}) or {}
    ctx = dict(banco=b, hoje=hoje, tipo=orgao['tipo'], bases=set(TR.bases_do(orgao)))
    exe = orgao['tipo'] == 'executivo'
    um = lambda sql, *p: db.um(b, sql, p)
    sim = lambda det, link: dict(itens={i: True for i in ('disponibilidade', 'atualidade', 'serie', 'gravacao', 'filtro')}, det=det, link=link)
    nao = lambda det, link='': dict(itens={i: False for i in ('disponibilidade', 'atualidade', 'serie', 'gravacao', 'filtro')}, det=det, link=link)
    dica = lambda t: dict(itens=None, dica=t)
    R = {}

    # 1. Informações prioritárias
    R['1.1'] = sim(f"Sítio próprio do órgão ({orgao.get('dominio') or 'domínio do órgão'}).", '/')
    R['1.2'] = sim('Portal da transparência próprio, dentro do sítio.', '/transparencia')
    R['1.3'] = sim('Link “Portal da Transparência” no menu e no rodapé de todas as páginas, inclusive a inicial.', '/')
    busca = '/busca' in rotas
    R['1.4'] = sim('Busca geral no sítio e na transparência.', '/busca') if busca else nao(
        'A busca do topo procura só na ' + ('Carta de Serviços' if exe else 'lista de proposições') + '; o PNTP exige busca no sítio e no portal da transparência.', '/')

    # 2. Informações institucionais
    sec = um('SELECT count(*) n, count(*) FILTER (WHERE resumo<>%s) resumo, count(*) FILTER (WHERE responsavel_id IS NOT NULL) resp FROM secretarias WHERE ativa', '')
    org = (ident.get('organograma') or {}).get('url')
    R['2.1'] = dica(f"{sec['n']} unidades ativas em “Governo”; organograma {'publicado' if org else 'não publicado'}. Exige também a norma que institui a estrutura e a data de atualização.")
    R['2.2'] = dica(f"{sec['resumo']} de {sec['n']} unidades com descrição das competências.")
    R['2.3'] = dica(f"{sec['resp']} de {sec['n']} unidades com responsável indicado.")
    falta = [n for k, n in (('endereco', 'endereço'), ('telefone', 'telefone'), ('email', 'e-mail')) if _vazio(ident.get(k))]
    R['2.4'] = nao('Falta no cadastro do órgão: ' + ', '.join(falta) + '.', '/admin/identidade') if falta else sim('Endereço, telefone e e-mail no rodapé de todas as páginas.', '/')
    R['2.5'] = nao('Horário de atendimento não cadastrado.', '/admin/identidade') if _vazio(ident.get('horario')) else sim(f"Horário no rodapé: {ident['horario']}.", '/')
    lg = um('SELECT count(*) FILTER (WHERE ano=%s) n, max(data) d FROM legislacao WHERE tipo = ANY(%s)', hoje.year, list(PROPRIOS))
    falta_ano = [a for a in range(hoje.year - 3, hoje.year) if not um('SELECT 1 x FROM legislacao WHERE tipo = ANY(%s) AND ano=%s LIMIT 1', list(PROPRIOS), a)]
    R['2.6'] = dict(itens=dict(disponibilidade=bool(lg['n']), atualidade=bool(lg['d']) and lg['d'] >= hoje - timedelta(days=30), serie=not falta_ano, filtro=True),
                    det=f"{lg['n']} atos próprios (decretos, portarias, resoluções) de {hoje.year} na Legislação" + (f"; sem {', '.join(map(str, falta_ano))}" if falta_ano else '') + '.',
                    link='/legislacao')
    R['2.7'] = dica('O portal não tem seção de perguntas frequentes.')
    redes = ident.get('redes_v2') or ident.get('redes')
    R['2.8'] = sim('Links das redes sociais no rodapé.', '/') if redes else nao('Nenhuma rede social cadastrada.', '/admin/identidade?aba=redes')
    R['2.9'] = sim('Botão “Radar da Transparência Pública” no rodapé de todas as páginas.', '/')

    # 3–4. Receita e despesa
    if exe:
        tem_mes = bool(um('SELECT 1 x FROM receitas WHERE ano=%s AND mes BETWEEN 1 AND 12 LIMIT 1', hoje.year))
        R['3.1'] = _base(ctx, 'receitas', 'receitas', 'coletado_em::date', filtro=tem_mes, filtro_falta='a fonte só traz o acumulado do ano (sem mês)')
        R['3.2'] = dict(R['3.1'], det='Natureza da receita com código e descrição. ' + R['3.1']['det'])
        R['3.3'] = dica('O portal não tem a lista da dívida ativa.')
    else:
        r = um("SELECT count(*) n, max(data) d FROM transferencias WHERE ano=%s", hoje.year)
        falta_ano = _anos(b, 'transferencias', hoje)
        R['3.1'] = dict(itens=dict(disponibilidade=bool(r['n']), atualidade=bool(r['d']) and r['d'] >= hoje - timedelta(days=30), serie=not falta_ano, gravacao=True, filtro=True),
                        det=f"Duodécimos de {hoje.year}: {r['n']} movimentos" + (f"; sem {', '.join(map(str, falta_ano))}" if falta_ano else '') + '.', link='/transparencia/transferencias')
    R['4.1'] = _base(ctx, 'despesas', 'despesas_unidade', 'coletado_em::date', filtro=False, filtro_falta='sem filtro por mês')
    R['4.2'] = _base(ctx, 'empenhos', 'empenhos', 'data', campos='subfunção (há unidade, função, natureza e fonte)')
    R['4.3'] = _base(ctx, 'empenhos', 'empenhos', 'data', campos='descrição do bem ou serviço (objeto) do empenho', filtro=False, filtro_falta='sem busca por CNPJ do credor')

    # 6–7. Pessoal e diárias
    R['6.1'] = _base(ctx, 'servidores', 'servidores', 'make_date(ano, mes, 1)', campos='carga horária e data de exoneração/inativação')
    R['6.2'] = _base(ctx, 'servidores', 'servidores', "(make_date(ano, mes, 1) + interval '1 month' - interval '1 day')::date")
    if exe:
        R['7.1'] = _base(ctx, 'diarias', 'diarias', 'data', campos='número de diárias, período do afastamento e destino')
    else:
        decl = (db.cfg(b, 'diarias_declaracao') or {}).get(str(hoje.year))
        r = um('SELECT count(*) n, max(inicio) d FROM diarias_legislativo WHERE ano=%s', hoje.year)
        if decl and not r['n']:
            R['7.1'] = sim(f'Declaração de inexistência de diárias em {hoje.year}: {decl}', '/transparencia/diarias-camara')
        else:
            R['7.1'] = dict(_base(ctx, 'diarias-camara', 'diarias_legislativo', 'inicio'), link='/transparencia/diarias-camara')

    # 8–9. Licitações e contratos
    R['8.1'] = _base(ctx, 'licitacoes', 'licitacoes', 'data')
    n_pncp = um("SELECT count(*) n FROM licitacoes WHERE fonte='pncp' AND link<>''")['n']
    for k in ('8.2', '8.3', '8.4', '8.5'):
        R[k] = dica(f'{n_pncp} licitações com link para o PNCP, onde costumam estar os documentos; confira se a íntegra está lá.' if n_pncp else 'Sem links para documentos das licitações.')
    R['8.6'] = dica('O portal não mostra o Plano de Contratações Anual na seção de licitações.')
    R['9.1'] = _base(ctx, 'contratos', 'contratos', 'assinatura', campos='aditivos de cada contrato')
    R['9.4'] = _base(ctx, 'ordem-cronologica', 'ordem_cronologica', 'pagamento')

    # 11. Planejamento e prestação de contas (dica com o que o portal já lê do Siconfi)
    rgf = um("SELECT max(ano * 10 + periodo) p FROM relatorios_fiscais WHERE demonstrativo='RGF'")['p']
    rreo = um("SELECT max(ano * 10 + periodo) p FROM relatorios_fiscais WHERE demonstrativo='RREO'")['p']
    R['11.5'] = dica(f"O portal mostra dados do RGF lidos do Siconfi (último: {rgf % 10}º período de {rgf // 10}); confira se o relatório completo está publicado." if rgf else 'Sem RGF no portal.')
    if exe:
        R['11.6'] = dica(f"O portal mostra dados do RREO lidos do Siconfi (último: {rreo % 10}º bimestre de {rreo // 10}); confira se o relatório completo está publicado." if rreo else 'Sem RREO no portal.')

    # 12. SIC
    from . import atendimento as AT
    at = AT.conf(b)
    R['12.1'] = sim(f"Página do e-SIC com a unidade responsável: {at['unidade']}.", '/e-sic') if at['unidade'] else nao('Unidade responsável pelo SIC não informada (Painel → e-SIC e Ouvidoria → Configuração).', '/admin/atendimento/configuracao')
    falta = [n for k, n in (('endereco', 'endereço'), ('telefone', 'telefone'), ('email', 'e-mail'), ('horario', 'horário')) if _vazio(ident.get(k))]
    R['12.2'] = nao('Falta no cadastro do órgão: ' + ', '.join(falta) + '.', '/e-sic') if falta else sim('Endereço, telefone, e-mail e horário na página do e-SIC.', '/e-sic')
    R['12.3'] = sim('Formulário eletrônico de pedido de informação, com protocolo e código de acesso para acompanhar.', '/e-sic')
    R['12.4'] = sim('O pedido exige só nome e e-mail para a resposta, sem documentos nem motivo.', '/e-sic')
    R['12.5'] = sim(f"Norma local da LAI na página do e-SIC: {at['norma_nome']}.", '/e-sic') if at['norma_nome'] and at['norma_url'] else nao('Norma local que regulamenta a LAI não informada (nome e endereço) na Configuração do atendimento.', '/admin/atendimento/configuracao')
    if at['autoridade1_cargo']:
        R['12.6'] = sim(f"Prazos (20 + 10 dias; recurso em 10, decisão em 5), procedimento e autoridades ({at['autoridade1_cargo']}" + (f"; 2ª instância: {at['autoridade2_cargo']}" if at['autoridade2_cargo'] else '') + ') na página do e-SIC.', '/e-sic')
    else:
        R['12.6'] = nao('A página mostra prazos e procedimento, mas falta a autoridade de recurso (Configuração do atendimento).', '/admin/atendimento/configuracao')
    R['12.7'] = sim('Relatório estatístico (recebidos, atendidos, indeferidos, recursos, perfil dos solicitantes) calculado dos registros, com CSV e JSON.', '/e-sic/estatisticas')
    n_cl = um('SELECT count(*) FILTER (WHERE desclassificada_em IS NULL) a, count(*) FILTER (WHERE desclassificada_em >= %s) d FROM info_classificadas', hoje - timedelta(days=365))
    declarou = bool(at['sem_classificadas'])
    R['12.8'] = sim(f"{n_cl['a']} informação(ões) classificada(s) publicada(s) com grau, assunto, categoria, fundamento e prazo." if n_cl['a'] else 'Declaração de que o órgão não tem informação classificada.', '/e-sic/informacoes-classificadas') \
        if (n_cl['a'] or declarou) else nao('Cadastre as informações classificadas ou declare que não há nenhuma (Configuração do atendimento).', '/admin/atendimento/classificadas')
    R['12.9'] = sim(f"{n_cl['d']} desclassificada(s) nos últimos 12 meses." if n_cl['d'] else 'Lista de desclassificadas dos últimos 12 meses publicada (nenhuma no período).', '/e-sic/informacoes-classificadas') \
        if (n_cl['a'] or n_cl['d'] or declarou) else nao('Lista de desclassificadas depende do cadastro das classificadas ou da declaração de inexistência.', '/admin/atendimento/classificadas')

    # 13. Acessibilidade (recursos do modelo do portal, em todas as páginas)
    R['13.1'] = sim('Símbolo e página de acessibilidade em destaque no topo.', '/acessibilidade')
    R['13.2'] = sim('Caminho da página (“Você está em”) nas páginas internas.', '/transparencia')
    R['13.3'] = sim('Botão de alto contraste no topo.', '/')
    R['13.4'] = sim('Botões A+ e A− no topo.', '/')
    R['13.5'] = sim('Mapa do site no rodapé.', '/mapa-do-site')

    # 14. Ouvidoria
    R['14.1'] = nao('Falta no cadastro do órgão: ' + ', '.join(falta) + '.', '/ouvidoria') if falta else sim('Endereço, telefone e horário na página da Ouvidoria.', '/ouvidoria')
    R['14.2'] = sim('Formulário eletrônico de manifestação (reclamação, sugestão, elogio, denúncia, solicitação).', '/ouvidoria')
    try:
        ns = um("SELECT count(*) n FROM servicos WHERE publicado_dados IS NOT NULL AND situacao<>'arquivado'")['n']
    except Exception:
        ns = 0
    R['14.3'] = sim(f'{ns} serviços publicados na Carta de Serviços.', '/servicos') if ns else nao('Nenhuma ficha publicada na Carta de Serviços.', '/servicos')

    # 15. LGPD e governo digital
    if _vazio(ident.get('encarregado')) or _vazio(ident.get('encarregado_email')):
        R['15.1'] = nao('Nome ou e-mail do encarregado de dados não cadastrado (aparece o marcador do piloto).', '/privacidade#encarregado')
    else:
        R['15.1'] = sim(f"Encarregado: {ident['encarregado']}.", '/privacidade#encarregado')
    R['15.2'] = sim('Política de privacidade publicada.', '/privacidade')
    R['15.4'] = sim('Dados abertos em CSV e JSON, com API e regras de uso na página.', '/dados-abertos')
    R['15.6'] = dica('A Ouvidoria publica o resultado das avaliações dos atendimentos em /ouvidoria/relatorio; confira se basta como pesquisa de satisfação do órgão.')

    if not exe:
        R.update(_dimensao20(ctx))
    return R
