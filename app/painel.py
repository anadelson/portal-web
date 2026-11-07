"""Painel de indicadores (módulo opcional "bi"): catálogo, séries de valores, formatação, gráficos SVG e exportação.

Regras de dados (Docs/PEDIDO-FASE7.md):
- nenhum número inventado ou estimado pelo portal: todo valor vem de um coletor (fonte oficial) ou de lançamento
  manual com motivo e auditoria;
- cada indicador mostra fonte, período de referência e data da última atualização; se a última coleta falhou,
  o último valor válido continua no ar com o aviso "dado de <data>"; indicador sem nenhum valor não aparece;
- LGPD: só agregados; contagens de pessoas abaixo de 5 aparecem como "menos de 5" (telas, gráficos e downloads).
"""
import calendar, csv, io, json, zipfile
from datetime import date, datetime
from decimal import Decimal
from xml.sax.saxutils import escape
from markupsafe import Markup
from psycopg.types.json import Jsonb
from . import config, db

TEMAS = [('fin', 'Dinheiro público'), ('cont', 'Contratações'), ('saude', 'Saúde'), ('edu', 'Educação'),
         ('social', 'Assistência social'), ('mun', 'Município e gestão')]
TEMA_NOME = dict(TEMAS)
BASE_LEGAL = 'LRF (LC 101/2000), art. 48; LAI (Lei 12.527/2011), arts. 7º e 8º; Lei 14.129/2021 (governo digital e dados abertos).'
SUPRESSAO = 5
MAX_DESTAQUES = 4
MESES = ['jan', 'fev', 'mar', 'abr', 'mai', 'jun', 'jul', 'ago', 'set', 'out', 'nov', 'dez']

# ---------- catálogo padrão ----------
# Textos em linguagem simples e neutros (sem tom de propaganda: valem também no período eleitoral, classe "transp").
_IBGE = 'https://servicodados.ibge.gov.br/api/'
_SICONFI = 'https://apidatalake.tesouro.gov.br/ords/siconfi/tt/rreo?an_exercicio={ano}&nr_periodo=6&co_tipo_demonstrativo=RREO&no_anexo=RREO-Anexo%2014&id_ente={ibge}'
_FIO = 'Sistema contábil da Prefeitura (dados abertos)'
_INEP_PL = 'https://download.inep.gov.br/ideb/resultados/divulgacao_{etapa}_municipios_{ano}.zip'
_PEND_MDS = 'Fonte do MDS (MI Social) fora do ar desde 21/10/2026 (manutenção de segurança). O conector está pronto e desligado; ligue a fonte "mds" no console quando o serviço voltar e os nomes dos campos forem confirmados.'

def _i(chave, tema, nome, descricao, unidade, formato, fonte, fonte_link, periodicidade, coletor, ordem, casas=0, meta=None, meta_base_legal='',
       sentido='neutro', suprimir=False, base_legal='', pendente='', modo='automatico', destaque=False, reserva=False, alternavel=False):
    # reserva: aceita lançamento manual mesmo com fonte automática; alternavel: o administrador escolhe automático ou manual
    return dict(chave=chave, tema=tema, nome=nome, descricao=descricao, unidade=unidade, formato=formato, casas=casas, fonte=fonte, fonte_link=fonte_link,
                periodicidade=periodicidade, modo=modo, coletor=coletor, pendente=pendente, meta=meta, meta_base_legal=meta_base_legal, sentido=sentido,
                suprimir=suprimir, base_legal=base_legal, ordem=ordem, destaque=destaque, reserva=reserva or alternavel, alternavel=alternavel)

PEND_IEGM = ('Consulta sem documentação oficial do painel do TCESP (pode mudar sem aviso), com o acesso anônimo publicado pelo próprio Tribunal '
             '(variáveis IEGM_USUARIO e IEGM_SENHA no .env). Em modo manual, lance a faixa a partir do resultado publicado pelo Tribunal.')
_IEGM = [('gestao_iegm', 'IEG-M — resultado geral'), ('gestao_iegm_educ', 'IEG-M — educação (i-Educ)'), ('gestao_iegm_saude', 'IEG-M — saúde (i-Saúde)'),
         ('gestao_iegm_planej', 'IEG-M — planejamento (i-Planejamento)'), ('gestao_iegm_fiscal', 'IEG-M — gestão fiscal (i-Fiscal)'),
         ('gestao_iegm_amb', 'IEG-M — meio ambiente (i-Amb)'), ('gestao_iegm_cidade', 'IEG-M — cidades protegidas (i-Cidade)'), ('gestao_iegm_ti', 'IEG-M — governança de TI (i-Gov TI)')]

