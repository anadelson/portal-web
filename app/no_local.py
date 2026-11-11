"""Cópia das tabelas operacionais para o banco local do nó (separação gestão × portais, etapa A2; usada na virada).

  python -m app.no_local exportar NOME_DO_NO arquivo.zip   # na VPS atual: só as linhas dos órgãos hospedados no nó
  python -m app.no_local importar arquivo.zip [--substituir] # no nó (PAPEL=no): tudo ou nada, conferindo contagens e somas
  python -m app.no_local conferir arquivo.zip               # mostra o manifesto (tabelas e contagens), sem importar

O arquivo leva um manifesto com, por tabela: colunas, número de linhas e SHA-256 do CSV. A importação roda numa transação
só: se um arquivo não confere com o manifesto, ou se a contagem no banco depois da cópia não bate, NADA é gravado.
Ficam de fora: tentativas de login (transitórias) e o cache de licenças (o nó busca na gestão).
O arquivo tem credenciais cifradas (CHAVE_CREDENCIAIS do .env) e dados operacionais: guarde com permissão 600 e apague depois."""
import hashlib, io, json, sys, zipfile
from datetime import datetime, timezone
from . import config, db

# tabela → (colunas, filtro SQL pelos órgãos do nó, coluna de id serial ou None)
def _tabelas():
    return {
        'fontes': ('orgao_id = ANY(%(ids)s)', None),
        'coletas': ('orgao_slug = ANY(%(slugs)s)', 'id'),
        'consulta_amostras': ('orgao_slug = ANY(%(slugs)s)', None),
        'consulta_testes': ('orgao_id = ANY(%(ids)s)', 'id'),
        'fontes_historico': ('orgao_id = ANY(%(ids)s)', 'id'),
        'credenciais_fontes': ('TRUE', None),
        'dados_publicos': ('ibge = ANY(%(ibges)s)', None),
        'indicadores_publicos': ('ibge = ANY(%(ibges)s)', None),
        'pares_orgaos': ('origem_id = ANY(%(ids)s) AND destino_id = ANY(%(ids)s)', None),
        'remessas_log': ('origem = ANY(%(slugs)s) OR destino = ANY(%(slugs)s)', 'id'),
        'config_console': ('TRUE', None),
    }
TABELAS = _tabelas()

