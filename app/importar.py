"""Importação de dados antigos da Câmara a partir de CSV exportado pelo sistema do fornecedor ou digitado (nada de raspagem).

  python -m app.importar MODELO ARQUIVO.csv [--orgao cm-bora] [--gravar]
Sem --gravar é só simulação: valida tudo e mostra o relatório de erros sem gravar nada.
CSV em UTF-8, separador ponto e vírgula, datas dd/mm/aaaa. Modelos em Docs/modelos/.
A importação é tudo ou nada: com qualquer erro, nada é gravado."""
import csv, io, re, sys
from datetime import date
from psycopg.types.json import Jsonb
from . import db, legislativo as L
from .coletores.comum import chave

MODELOS = {
    'legislaturas': ['numero', 'anos', 'prefeito', 'vice'],
    'vereadores': ['legislatura', 'nome', 'apelido', 'partido', 'votos'],
    'mesas': ['legislatura', 'bienio', 'cargo', 'nome'],
    'proposicoes': ['tipo', 'numero', 'ano', 'autores', 'relator', 'ementa', 'situacao'],
    'tramitacao': ['tipo', 'numero', 'ano', 'data', 'fase', 'descricao'],
    'sessoes': ['nome', 'data', 'hora', 'tipo'],
    'presencas': ['sessao_data', 'sessao_nome', 'vereador', 'situacao'],
    'votos': ['sessao_data', 'tipo', 'numero', 'ano', 'vereador', 'voto'],
    'diarias': ['beneficiario', 'cargo', 'destino', 'motivo', 'inicio', 'fim', 'valor'],
}
# Prefeitura (Fase 8): acervo de legislação anterior ao Diário eletrônico — opcional, a partir de planilha (nada de raspagem)
MODELOS_EXECUTIVO = {'legislacao': ['tipo', 'numero', 'ano', 'data', 'ementa', 'link', 'relacoes']}
MODELOS_TODOS = {**MODELOS, **MODELOS_EXECUTIVO}

def modelos_do(tipo):
    return MODELOS_EXECUTIVO if tipo == 'executivo' else MODELOS
DESCRICAO = {
    'legislaturas': 'numero inteiro; anos no formato 2021–2024 (ou 2021-2024)',
    'vereadores': 'legislatura já cadastrada; votos inteiro ou vazio',
    'mesas': 'cargo: Presidente, Vice-presidente, 1º secretário, 2º secretário; nome de um vereador da legislatura',
    'proposicoes': 'tipo da lista oficial; autores separados por | (vereadores, Poder Executivo, Mesa Diretora, Comissão de ...)',
    'tramitacao': 'proposição já cadastrada (tipo, numero, ano); data dd/mm/aaaa',
    'sessoes': 'tipo: Ordinária, Extraordinária, Solene, Especial',
    'presencas': 'sessão já cadastrada (data e nome); vereador da legislatura atual; situacao: presente, ausente ou justificada',
    'votos': 'sessão já cadastrada na data; proposição já cadastrada; voto: sim, nao, abstencao ou ausente',
    'diarias': 'valor com vírgula decimal; inicio e fim dd/mm/aaaa',
    'legislacao': 'tipo: Lei, Lei Complementar, Decreto, Decreto Legislativo, Portaria ou Resolução; data dd/mm/aaaa (ou vazia); link https:// do texto oficial; relacoes: revoga:Lei 3/2001|altera:Lei 5/2002 (atos já importados ou de linhas anteriores)',
}
CPF = re.compile(r'\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b')

class _Simulacao(Exception):
    pass

def _data(s):
    m = re.match(r'^\s*(\d{2})/(\d{2})/(\d{4})\s*$', s or '')
    if not m:
        raise ValueError(f'data inválida "{s}" (use dd/mm/aaaa)')
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        raise ValueError(f'data inválida "{s}" (dia ou mês fora do calendário)')

def _int(s, campo):
    if not str(s).strip().isdigit():
        raise ValueError(f'{campo} deve ser número inteiro')
    return int(s)

def ler_csv(dados: bytes):
    t = dados.decode('utf-8-sig')
    return list(csv.DictReader(io.StringIO(t), delimiter=';'))