CATALOGO = [
    # Dinheiro público (dados do próprio órgão, coletor "painel")
    _i('fin_receita', 'fin', 'Receita arrecadada no ano', 'Quanto a Prefeitura recebeu no ano: tributos, repasses da União e do Estado e outras receitas, já descontadas as deduções para o FUNDEB. No ano corrente, o valor é acumulado até a data da coleta.',
       'R$', 'moeda', _FIO + '; anos anteriores: TCESP (Transparência Municipal)', '/transparencia/receitas', 'Diária (a cada hora, das 7h às 19h)', 'painel', 10,
       base_legal='LRF, art. 48-A, II; LAI, art. 8º, § 1º, II.', destaque=True),
    _i('fin_receita_prevista', 'fin', 'Receita arrecadada em relação à prevista', 'Parte da receita prevista no orçamento do ano que já foi arrecadada.',
       '%', 'pct', _FIO, '/transparencia/receitas', 'Diária (a cada hora, das 7h às 19h)', 'painel', 20, casas=1, base_legal='LRF, arts. 13 e 48-A, II.'),
    _i('fin_despesa_paga', 'fin', 'Despesa paga no ano', 'Quanto a Prefeitura já pagou no ano, somando todas as unidades do orçamento. No ano corrente, o valor é acumulado até a data da coleta.',
       'R$', 'moeda', _FIO, '/transparencia/despesas', 'Diária (a cada hora, das 7h às 19h)', 'painel', 30, base_legal='LRF, art. 48-A, I; LAI, art. 8º, § 1º, III.'),
    _i('fin_empenhada_dotacao', 'fin', 'Despesa empenhada em relação à dotação', 'Parte do orçamento autorizado do ano (dotação atualizada) que já foi comprometida com empenhos.',
       '%', 'pct', _FIO, '/transparencia/despesas', 'Diária (a cada hora, das 7h às 19h)', 'painel', 40, casas=1, base_legal='Lei 4.320/1964, arts. 58 a 60; LRF, art. 48-A, I.'),
    # Contratações (PNCP, gravado pela Fase 4)
    _i('cont_publicadas', 'cont', 'Contratações publicadas no PNCP', 'Quantas contratações (licitações, dispensas e inexigibilidades) o órgão publicou no Portal Nacional de Contratações Públicas no ano, com a divisão por modalidade.',
       'contratações', 'numero', 'Portal Nacional de Contratações Públicas (PNCP)', '/transparencia/licitacoes', 'A cada 6 horas', 'painel', 10,
       base_legal='Lei 14.133/2021, arts. 54, 72 (parágrafo único) e 174.'),
    _i('cont_valor', 'cont', 'Valor das contratações publicadas no PNCP', 'Soma dos valores das contratações publicadas no ano: o valor homologado ou, quando ainda não há, o valor estimado informado ao PNCP.',
       'R$', 'moeda', 'Portal Nacional de Contratações Públicas (PNCP)', '/transparencia/licitacoes', 'A cada 6 horas', 'painel', 20, base_legal='Lei 14.133/2021, arts. 94 e 174.'),
    _i('cont_dispensa', 'cont', 'Contratações por dispensa de licitação', 'Parte das contratações publicadas no ano que foram feitas por dispensa de licitação (Lei 14.133/2021, art. 75).',
       '%', 'pct', 'Portal Nacional de Contratações Públicas (PNCP)', '/transparencia/licitacoes', 'A cada 6 horas', 'painel', 30, casas=1, base_legal='Lei 14.133/2021, arts. 72 e 75.'),
    # Saúde
    _i('saude_minimo', 'saude', 'Aplicação em ações e serviços públicos de saúde', 'Parte da receita de impostos e transferências aplicada em saúde, declarada pela Prefeitura ao Tesouro Nacional no RREO. A lei exige no mínimo 15% no ano.',
       '%', 'pct', 'Siconfi — RREO, Anexo 14 (declarado pela Prefeitura)', _SICONFI, 'Bimestral', 'painel', 10, casas=2, meta=15,
       meta_base_legal='Constituição, art. 198, § 2º, III; LC 141/2012, art. 7º (mínimo de 15%).', sentido='maior', base_legal='LC 141/2012, arts. 7º e 31; LRF, art. 52.', destaque=True),
    _i('saude_estabelecimentos', 'saude', 'Estabelecimentos de saúde no CNES', 'Estabelecimentos de saúde do município registrados no Cadastro Nacional de Estabelecimentos de Saúde, por tipo.',
       'estabelecimentos', 'numero', 'CNES — Ministério da Saúde (API de dados abertos)', 'https://apidadosabertos.saude.gov.br/cnes/estabelecimentos?codigo_municipio={ibge6}', 'Mensal', 'cnes', 20,
       base_legal='Portaria de Consolidação MS 1/2017 (CNES); LAI, art. 8º.'),
    _i('saude_nascidos', 'saude', 'Nascidos vivos', 'Nascimentos registrados em cartório no ano, de mães residentes no município. Anos com menos de 5 nascimentos aparecem sem o número, para proteger as famílias.',
       'nascimentos', 'numero', 'IBGE — Estatísticas do Registro Civil (SIDRA, tabela 2612)', 'https://sidra.ibge.gov.br/tabela/2612', 'Anual', 'ibge', 30, suprimir=True,
       base_legal='Lei 6.015/1973 (registros públicos); LGPD, art. 6º, III.'),
    _i('saude_obitos', 'saude', 'Óbitos', 'Óbitos registrados em cartório no ano, de pessoas residentes no município. Anos com menos de 5 óbitos aparecem sem o número.',
       'óbitos', 'numero', 'IBGE — Estatísticas do Registro Civil (SIDRA, tabela 2654)', 'https://sidra.ibge.gov.br/tabela/2654', 'Anual', 'ibge', 40, suprimir=True,
       base_legal='Lei 6.015/1973 (registros públicos); LGPD, art. 6º, III.'),
    _i('saude_vacinacao', 'saude', 'Doses de vacina aplicadas', 'Total de doses aplicadas no município, por vacina.', 'doses', 'numero', 'Ministério da Saúde — PNI', '', 'Mensal', 'pni', 50, suprimir=True,
       pendente='Pendente de fonte estável: a API do PNI não filtra por município e devolve registros individuais. Conector pronto e desligado.'),
    # Educação
    _i('edu_mde_minimo', 'edu', 'Aplicação na manutenção e desenvolvimento do ensino', 'Parte da receita de impostos e transferências aplicada em educação, declarada pela Prefeitura no RREO. A Constituição exige no mínimo 25% no ano.',
       '%', 'pct', 'Siconfi — RREO, Anexo 14 (declarado pela Prefeitura)', _SICONFI, 'Bimestral', 'painel', 10, casas=2, meta=25,
       meta_base_legal='Constituição, art. 212 (mínimo de 25%).', sentido='maior', base_legal='Constituição, art. 212; Lei 9.394/1996, art. 69; LRF, art. 52.', destaque=True),
    _i('edu_fundeb_minimo', 'edu', 'FUNDEB aplicado na remuneração dos profissionais da educação', 'Parte dos recursos do FUNDEB usada para pagar os profissionais da educação básica em efetivo exercício. A lei exige no mínimo 70%.',
       '%', 'pct', 'Siconfi — RREO, Anexo 14 (declarado pela Prefeitura)', _SICONFI, 'Bimestral', 'painel', 20, casas=2, meta=70,
       meta_base_legal='Constituição, art. 212-A, XI; Lei 14.113/2020, art. 26 (mínimo de 70%).', sentido='maior', base_legal='Lei 14.113/2020, arts. 26 e 33.'),
    # IDEB e Saeb: planilhas oficiais do INEP por município (rede Pública, com a rede responsável escrita em cada valor)
    _i('edu_ideb_ai', 'edu', 'IDEB — anos iniciais do ensino fundamental (rede pública)', 'Índice de Desenvolvimento da Educação Básica calculado pelo INEP a cada dois anos, de 0 a 10: combina a aprovação dos alunos (indicador de rendimento) com o desempenho no Saeb. Valor da rede pública do município; a rede responsável aparece junto de cada resultado.',
       'nota (0 a 10)', 'nota', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_iniciais'), 'A cada dois anos', 'inep', 30, casas=1, sentido='maior',
       base_legal='Decreto 6.094/2007, art. 3º; Lei 13.005/2014 (PNE), meta 7.', reserva=True),
    _i('edu_saeb_mat_ai', 'edu', 'Saeb — Matemática, anos iniciais do ensino fundamental (rede pública)', 'Nota média dos estudantes na prova de Matemática do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_iniciais'), 'A cada dois anos', 'inep', 31, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_saeb_lp_ai', 'edu', 'Saeb — Língua Portuguesa, anos iniciais do ensino fundamental (rede pública)', 'Nota média dos estudantes na prova de Língua Portuguesa do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_iniciais'), 'A cada dois anos', 'inep', 32, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_ideb_af', 'edu', 'IDEB — anos finais do ensino fundamental (rede pública)', 'Índice de Desenvolvimento da Educação Básica calculado pelo INEP a cada dois anos, de 0 a 10: combina a aprovação dos alunos (indicador de rendimento) com o desempenho no Saeb. Valor da rede pública do município; a rede responsável aparece junto de cada resultado.',
       'nota (0 a 10)', 'nota', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_finais'), 'A cada dois anos', 'inep', 33, casas=1, sentido='maior',
       base_legal='Decreto 6.094/2007, art. 3º; Lei 13.005/2014 (PNE), meta 7.', reserva=True),
    _i('edu_saeb_mat_af', 'edu', 'Saeb — Matemática, anos finais do ensino fundamental (rede pública)', 'Nota média dos estudantes na prova de Matemática do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_finais'), 'A cada dois anos', 'inep', 34, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_saeb_lp_af', 'edu', 'Saeb — Língua Portuguesa, anos finais do ensino fundamental (rede pública)', 'Nota média dos estudantes na prova de Língua Portuguesa do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'anos_finais'), 'A cada dois anos', 'inep', 35, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_ideb_em', 'edu', 'IDEB — ensino médio (rede pública)', 'Índice de Desenvolvimento da Educação Básica calculado pelo INEP a cada dois anos, de 0 a 10: combina a aprovação dos alunos (indicador de rendimento) com o desempenho no Saeb. Valor da rede pública do município; a rede responsável aparece junto de cada resultado.',
       'nota (0 a 10)', 'nota', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'ensino_medio'), 'A cada dois anos', 'inep', 36, casas=1, sentido='maior',
       base_legal='Decreto 6.094/2007, art. 3º; Lei 13.005/2014 (PNE), meta 7.', reserva=True),
    _i('edu_saeb_mat_em', 'edu', 'Saeb — Matemática, ensino médio (rede pública)', 'Nota média dos estudantes na prova de Matemática do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'ensino_medio'), 'A cada dois anos', 'inep', 37, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_saeb_lp_em', 'edu', 'Saeb — Língua Portuguesa, ensino médio (rede pública)', 'Nota média dos estudantes na prova de Língua Portuguesa do Saeb (escala de proficiência do INEP), rede pública do município.',
       'pontos (escala Saeb)', 'numero', 'INEP — planilhas oficiais de resultados do IDEB por município', _INEP_PL.replace('{etapa}', 'ensino_medio'), 'A cada dois anos', 'inep', 38, casas=2, sentido='maior',
       base_legal='Lei 9.394/1996, art. 9º, VI; Decreto 6.094/2007, art. 3º.', reserva=True),
    _i('edu_alfabetizacao', 'edu', 'Taxa de alfabetização (15 anos ou mais)', 'Parte das pessoas com 15 anos ou mais que sabem ler e escrever, segundo o Censo Demográfico.',
       '%', 'pct', 'IBGE — Censo Demográfico 2022', _IBGE + 'v1/pesquisas/10101/periodos/2022/indicadores/111628/resultados/{ibge}', 'Decenal (Censo)', 'ibge', 50, casas=2, sentido='maior',
       base_legal='Lei 13.005/2014 (PNE), meta 9.'),
    # Assistência social (MDS; desligado até a fonte voltar)
    _i('social_bf_familias', 'social', 'Famílias no Bolsa Família', 'Famílias do município que receberam o Bolsa Família no mês (total, sem nomes).',
       'famílias', 'numero', 'MDS — MI Social', 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial', 'Mensal', 'mds', 10, suprimir=True, pendente=_PEND_MDS,
       base_legal='Lei 14.601/2023; LGPD, art. 6º, III.'),
    _i('social_bf_valor', 'social', 'Valor repassado pelo Bolsa Família', 'Total pago às famílias do município pelo Bolsa Família no mês.',
       'R$', 'moeda', 'MDS — MI Social', 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial', 'Mensal', 'mds', 20, pendente=_PEND_MDS, base_legal='Lei 14.601/2023.'),
    _i('social_cadunico_familias', 'social', 'Famílias no Cadastro Único', 'Famílias do município inscritas no Cadastro Único para programas sociais (total, sem nomes).',
       'famílias', 'numero', 'MDS — MI Social', 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial', 'Mensal', 'mds', 30, suprimir=True, pendente=_PEND_MDS,
       base_legal='Decreto 11.016/2022; LGPD, art. 6º, III.'),
    _i('social_bpc', 'social', 'Beneficiários do BPC', 'Pessoas idosas e pessoas com deficiência do município que recebem o Benefício de Prestação Continuada (total, sem nomes).',
       'beneficiários', 'numero', 'MDS — MI Social', 'https://aplicacoes.mds.gov.br/sagi/servicos/misocial', 'Mensal', 'mds', 40, suprimir=True, pendente=_PEND_MDS,
       base_legal='Lei 8.742/1993, art. 20; LGPD, art. 6º, III.'),
    # Município e gestão
    _i('mun_populacao', 'mun', 'População estimada', 'Estimativa oficial do IBGE para a população residente no município em 1º de julho de cada ano (nos anos de Censo, a contagem do Censo).',
       'habitantes', 'numero', 'IBGE — Estimativas da população (agregado 6579) e Censo 2022', _IBGE + 'v3/agregados/6579/periodos/-6/variaveis/9324?localidades=N6[{ibge}]', 'Anual', 'ibge', 10,
       base_legal='Lei 8.443/1992, art. 102 (estimativas do IBGE para o TCU).', destaque=True),
    _i('mun_pib_per_capita', 'mun', 'PIB per capita', 'Produto Interno Bruto do município dividido pela população, calculado e publicado pelo IBGE (valores correntes de cada ano).',
       'R$', 'moeda', 'IBGE — PIB dos Municípios', _IBGE + 'v1/pesquisas/38/periodos/all/indicadores/47001/resultados/{ibge}', 'Anual', 'ibge', 20, base_legal='LAI, art. 8º.'),
    _i('mun_pessoal_ocupado', 'mun', 'Pessoal ocupado em empresas e organizações', 'Pessoas ocupadas em empresas e outras organizações formais com sede no município (Cadastro Central de Empresas).',
       'pessoas', 'numero', 'IBGE — Cadastro Central de Empresas (CEMPRE)', _IBGE + 'v1/pesquisas/19/periodos/all/indicadores/143514/resultados/{ibge}', 'Anual', 'ibge', 30, suprimir=True,
       base_legal='LAI, art. 8º.'),
    _i('mun_salario_medio', 'mun', 'Salário médio mensal dos trabalhadores formais', 'Média dos salários das pessoas ocupadas em empresas e organizações formais, em salários mínimos.',
       'salários mínimos', 'numero', 'IBGE — Cadastro Central de Empresas (CEMPRE)', _IBGE + 'v1/pesquisas/19/periodos/all/indicadores/143558/resultados/{ibge}', 'Anual', 'ibge', 40, casas=1,
       base_legal='LAI, art. 8º.'),
    _i('mun_esgoto', 'mun', 'Domicílios com esgotamento sanitário por rede', 'Parte dos domicílios ligados à rede geral de esgoto, à rede pluvial ou a fossa ligada à rede, segundo o Censo.',
       '%', 'pct', 'IBGE — Censo Demográfico 2022', _IBGE + 'v1/pesquisas/10101/periodos/2022/indicadores/105286/resultados/{ibge}', 'Decenal (Censo)', 'ibge', 50, casas=2, sentido='maior',
       base_legal='Lei 11.445/2007, art. 2º (universalização do saneamento).'),
    _i('gestao_sic_pedidos', 'mun', 'Pedidos de acesso à informação recebidos', 'Pedidos feitos ao Serviço de Informação ao Cidadão (e-SIC) deste portal no ano. Só a quantidade; nunca quem pediu.',
       'pedidos', 'numero', 'e-SIC deste portal', '/acesso', 'Tempo real (atualizado a cada hora)', 'painel', 60, suprimir=True,
       base_legal='LAI, arts. 9º a 11 e 30, III (relatório estatístico).'),
    _i('gestao_sic_no_prazo', 'mun', 'Pedidos de informação respondidos no prazo', 'Parte dos pedidos respondidos no ano dentro do prazo da LAI: 20 dias, ou 30 dias quando a prorrogação foi justificada. Só aparece com 5 ou mais pedidos respondidos.',
       '%', 'pct', 'e-SIC deste portal', '/acesso', 'Tempo real (atualizado a cada hora)', 'painel', 70, casas=1, sentido='maior', meta=100,
       meta_base_legal='LAI, art. 11, §§ 1º e 2º (20 dias, prorrogáveis por 10 com justificativa).', base_legal='LAI, arts. 11 e 30, III.'),
    _i('gestao_sic_prazo_medio', 'mun', 'Tempo médio de resposta aos pedidos de informação', 'Média de dias entre o recebimento e a resposta dos pedidos respondidos no ano. Só aparece com 5 ou mais pedidos respondidos.',
       'dias', 'numero', 'e-SIC deste portal', '/acesso', 'Tempo real (atualizado a cada hora)', 'painel', 80, casas=1, sentido='menor', base_legal='LAI, arts. 11 e 30, III.'),
    _i('gestao_ouv_manifestacoes', 'mun', 'Manifestações recebidas pela Ouvidoria', 'Reclamações, sugestões, elogios, denúncias e solicitações recebidas pela Ouvidoria deste portal no ano. Só a quantidade.',
       'manifestações', 'numero', 'Ouvidoria deste portal', '/acesso', 'Tempo real (atualizado a cada hora)', 'painel', 90, suprimir=True, base_legal='Lei 13.460/2017, arts. 13 e 15.'),
] + [_i(k, 'mun', n, 'Faixa do Índice de Efetividade da Gestão Municipal (IEG-M) do Tribunal de Contas do Estado: A (altamente efetiva), B+ (muito efetiva), B (efetiva), C+ (em fase de adequação) e C (baixo nível de adequação). Ano de referência = ano-base avaliado.',
         'faixa', 'faixa', 'TCESP — IEG-M (painel público do Tribunal)', 'https://painel.tce.sp.gov.br/', 'Anual', 'iegm', 100 + i, modo='manual', alternavel=True,
         pendente=PEND_IEGM,
         base_legal='Constituição, art. 71 c/c art. 75; Lei Complementar estadual 709/1993.') for i, (k, n) in enumerate(_IEGM)]