def _colunas(banco, t):
    return [r['column_name'] for r in db.todos(banco, "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (t,))]

def _orgaos_do_no(nome):
    n = db.um(db.PLATAFORMA, 'SELECT * FROM nos WHERE nome=%s', (nome,))
    if not n:
        raise SystemExit(f'nó {nome!r} não cadastrado na gestão')
    os_ = db.todos(db.PLATAFORMA, 'SELECT id, slug, ibge FROM orgaos WHERE no_id=%s ORDER BY id', (n['id'],))
    if not os_:
        raise SystemExit(f'nenhum órgão hospedado no nó {nome!r} (Console → órgão → Hospedagem e licença)')
    return os_

def exportar(nome_no, destino):
    """Gera o arquivo do nó a partir do banco de controle. Devolve o manifesto."""
    os_ = _orgaos_do_no(nome_no)
    filtro = {'ids': [o['id'] for o in os_], 'slugs': [o['slug'] for o in os_], 'ibges': sorted({o['ibge'] for o in os_})}
    man = {'versao': 1, 'no': nome_no, 'orgaos': filtro['slugs'], 'gerado_em': datetime.now(timezone.utc).isoformat(), 'tabelas': {}}
    with zipfile.ZipFile(destino, 'w', zipfile.ZIP_DEFLATED) as z, db.conn(db.PLATAFORMA) as c:
        for t, (onde, _) in TABELAS.items():
            cols = _colunas(db.PLATAFORMA, t)
            buf = io.BytesIO()
            with c.cursor() as cur:
                lista = ', '.join(f'"{x}"' for x in cols)
                with cur.copy(f'COPY (SELECT {lista} FROM {t} WHERE {onde} ORDER BY 1) TO STDOUT WITH (FORMAT csv)', filtro) as cp:
                    for bloco in cp:
                        buf.write(bloco)
            dados = buf.getvalue()
            n = db.um(db.PLATAFORMA, f'SELECT count(*) n FROM {t} WHERE {onde}', filtro)['n']
            z.writestr(f'{t}.csv', dados)
            man['tabelas'][t] = {'colunas': cols, 'linhas': n, 'sha256': hashlib.sha256(dados).hexdigest()}
        z.writestr('manifesto.json', json.dumps(man, ensure_ascii=False, indent=1))
    return man

def ler(arquivo):
    with zipfile.ZipFile(arquivo) as z:
        man = json.loads(z.read('manifesto.json'))
        dados = {t: z.read(f'{t}.csv') for t in man['tabelas']}
    for t, d in dados.items():
        if hashlib.sha256(d).hexdigest() != man['tabelas'][t]['sha256']:
            raise ValueError(f'{t}: o arquivo não confere com o manifesto (SHA-256 diferente) — arquivo corrompido ou alterado')
        if t not in TABELAS:
            raise ValueError(f'{t}: tabela fora da lista permitida')
    return man, dados

def importar(arquivo, substituir=False):
    """Importa no banco local (papel "no"). Tudo numa transação: qualquer diferença desfaz tudo. Devolve {tabela: linhas}."""
    man, dados = ler(arquivo)
    feitas = {}
    with db.conn(db.LOCAL) as c:
        with c.transaction():
            for t, info in man['tabelas'].items():
                cols = _colunas(db.LOCAL, t)
                if cols != info['colunas']:
                    raise ValueError(f'{t}: colunas do banco local diferentes das do arquivo ({cols} × {info["colunas"]})')
                antes = c.execute(f'SELECT count(*) n FROM {t}').fetchone()['n']
                if antes and not substituir:
                    raise ValueError(f'{t}: o banco local já tem {antes} linha(s); use --substituir para trocar pelo conteúdo do arquivo')
                if substituir:
                    c.execute(f'DELETE FROM {t}')
                lista = ', '.join(f'"{x}"' for x in cols)
                with c.cursor() as cur:
                    with cur.copy(f'COPY {t} ({lista}) FROM STDIN WITH (FORMAT csv)') as cp:
                        cp.write(dados[t])
                depois = c.execute(f'SELECT count(*) n FROM {t}').fetchone()['n']
                if depois != info['linhas']:
                    raise ValueError(f'{t}: {depois} linha(s) no banco local, {info["linhas"]} no manifesto — nada foi gravado')
                serial = TABELAS[t][1]
                if serial:
                    c.execute(f"SELECT setval(pg_get_serial_sequence('{t}', '{serial}'), greatest((SELECT max({serial}) FROM {t}), 1))")
                feitas[t] = depois
    return feitas

def main(a):
    if not a:
        print(__doc__, file=sys.stderr); return 2
    if a[0] == 'exportar' and len(a) == 3:
        if config.PAPEL == 'no':
            print('exportar roda na gestão (banco de controle), não no nó', file=sys.stderr); return 2
        man = exportar(a[1], a[2])
        import os
        os.chmod(a[2], 0o600)
        for t, i in man['tabelas'].items():
            print(f'{t}: {i["linhas"]} linha(s)')
        print(f"arquivo {a[2]} (permissão 600) com os órgãos {', '.join(man['orgaos'])}")
    elif a[0] == 'importar' and len(a) >= 2:
        if config.PAPEL != 'no':
            print('importar roda no nó (PAPEL=no)', file=sys.stderr); return 2
        for t, n in importar(a[1], '--substituir' in a).items():
            print(f'{t}: {n} linha(s) conferidas')
        print('importação concluída: contagens e somas conferem')
    elif a[0] == 'conferir' and len(a) == 2:
        man, _ = ler(a[1])
        print(f"nó {man['no']} · órgãos {', '.join(man['orgaos'])} · gerado em {man['gerado_em']}")
        for t, i in man['tabelas'].items():
            print(f'{t}: {i["linhas"]} linha(s) · SHA-256 confere')
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0

if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