def importar(banco, modelo, dados: bytes, simular=True, quem='linha de comando', arquivo='arquivo.csv'):
    cols = MODELOS_TODOS[modelo]
    erros, n_ok = [], 0
    try:
        linhas = ler_csv(dados)
    except UnicodeDecodeError:
        return _registrar(banco, modelo, arquivo, 0, 0, [{'linha': 0, 'erro': 'arquivo não está em UTF-8'}], simular, quem)
    if linhas and set(cols) - set(linhas[0].keys()):
        return _registrar(banco, modelo, arquivo, len(linhas), 0, [{'linha': 1, 'erro': f'cabeçalho deve ter as colunas: {";".join(cols)}'}], simular, quem)
    try:
        with db.conn(banco) as c:
            with c.transaction():
                for i, l in enumerate(linhas, start=2):
                    l = {k: (v or '').strip() for k, v in l.items() if k}
                    try:
                        if any(CPF.search(v) for v in l.values()):
                            raise ValueError('a linha contém um número com formato de CPF (LGPD): retire antes de importar')
                        with c.transaction():  # cada linha num savepoint: o erro de uma não esconde o das outras
                            _linha(c, modelo, l)
                        n_ok += 1
                    except (ValueError, KeyError) as e:
                        erros.append({'linha': i, 'erro': str(e)})
                if simular or erros:
                    raise _Simulacao()
    except _Simulacao:
        pass
    return _registrar(banco, modelo, arquivo, len(linhas), 0 if (simular or erros) else n_ok, erros, simular, quem, validas=n_ok)

def _registrar(banco, modelo, arquivo, n, gravadas, erros, simular, quem, validas=0):
    db.exe(banco, 'INSERT INTO importacoes (modelo, arquivo, linhas, gravadas, erros, simulacao, quem) VALUES (%s,%s,%s,%s,%s,%s,%s)',
           (modelo, arquivo[:200], n, gravadas, Jsonb(erros[:500]), simular, quem))
    return {'modelo': modelo, 'linhas': n, 'validas': validas, 'gravadas': gravadas, 'erros': erros, 'simulacao': simular}

def _um(c, sql, p=()):
    return c.execute(sql, p).fetchone()

def _ver(c, nome, leg=None):
    leg = leg or _um(c, 'SELECT max(numero) n FROM legislaturas')['n']
    v = _um(c, 'SELECT * FROM vereadores WHERE legislatura=%s AND lower(nome)=lower(%s)', (leg, nome))
    if not v:
        raise ValueError(f'vereador "{nome}" não cadastrado na {leg}ª Legislatura')
    return v

def _prop(c, l):
    p = _um(c, 'SELECT * FROM proposicoes WHERE tipo=%s AND numero=%s AND ano=%s', (l['tipo'], _int(l['numero'], 'numero'), _int(l['ano'], 'ano')))
    if not p:
        raise ValueError(f"proposição {l['tipo']} {l['numero']}/{l['ano']} não cadastrada (importe proposicoes.csv antes)")
    return p

def _sessao(c, data, nome=None):
    rows = c.execute('SELECT * FROM sessoes WHERE data=%s' + (' AND lower(nome)=lower(%s)' if nome else ''), (data, nome) if nome else (data,)).fetchall()
    if not rows:
        raise ValueError(f"sessão de {data.strftime('%d/%m/%Y')}{' (' + nome + ')' if nome else ''} não cadastrada (importe sessoes.csv antes)")
    if len(rows) > 1:
        raise ValueError(f"há {len(rows)} sessões em {data.strftime('%d/%m/%Y')}: informe o nome da sessão")
    return rows[0]