CAT = {c['chave']: c for c in CATALOGO}
# indicadores retirados do catálogo (substituídos): ficam ocultos e sem coletor, com a série guardada
RETIRADOS = {'edu_ideb_ai_mun': 'edu_ideb_ai', 'edu_ideb_ai_est': 'edu_ideb_ai', 'edu_ideb_af_mun': 'edu_ideb_af', 'edu_ideb_af_est': 'edu_ideb_af',
             'edu_ideb_em_est': 'edu_ideb_em', 'edu_saeb': 'edu_saeb_mat_ai'}
FAIXAS_IEGM = ['A', 'B+', 'B', 'C+', 'C']

# campos que o código mantém atualizados; os demais (texto explicativo, meta, visibilidade, ordem, destaque) são do administrador
_DO_CODIGO = ['tema', 'nome', 'unidade', 'formato', 'casas', 'fonte', 'fonte_link', 'periodicidade', 'modo', 'coletor', 'pendente', 'sentido', 'suprimir', 'base_legal']
_DO_ADMIN = ['descricao', 'meta', 'meta_base_legal', 'visivel', 'destaque', 'ordem']

def semear(banco):
    """Cria/atualiza o catálogo padrão no banco do órgão sem sobrescrever o que o administrador ajustou."""
    n = 0
    for c in CATALOGO:
        cols = ['chave'] + _DO_CODIGO + _DO_ADMIN
        vals = [c['chave']] + [c[k] for k in _DO_CODIGO] + [c['descricao'], c['meta'], c['meta_base_legal'], True, c['destaque'], c['ordem']]
        atualiza = [k for k in _DO_CODIGO if not (c['alternavel'] and k == 'modo')]  # modo alternável é escolha do administrador
        r = db.exe(banco, f"INSERT INTO indicadores ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) ON CONFLICT (chave) DO UPDATE SET "
                   + ', '.join(f'{k}=EXCLUDED.{k}' for k in atualiza) + ' RETURNING (xmax = 0) novo', vals)
        n += 1 if r and r['novo'] else 0
    for velho, novo in RETIRADOS.items():
        r = db.um(banco, 'SELECT destaque FROM indicadores WHERE chave=%s AND (visivel OR coletor<>%s)', (velho, ''))
        if r:
            db.exe(banco, "UPDATE indicadores SET visivel=FALSE, destaque=FALSE, coletor='', pendente=%s WHERE chave=%s", (f'Substituído por {novo} (planilhas oficiais do INEP).', velho))
            if r['destaque']:
                db.exe(banco, 'UPDATE indicadores SET destaque=TRUE WHERE chave=%s', (novo,))
    return n

# ---------- períodos ----------
def fim_do_ano(a):
    return date(int(a), 12, 31)

def fim_do_mes(a, m):
    return date(int(a), int(m), calendar.monthrange(int(a), int(m))[1])

def rotulo_mes(d):
    return f'{MESES[d.month - 1]}/{d.year}'

# ---------- gravação ----------
def _ind(banco, chave):
    return db.um(banco, 'SELECT * FROM indicadores WHERE chave=%s', (chave,))

def gravar(banco, chave, periodo, data_ref, valor=None, texto='', detalhe=None, nota='', parcial=False, origem='coletor', usuario='', motivo=''):
    """Grava (upsert) um valor da série. O coletor nunca sobrescreve um lançamento manual do mesmo período."""
    ind = _ind(banco, chave)
    if not ind:
        return False
    v = None if valor is None else Decimal(str(valor))
    cond = '' if origem == 'manual' else " WHERE indicador_valores.origem <> 'manual'"
    r = db.exe(banco, """INSERT INTO indicador_valores (indicador_id, periodo, data_ref, valor, texto, detalhe, nota, parcial, origem, usuario, motivo, coletado_em)
                         VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                         ON CONFLICT (indicador_id, periodo) DO UPDATE SET data_ref=EXCLUDED.data_ref, valor=EXCLUDED.valor, texto=EXCLUDED.texto, detalhe=EXCLUDED.detalhe,
                         nota=EXCLUDED.nota, parcial=EXCLUDED.parcial, origem=EXCLUDED.origem, usuario=EXCLUDED.usuario, motivo=EXCLUDED.motivo, coletado_em=now()""" + cond + ' RETURNING id',
               (ind['id'], str(periodo)[:40], data_ref, v, (texto or '')[:40], Jsonb(detalhe) if detalhe is not None else None, (nota or '')[:300], bool(parcial), origem, usuario[:120], (motivo or '')[:500]))
    return bool(r)