def _legislacao(c, l):
    from .fase8 import TIPOS_LEGISLACAO, RELACOES
    if l['tipo'] not in TIPOS_LEGISLACAO:
        raise ValueError(f"tipo deve ser um de: {', '.join(TIPOS_LEGISLACAO)}")
    num, ano = l['numero'].replace('.', ''), _int(l['ano'], 'ano')
    if not num.isdigit():
        raise ValueError('numero deve ser só o número do ato (ex.: 1234)')
    if not l['ementa']:
        raise ValueError('ementa é obrigatória')
    if l.get('link') and not l['link'].startswith('https://'):
        raise ValueError('link deve começar com https://')
    data = _data(l['data']) if l.get('data') else None
    if _um(c, 'SELECT 1 FROM legislacao WHERE lower(tipo)=lower(%s) AND numero=%s AND ano=%s', (l['tipo'], num, ano)):
        raise ValueError(f"{l['tipo']} {num}/{ano} já está na lista (veio do Diário ou de importação anterior)")
    novo = _um(c, "INSERT INTO legislacao (origem, tipo, numero, ano, data, ementa, pdf_url) VALUES ('importado',%s,%s,%s,%s,%s,%s) RETURNING id", (l['tipo'], num, ano, data, l['ementa'], l.get('link', '')))
    for rel in [x.strip() for x in (l.get('relacoes') or '').split('|') if x.strip()]:
        t, _, alvo = rel.partition(':')
        m = re.match(r'^\s*(.+?)\s+([\d.]+)\s*/\s*(\d{4})\s*$', alvo)
        if t.strip() not in RELACOES or not m:
            raise ValueError(f'relação "{rel}" inválida (use revoga:Lei 3/2001)')
        d = _um(c, 'SELECT id FROM legislacao WHERE lower(tipo)=lower(%s) AND numero=%s AND ano=%s', (m.group(1).strip(), m.group(2).replace('.', ''), int(m.group(3))))
        if not d:
            raise ValueError(f'ato citado "{alvo.strip()}" não está na lista (coloque-o em linha anterior)')
        c.execute('INSERT INTO legislacao_relacoes (origem_id, destino_id, tipo) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (novo['id'], d['id'], t.strip()))

def _linha(c, modelo, l):
    if modelo == 'legislacao':
        return _legislacao(c, l)
    if modelo == 'legislaturas':
        if not re.match(r'^\d{4}\s*[–-]\s*\d{4}$', l['anos']):
            raise ValueError('anos no formato 2021–2024')
        c.execute('INSERT INTO legislaturas (numero, anos, prefeito, vice) VALUES (%s,%s,%s,%s) ON CONFLICT (numero) DO UPDATE SET anos=EXCLUDED.anos, prefeito=EXCLUDED.prefeito, vice=EXCLUDED.vice',
                  (_int(l['numero'], 'numero'), re.sub(r'\s*[–-]\s*', '–', l['anos']), l.get('prefeito', ''), l.get('vice', '')))
    elif modelo == 'vereadores':
        leg = _int(l['legislatura'], 'legislatura')
        if not _um(c, 'SELECT 1 FROM legislaturas WHERE numero=%s', (leg,)):
            raise ValueError(f'legislatura {leg} não cadastrada')
        if not l['nome'] or not l['partido']:
            raise ValueError('nome e partido são obrigatórios')
        c.execute('INSERT INTO vereadores (nome, apelido, partido, legislatura, votos) VALUES (%s,%s,%s,%s,%s) ON CONFLICT (nome, legislatura) DO UPDATE SET apelido=EXCLUDED.apelido, partido=EXCLUDED.partido, votos=EXCLUDED.votos',
                  (l['nome'], l.get('apelido', ''), l['partido'], leg, int(l['votos']) if l.get('votos', '').isdigit() else None))
    elif modelo == 'mesas':
        leg = _int(l['legislatura'], 'legislatura')
        if l['cargo'] not in ('Presidente', 'Vice-presidente', '1º secretário', '2º secretário'):
            raise ValueError('cargo deve ser Presidente, Vice-presidente, 1º secretário ou 2º secretário')
        _ver(c, l['nome'], leg)
        bi = re.sub(r'\s*[–-]\s*', '–', l['bienio'])
        r = _um(c, 'SELECT id FROM mesas WHERE legislatura=%s AND bienio=%s AND cargo=%s', (leg, bi, l['cargo']))
        if r:
            c.execute('UPDATE mesas SET nome=%s WHERE id=%s', (l['nome'], r['id']))
        else:
            c.execute('INSERT INTO mesas (legislatura, bienio, cargo, nome) VALUES (%s,%s,%s,%s)', (leg, bi, l['cargo'], l['nome']))
    elif modelo == 'proposicoes':
        if l['tipo'] not in L.TIPO_SIGLA:
            raise ValueError(f"tipo \"{l['tipo']}\" fora da lista: {', '.join(L.TIPO_SIGLA)}")
        if not l['ementa']:
            raise ValueError('ementa obrigatória')
        autores = [a.strip() for a in re.split(r'[|]', l.get('autores', '')) if a.strip()]
        if not autores:
            raise ValueError('informe ao menos um autor')
        p = c.execute("""INSERT INTO proposicoes (tipo, numero, ano, autor, ementa, situacao, relator, origem) VALUES (%s,%s,%s,%s,%s,%s,%s,'importacao')
                         ON CONFLICT (tipo, numero, ano) DO UPDATE SET autor=EXCLUDED.autor, ementa=EXCLUDED.ementa, situacao=EXCLUDED.situacao, relator=EXCLUDED.relator RETURNING id""",
                      (l['tipo'], _int(l['numero'], 'numero'), _int(l['ano'], 'ano'), '; '.join(autores), l['ementa'], l.get('situacao') or 'Em tramitação', l.get('relator', ''))).fetchone()
        c.execute('DELETE FROM proposicao_autores WHERE proposicao_id=%s', (p['id'],))
        for a in autores:
            v = _um(c, 'SELECT id FROM vereadores WHERE lower(nome)=lower(%s) ORDER BY legislatura DESC LIMIT 1', (a,))
            c.execute('INSERT INTO proposicao_autores (proposicao_id, vereador_id, nome) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING', (p['id'], v['id'] if v else None, a))
    elif modelo == 'tramitacao':
        p = _prop(c, l)
        if not l['fase']:
            raise ValueError('fase obrigatória')
        c.execute("INSERT INTO tramitacao (proposicao_id, data, fase, descricao, origem, registrado_por) VALUES (%s,%s,%s,%s,'importacao','importação')", (p['id'], _data(l['data']), l['fase'], l.get('descricao', '')))
    elif modelo == 'sessoes':
        d = _data(l['data'])
        if not l['nome']:
            raise ValueError('nome da sessão obrigatório')
        if not _um(c, 'SELECT 1 FROM sessoes WHERE data=%s AND lower(nome)=lower(%s)', (d, l['nome'])):
            c.execute("INSERT INTO sessoes (nome, data, hora, tipo, origem) VALUES (%s,%s,%s,%s,'importacao')", (l['nome'], d, l.get('hora') or '19h', l.get('tipo') or 'Ordinária'))
    elif modelo == 'presencas':
        s = _sessao(c, _data(l['sessao_data']), l.get('sessao_nome') or None)
        if l['situacao'] not in ('presente', 'ausente', 'justificada'):
            raise ValueError('situacao deve ser presente, ausente ou justificada')
        v = _ver(c, l['vereador'])
        c.execute("INSERT INTO presencas (sessao_id, vereador_id, situacao, origem) VALUES (%s,%s,%s,'importacao') ON CONFLICT (sessao_id, vereador_id) DO UPDATE SET situacao=EXCLUDED.situacao, origem='importacao'", (s['id'], v['id'], l['situacao']))
    elif modelo == 'votos':
        s = _sessao(c, _data(l['sessao_data']))
        p = _prop(c, l)
        if l['voto'] not in L.VOTOS:
            raise ValueError('voto deve ser sim, nao, abstencao ou ausente')
        v = _ver(c, l['vereador'])
        it = _um(c, 'SELECT * FROM pauta_itens WHERE sessao_id=%s AND proposicao_id=%s', (s['id'], p['id']))
        if not it:
            ordem = _um(c, 'SELECT coalesce(max(ordem),0)+1 n FROM pauta_itens WHERE sessao_id=%s', (s['id'],))['n']
            it = c.execute('INSERT INTO pauta_itens (sessao_id, ordem, proposicao_id, descricao) VALUES (%s,%s,%s,%s) RETURNING *', (s['id'], ordem, p['id'], f"{L.rotulo(p)} — {p['ementa'][:200]}")).fetchone()
        c.execute("INSERT INTO votos (item_id, vereador_id, voto, origem) VALUES (%s,%s,%s,'importacao') ON CONFLICT (item_id, vereador_id) DO UPDATE SET voto=EXCLUDED.voto, origem='importacao'", (it['id'], v['id'], l['voto']))
        cont = {r['voto']: r['n'] for r in c.execute('SELECT voto, count(*) n FROM votos WHERE item_id=%s GROUP BY voto', (it['id'],)).fetchall()}
        res = 'aprovado' if cont.get('sim', 0) > cont.get('nao', 0) else 'rejeitado'
        c.execute('UPDATE pauta_itens SET resultado=%s WHERE id=%s', (res, it['id']))
    elif modelo == 'diarias':
        ini, fim = _data(l['inicio']), (_data(l['fim']) if l.get('fim') else None)
        try:
            valor = float(l['valor'].replace('.', '').replace(',', '.'))
        except ValueError:
            raise ValueError('valor inválido (use 1.234,56)')
        if not l['beneficiario'] or valor <= 0:
            raise ValueError('beneficiário e valor positivo são obrigatórios')
        c.execute("""INSERT INTO diarias_legislativo (chave, fonte, ano, beneficiario, cargo, destino, motivo, inicio, fim, valor) VALUES (%s,'importacao',%s,%s,%s,%s,%s,%s,%s,%s)
                     ON CONFLICT (chave) DO UPDATE SET motivo=EXCLUDED.motivo, valor=EXCLUDED.valor, coletado_em=now()""",
                  (chave('dl', l['beneficiario'], ini, fim, valor, l.get('destino')), ini.year, l['beneficiario'], l.get('cargo', ''), l.get('destino', ''), l.get('motivo', ''), ini, fim, valor))

def votacoes_importadas_tramitar(banco):
    """Depois de importar votos, registra na tramitação o resultado de cada item importado que ainda não tem esse evento."""
    for it in db.todos(banco, """SELECT i.*, s.nome sessao, s.data FROM pauta_itens i JOIN sessoes s ON s.id=i.sessao_id
                                 WHERE i.proposicao_id IS NOT NULL AND i.resultado IS NOT NULL AND NOT EXISTS (SELECT 1 FROM tramitacao t WHERE t.proposicao_id=i.proposicao_id AND t.sessao_id=i.sessao_id AND t.fase LIKE 'Votação%%')
                                 AND EXISTS (SELECT 1 FROM votos v WHERE v.item_id=i.id AND v.origem='importacao')"""):
        c = L.contagem(banco, it['id'])
        L.tramitar(banco, it['proposicao_id'], it['data'], 'Votação em Plenário (importada)', f"{'Aprovado' if it['resultado'] == 'aprovado' else 'Rejeitado'} na {it['sessao']}: {c['sim']} sim, {c['nao']} não, {c['abstencao']} abstenções, {c['ausente']} ausentes.",
                   sessao_id=it['sessao_id'], origem='importacao', quem='importação')

if __name__ == '__main__':
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in MODELOS:
        sys.exit(__doc__ + '\nModelos: ' + ', '.join(MODELOS))
    slug = a[a.index('--orgao') + 1] if '--orgao' in a else None
    o = db.um(db.PLATAFORMA, "SELECT * FROM orgaos WHERE slug=%s" if slug else "SELECT * FROM orgaos WHERE tipo='legislativo' ORDER BY id LIMIT 1", (slug,) if slug else ())
    rel = importar(o['banco'], a[0], open(a[1], 'rb').read(), simular='--gravar' not in a, arquivo=a[1])
    if a[0] == 'votos' and not rel['simulacao'] and not rel['erros']:
        votacoes_importadas_tramitar(o['banco'])
    print(f"{o['slug']} · {a[0]}: {rel['linhas']} linhas, {rel['validas']} válidas, {rel['gravadas']} gravadas{' (SIMULAÇÃO: nada gravado; use --gravar)' if rel['simulacao'] else ''}")
    for e in rel['erros']:
        print(f"  linha {e['linha']}: {e['erro']}")
    db.fechar()
    sys.exit(1 if rel['erros'] else 0)