def gravar_publico(ibge, chave, periodo, data_ref, fonte, valor=None, texto='', detalhe=None, nota='', parcial=False):
    """Dados nacionais (IBGE, INEP, CNES, MDS, Siconfi) ficam no banco de controle por código IBGE, para servir a qualquer município."""
    db.exe(db.PLATAFORMA, """INSERT INTO indicadores_publicos (ibge, indicador, periodo, data_ref, valor, texto, detalhe, nota, parcial, fonte, coletado_em)
                             VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, now())
                             ON CONFLICT (ibge, indicador, periodo) DO UPDATE SET data_ref=EXCLUDED.data_ref, valor=EXCLUDED.valor, texto=EXCLUDED.texto, detalhe=EXCLUDED.detalhe,
                             nota=EXCLUDED.nota, parcial=EXCLUDED.parcial, fonte=EXCLUDED.fonte, coletado_em=now()""",
           (str(ibge), chave, str(periodo)[:40], data_ref, None if valor is None else Decimal(str(valor)), texto or '', Jsonb(detalhe) if detalhe is not None else None, nota or '', bool(parcial), fonte))

def copiar_publicos(banco, ibge, chaves):
    """Copia para o banco do órgão a série compartilhada dos indicadores indicados."""
    n = 0
    for x in db.todos(db.PLATAFORMA, 'SELECT * FROM indicadores_publicos WHERE ibge=%s AND indicador = ANY(%s)', (str(ibge), list(chaves))):
        n += gravar(banco, x['indicador'], x['periodo'], x['data_ref'], x['valor'], x['texto'], x['detalhe'], x['nota'], x['parcial'])
    return n

def marcar_coleta(banco, coletor, ok, msg, chaves=None):
    """Registra no catálogo a situação da última coleta dos indicadores de um coletor (para o aviso "dado de <data>")."""
    if chaves is not None and not chaves:
        return
    sql = 'UPDATE indicadores SET ultima_tentativa=now(), ultima_msg=%s' + (', ultima_ok=now()' if ok else '') + ' WHERE coletor=%s'
    p = [(msg or '')[:300], coletor]
    if chaves:
        sql += ' AND chave = ANY(%s)'
        p.append(list(chaves))
    db.exe(banco, sql, p)

def historico(banco, indicador_id, usuario, acao, antes=None, depois=None):
    def limpo(d):
        return None if d is None else json.loads(json.dumps(d, default=str))
    db.exe(banco, 'INSERT INTO indicador_historico (indicador_id, usuario, acao, antes, depois) VALUES (%s,%s,%s,%s,%s)',
           (indicador_id, usuario, acao[:300], Jsonb(limpo(antes)) if antes is not None else None, Jsonb(limpo(depois)) if depois is not None else None))

# ---------- leitura ----------
def serie(banco, indicador_id, limite=None):
    s = db.todos(banco, 'SELECT * FROM indicador_valores WHERE indicador_id=%s ORDER BY data_ref, periodo', (indicador_id,))
    return s[-limite:] if limite else s

def catalogo(banco, so_visiveis=True, tema=None):
    sql = 'SELECT * FROM indicadores'
    w, p = [], []
    if so_visiveis:
        w.append('visivel')
    if tema:
        w.append('tema=%s'); p.append(tema)
    if w:
        sql += ' WHERE ' + ' AND '.join(w)
    return db.todos(banco, sql + ' ORDER BY array_position(%s::text[], tema), ordem, id', p + [[t for t, _ in TEMAS]])

def montar(banco, ind, limite=12):
    """Indicador pronto para exibir: série, último valor, textos de variação e meta, aviso de dado antigo."""
    s = serie(banco, ind['id'])
    if not s:
        return None
    ult = s[-1]
    ant = s[-2] if len(s) > 1 else None
    d = dict(ind)
    d.update(serie=s, ult=ult, ant=ant, valor_txt=exibir(ind, ult), valor_curto=exibir(ind, ult, curto=True), variacao=variacao(ind, ult, ant),
             meta_txt=texto_meta(ind, ult), aviso=aviso_antigo(ind), tema_nome=TEMA_NOME[ind['tema']], spark=spark(ind, s[-limite:]))
    return d

def aviso_antigo(ind):
    """'Dado de <data>' quando a última tentativa de coleta falhou e o valor exibido é o último válido."""
    if ind['modo'] != 'automatico' or not ind['ultima_tentativa']:
        return ''
    if ind['ultima_ok'] and ind['ultima_ok'] >= ind['ultima_tentativa']:
        return ''
    quando = ind['ultima_ok']
    return f"Dado de {quando.astimezone().strftime('%d/%m/%Y')}: a última consulta à fonte falhou; mostramos o último valor válido." if quando else 'A última consulta à fonte falhou; mostramos o último valor válido.'

def painel(banco, tema=None):
    out = []
    for ind in catalogo(banco, True, tema):
        m = montar(banco, ind)
        if m:
            out.append(m)
    return out

def destaques(banco):
    inds = db.todos(banco, 'SELECT * FROM indicadores WHERE visivel AND destaque ORDER BY array_position(%s::text[], tema), ordem, id', ([t for t, _ in TEMAS],))
    return [m for m in (montar(banco, i) for i in inds) if m][:MAX_DESTAQUES]

# ---------- formatação ----------
def _br(v, casas):
    s = f'{float(v):,.{casas}f}'
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')

def suprimido(ind, linha):
    return bool(ind['suprimir'] and linha and linha['valor'] is not None and float(linha['valor']) < SUPRESSAO)

def exibir(ind, linha, curto=False):
    if not linha:
        return '—'
    if ind['formato'] == 'faixa':
        return linha['texto'] or '—'
    if linha['valor'] is None:
        return linha['texto'] or '—'
    if suprimido(ind, linha):
        return 'menos de 5'
    v = float(linha['valor'])
    c = ind['casas']
    if ind['formato'] == 'moeda':
        if curto and abs(v) >= 1e6:
            return 'R$ ' + _br(v / 1e6, 1) + ' mi'
        if curto and abs(v) >= 1e4:
            return 'R$ ' + _br(v / 1e3, 0) + ' mil'
        return 'R$ ' + _br(v, 0 if curto else 2)
    if ind['formato'] == 'pct':
        return _br(v, c) + '%'
    return _br(v, c)

def variacao(ind, ult, ant):
    """Texto (não só cor) com a variação em relação ao período anterior. Períodos parciais e valores suprimidos não são comparados."""
    if ind['formato'] == 'faixa':
        if ant and ant['texto'] and ult['texto']:
            return f"{ant['periodo']}: {ant['texto']}"
        return ''
    if not ant or ult['valor'] is None or ant['valor'] is None:
        return ''
    if ult['parcial']:
        return f"{ult['periodo']} ainda em andamento: sem comparação com {ant['periodo']}"
    if ant['parcial'] or suprimido(ind, ult) or suprimido(ind, ant):
        return ''
    a, b = float(ant['valor']), float(ult['valor'])
    if ind['formato'] in ('pct', 'nota'):
        dif = b - a
        un = ' p.p.' if ind['formato'] == 'pct' else ' ponto' + ('s' if round(abs(dif), ind['casas']) != 1 else '')
        if round(dif, ind['casas']) == 0:
            return f"igual a {ant['periodo']}"
        return f"{'+' if dif > 0 else '−'}{_br(abs(dif), max(ind['casas'], 1))}{un} em relação a {ant['periodo']}"
    if a == 0:
        return ''
    pct = (b - a) / abs(a) * 100
    if round(pct, 1) == 0:
        return f"igual a {ant['periodo']}"
    return f"{'+' if pct > 0 else '−'}{_br(abs(pct), 1)}% em relação a {ant['periodo']}"

def texto_meta(ind, linha):
    if ind['meta'] is None or not linha or linha['valor'] is None or suprimido(ind, linha):
        return ''
    meta, v = float(ind['meta']), float(linha['valor'])
    mf = _br(meta, 0 if meta == int(meta) else ind['casas']) + ('%' if ind['formato'] == 'pct' else '')
    if ind['sentido'] == 'maior':
        sit = 'atingido' if v >= meta else 'abaixo do mínimo'
        rot = 'Mínimo legal' if ind['meta_base_legal'] else 'Meta'
        if rot == 'Meta':
            sit = 'atingida' if v >= meta else 'não atingida'
        return f'{rot}: {mf} · {sit}' + (' até agora (período em andamento)' if linha['parcial'] else '')
    if ind['sentido'] == 'menor':
        return f"Meta: até {mf} · {'atingida' if v <= meta else 'não atingida'}"
    return f'Meta: {mf}'

def link_fonte(ind, o, linha=None):
    url = ind['fonte_link'] or ''
    ano = (linha['data_ref'].year if linha else config.hoje().year)
    return url.replace('{ibge}', str(o['ibge'])).replace('{ibge6}', str(o['ibge'])[:6]).replace('{ano}', str(ano))

# ---------- gráficos SVG (no servidor, sem biblioteca externa) ----------
# Paleta Okabe-Ito (segura para daltonismo); rótulos de texto em todas as barras.
COR_BARRA, COR_PARCIAL, COR_META, COR_TXT, COR_EIXO = '#0072B2', '#56B4E9', '#B34700', '#17212B', '#6B7684'
COR_PROJ = '#00795A'  # verde-azulado (família Okabe-Ito, escurecido para contraste 5:1 no branco)

def _esc(s):
    return escape(str(s), {'"': '&quot;'})

def grafico(ind, s, uid='g'):
    """Gráfico de barras da série (últimos 12 períodos), com valor escrito em cada barra, linha tracejada da meta
    e barra tracejada para contagens suprimidas. Retorna None para indicadores de faixa (só tabela)."""
    if ind['formato'] == 'faixa' or not s:
        return None
    s = s[-12:]
    W, H, ml, mr, mt, mb = 640, 300, 12, 12, 34, 54
    vals = [float(x['valor']) for x in s if x['valor'] is not None and not suprimido(ind, x)]
    proj = [(i, float(x['detalhe']['projecao'])) for i, x in enumerate(s) if isinstance(x['detalhe'], dict) and x['detalhe'].get('projecao') is not None]
    if proj:
        mt = 52  # espaço para a legenda da referência histórica
    vals += [v for _, v in proj]
    if ind['meta'] is not None:
        vals.append(float(ind['meta']))
    topo = max(vals + [0]) * 1.15 or 1
    if ind['formato'] == 'pct' and topo < 100 and max(vals + [0]) > 60:
        topo = 105
    n = len(s)
    passo = (W - ml - mr) / n
    lb = min(56, passo * 0.62)
    base = H - mb
    y = lambda v: base - (v / topo) * (H - mt - mb)
    titulo = f"{ind['nome']}: série histórica"
    desc = '; '.join(f"{x['periodo']}: {exibir(ind, x)}{' (parcial)' if x['parcial'] else ''}" for x in s)
    if ind['meta'] is not None:
        desc += f". {texto_meta(ind, s[-1])}"
    if proj:
        desc += '. Metas projetadas pelo INEP (referência histórica, não são meta atual): ' + '; '.join(f"{s[i]['periodo']}: {_br(v, ind['casas'])}" for i, v in proj)
    p = [f'<svg class="grafico" viewBox="0 0 {W} {H}" role="img" aria-labelledby="{uid}-t {uid}-d" xmlns="http://www.w3.org/2000/svg">',
         f'<title id="{uid}-t">{_esc(titulo)}</title><desc id="{uid}-d">{_esc(desc)}</desc>',
         f'<line x1="{ml}" y1="{base}" x2="{W - mr}" y2="{base}" stroke="{COR_EIXO}" stroke-width="1"/>']
    for i, x in enumerate(s):
        cx = ml + passo * i + passo / 2
        rot = exibir(ind, x, curto=True)
        if suprimido(ind, x):
            p.append(f'<rect x="{cx - lb / 2:.1f}" y="{base - 22}" width="{lb:.1f}" height="22" fill="none" stroke="{COR_EIXO}" stroke-dasharray="4 3"/>')
            ty = base - 28
        elif x['valor'] is None:
            ty = base - 8
            if x['texto']:  # ex.: "não divulgado pelo INEP" — nunca desenhado como zero
                p.append(f'<text x="{cx:.1f}" y="{base - 22}" text-anchor="middle" font-size="11" fill="{COR_EIXO}">não</text>')
                p.append(f'<text x="{cx:.1f}" y="{base - 8}" text-anchor="middle" font-size="11" fill="{COR_EIXO}">divulgado</text>')
                rot = ''
        else:
            yy = y(float(x['valor']))
            cor = COR_PARCIAL if x['parcial'] else COR_BARRA
            p.append(f'<rect x="{cx - lb / 2:.1f}" y="{yy:.1f}" width="{lb:.1f}" height="{max(base - yy, 1):.1f}" fill="{cor}" rx="2"/>')
            ty = yy - 7
        if rot:
            p.append(f'<text x="{cx:.1f}" y="{ty:.1f}" text-anchor="middle" font-size="13" font-weight="700" fill="{COR_TXT}">{_esc(rot)}</text>')
        p.append(f'<text x="{cx:.1f}" y="{base + 18}" text-anchor="middle" font-size="13" fill="{COR_TXT}">{_esc(x["periodo"])}</text>')
        if x['parcial']:
            p.append(f'<text x="{cx:.1f}" y="{base + 34}" text-anchor="middle" font-size="11" fill="{COR_EIXO}">parcial</text>')
    if proj:
        pts = [(ml + passo * i + passo / 2, y(v)) for i, v in proj]
        p.append(f'<polyline points="{" ".join(f"{a:.1f},{b:.1f}" for a, b in pts)}" fill="none" stroke="{COR_PROJ}" stroke-width="2" stroke-dasharray="3 4"/>')
        for a, b in pts:
            p.append(f'<path d="M{a:.1f} {b - 6:.1f} L{a + 6:.1f} {b:.1f} L{a:.1f} {b + 6:.1f} L{a - 6:.1f} {b:.1f} Z" fill="#fff" stroke="{COR_PROJ}" stroke-width="2"/>')
        p.append(f'<path d="M{ml + 6} 10 L{ml + 12} 16 L{ml + 6} 22 L{ml} 16 Z" fill="#fff" stroke="{COR_PROJ}" stroke-width="2"/>')
        p.append(f'<text x="{ml + 18}" y="20" font-size="12" fill="{COR_TXT}">Meta projetada pelo INEP (referência histórica até 2021; não é meta atual)</text>')
    if ind['meta'] is not None:
        ym = y(float(ind['meta']))
        p.append(f'<line x1="{ml}" y1="{ym:.1f}" x2="{W - mr}" y2="{ym:.1f}" stroke="{COR_META}" stroke-width="2" stroke-dasharray="7 5"/>')
        mf = _br(float(ind['meta']), 0) + ('%' if ind['formato'] == 'pct' else '')
        p.append(f'<text x="{W - mr}" y="{ym - 6:.1f}" text-anchor="end" font-size="12" font-weight="700" fill="{COR_META}">{"Mínimo" if ind["meta_base_legal"] else "Meta"} {mf}</text>')
    p.append('</svg>')
    return Markup(''.join(p))

def spark(ind, s):
    """Mini gráfico do cartão (decorativo: o número e a variação estão em texto ao lado)."""
    if ind['formato'] == 'faixa' or len(s) < 2:
        return ''
    vals = [0 if (x['valor'] is None or suprimido(ind, x)) else float(x['valor']) for x in s]
    topo = max(vals) or 1
    W, H, n = 120, 32, len(vals)
    lb = W / n * 0.7
    out = [f'<svg class="spark" viewBox="0 0 {W} {H}" aria-hidden="true" focusable="false" xmlns="http://www.w3.org/2000/svg">']
    for i, v in enumerate(vals):
        h = max(2, v / topo * (H - 2)) if v else 2
        cor = COR_PARCIAL if s[i]['parcial'] else COR_BARRA
        out.append(f'<rect x="{i * W / n + (W / n - lb) / 2:.1f}" y="{H - h:.1f}" width="{lb:.1f}" height="{h:.1f}" fill="{cor if v else "#C9D1D9"}" rx="1"/>')
    out.append('</svg>')
    return Markup(''.join(out))

# ---------- exportação (CSV, JSON, ODS) ----------
CAMPOS = ['tema', 'indicador', 'chave', 'periodo', 'data_referencia', 'valor', 'valor_exibido', 'unidade', 'parcial', 'nota', 'complemento', 'origem', 'fonte', 'link_fonte', 'coletado_em', 'base_legal']

def linhas_export(o, inds):
    """Linhas planas para download. Contagens suprimidas saem sem o número (valor vazio, valor_exibido = 'menos de 5')."""
    out = []
    for ind in inds:
        for x in serie(o['banco'], ind['id']):
            sup = suprimido(ind, x)
            out.append({'tema': TEMA_NOME[ind['tema']], 'indicador': ind['nome'], 'chave': ind['chave'], 'periodo': x['periodo'],
                        'data_referencia': x['data_ref'].isoformat(), 'valor': None if sup or x['valor'] is None else float(x['valor']),
                        'valor_exibido': exibir(ind, x), 'unidade': ind['unidade'], 'parcial': x['parcial'], 'nota': x['nota'], 'complemento': complemento(x),
                        'origem': 'lançamento manual' if x['origem'] == 'manual' else 'coleta automática', 'fonte': ind['fonte'],
                        'link_fonte': link_fonte(ind, o, x), 'coletado_em': x['coletado_em'].astimezone().isoformat(timespec='minutes'), 'base_legal': ind['base_legal']})
    return out

def complemento(x):
    """Dados extras da linha em texto (ex.: rendimento e meta projetada do INEP no IDEB)."""
    d = x['detalhe'] if isinstance(x['detalhe'], dict) else {}
    partes = []
    if d.get('rendimento') is not None:
        partes.append(f"indicador de rendimento (P) {_br(d['rendimento'], 3)}")
    if d.get('projecao') is not None:
        partes.append(f"meta projetada pelo INEP (referência histórica) {_br(d['projecao'], 1)}")
    return '; '.join(partes)

def csv_bytes(linhas):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=CAMPOS)
    w.writeheader()
    for l in linhas:
        w.writerow({k: ('' if l[k] is None else ('sim' if l[k] is True else 'não' if l[k] is False else l[k])) for k in CAMPOS})
    return ('﻿' + buf.getvalue()).encode('utf-8')

def json_obj(o, linhas, titulo):
    return {'orgao': o['nome'], 'titulo': titulo, 'base_legal': BASE_LEGAL, 'gerado_em': datetime.now().astimezone().isoformat(timespec='minutes'),
            'lgpd': 'Só dados agregados. Contagens de pessoas abaixo de 5 aparecem como "menos de 5" e sem o número.', 'campos': CAMPOS, 'registros': linhas}

def ods_bytes(linhas, nome='Indicadores'):
    """Planilha OpenDocument (ODS) mínima e válida, sem bibliotecas externas."""
    def cel(v):
        if isinstance(v, bool):
            return f'<table:table-cell office:value-type="string"><text:p>{"sim" if v else "não"}</text:p></table:table-cell>'
        if isinstance(v, (int, float)) and v is not None:
            return f'<table:table-cell office:value-type="float" office:value="{v}"><text:p>{v}</text:p></table:table-cell>'
        if v is None or v == '':
            return '<table:table-cell/>'
        return f'<table:table-cell office:value-type="string"><text:p>{escape(str(v))}</text:p></table:table-cell>'
    linhas_xml = ['<table:table-row>' + ''.join(cel(c) for c in CAMPOS) + '</table:table-row>']
    linhas_xml += ['<table:table-row>' + ''.join(cel(l[c]) for c in CAMPOS) + '</table:table-row>' for l in linhas]
    content = ('<?xml version="1.0" encoding="UTF-8"?>'
               '<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" xmlns:table="urn:oasis:names:tc:opendocument:xmlns:table:1.0" '
               'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" office:version="1.2"><office:body><office:spreadsheet>'
               f'<table:table table:name="{escape(nome[:31])}">' + ''.join(linhas_xml) + '</table:table></office:spreadsheet></office:body></office:document-content>')
    manifest = ('<?xml version="1.0" encoding="UTF-8"?><manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.2">'
                '<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.spreadsheet"/>'
                '<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/></manifest:manifest>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(zipfile.ZipInfo('mimetype'), 'application/vnd.oasis.opendocument.spreadsheet', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/manifest.xml', manifest, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('content.xml', content, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()
