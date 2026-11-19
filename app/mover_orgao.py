"""Mover um órgão de um nó para outro — a parte que roda DENTRO do app da instância (18/11/2026).

Quem chama é o deploy/no/mover_orgao.sh (na VPS, como root), que cuida do banco do órgão (pg_dump/pg_restore) e da
pasta de arquivos. Aqui ficam: as informações do órgão, a contagem de linhas do banco do órgão (para conferir a cópia)
e as linhas do banco LOCAL do nó que são daquele órgão (fontes, coletas, consultas, histórico das fontes).

  python -m app.mover_orgao info SLUG                  # id, banco, domínio e se o domínio está publicado neste nó (JSON)
  python -m app.mover_orgao contar BANCO               # {tabela: linhas} do banco do órgão (JSON)
  python -m app.mover_orgao exportar-local SLUG -      # ZIP (na saída padrão) com as linhas do banco local do órgão
  python -m app.mover_orgao importar-local - [--orgao-id ID]   # lê o ZIP da entrada padrão; tudo ou nada, conferindo contagens
  python -m app.mover_orgao limpar-local SLUG ID       # apaga do banco local as linhas do órgão (só se ele não for mais deste nó)

Credenciais das fontes (credenciais_fontes) são do NÓ, não do órgão: não vão no arquivo (o nó novo já recebe as dele da gestão)."""
import hashlib, io, json, sys, zipfile
from datetime import datetime, timezone
from . import config, db

# tabela do banco local → (filtro pelo órgão, coluna serial ou None). As mesmas do no_local, só as que são de um órgão.
TABELAS = {
    'fontes': ('orgao_id = %(id)s', None),
    'fontes_historico': ('orgao_id = %(id)s', 'id'),
    'consulta_testes': ('orgao_id = %(id)s', 'id'),
    'consulta_amostras': ('orgao_slug = %(slug)s', None),
    'coletas': ('orgao_slug = %(slug)s', 'id'),
}


def _colunas(banco, t):
    return [r['column_name'] for r in db.todos(banco, "SELECT column_name FROM information_schema.columns WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position", (t,))]


def _orgao(slug):
    from . import orgaos
    o = orgaos.por_slug(slug)
    if not o:
        raise SystemExit(f'órgão {slug!r} não está neste nó (sem licença aqui)')
    return o


def info(slug):
    from . import orgaos
    o = orgaos.por_slug(slug)
    pub = db.um(db.LOCAL, 'SELECT 1 x FROM dominios_publicados WHERE orgao_id=%s LIMIT 1', (o['id'],)) if o else None
    return {'slug': slug, 'hospedado_aqui': bool(o), 'id': o['id'] if o else None, 'banco': o['banco'] if o else None,
            'dominio': o['dominio'] if o else None, 'publicado': bool(pub), 'instancia': config.INSTANCIA, 'versao': _versao()}


def _versao():
    from .licenca import VERSAO_APP
    return VERSAO_APP()


def contar(banco):
    """Linhas de cada tabela do banco do órgão (para conferir a cópia: as duas pontas têm de bater)."""
    tabs = [r['t'] for r in db.todos(banco, "SELECT table_name t FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY 1")]
    return {t: db.um(banco, f'SELECT count(*) n FROM "{t}"')['n'] for t in tabs}


def exportar_local(slug):
    o = _orgao(slug)
    filtro = {'id': o['id'], 'slug': slug}
    man = {'versao': 1, 'orgao': {k: o[k] for k in ('id', 'slug', 'banco', 'dominio', 'nome', 'tipo')}, 'gerado_em': datetime.now(timezone.utc).isoformat(), 'tabelas': {}}
    buf_zip = io.BytesIO()
    with zipfile.ZipFile(buf_zip, 'w', zipfile.ZIP_DEFLATED) as z, db.conn(db.LOCAL) as c:
        for t, (onde, _) in TABELAS.items():
            cols = _colunas(db.LOCAL, t)
            lista = ', '.join(f'"{x}"' for x in cols)
            buf = io.BytesIO()
            with c.cursor() as cur:
                with cur.copy(f'COPY (SELECT {lista} FROM {t} WHERE {onde} ORDER BY 1) TO STDOUT WITH (FORMAT csv)', filtro) as cp:
                    for bloco in cp:
                        buf.write(bloco)
            dados = buf.getvalue()
            n = db.um(db.LOCAL, f'SELECT count(*) n FROM {t} WHERE {onde}', filtro)['n']
            z.writestr(f'{t}.csv', dados)
            man['tabelas'][t] = {'colunas': cols, 'linhas': n, 'sha256': hashlib.sha256(dados).hexdigest()}
        z.writestr('manifesto.json', json.dumps(man, ensure_ascii=False, indent=1))
    return buf_zip.getvalue(), man


def ler(conteudo):
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        man = json.loads(z.read('manifesto.json'))
        dados = {t: z.read(f'{t}.csv') for t in man['tabelas']}
    for t, d in dados.items():
        if t not in TABELAS:
            raise ValueError(f'{t}: tabela fora da lista permitida')
        if hashlib.sha256(d).hexdigest() != man['tabelas'][t]['sha256']:
            raise ValueError(f'{t}: o arquivo não confere com o manifesto (SHA-256 diferente)')
    return man, dados


def importar_local(conteudo):
    """Grava as linhas do órgão no banco local deste nó. Recusa se já houver linhas do órgão aqui. Tudo ou nada."""
    man, dados = ler(conteudo)
    filtro = {'id': man['orgao']['id'], 'slug': man['orgao']['slug']}
    feitas = {}
    with db.conn(db.LOCAL) as c:
        with c.transaction():
            for t, info_t in man['tabelas'].items():
                onde = TABELAS[t][0]
                cols = _colunas(db.LOCAL, t)
                if cols != info_t['colunas']:
                    raise ValueError(f'{t}: colunas do banco local diferentes das do arquivo (versões diferentes? atualize os dois nós para a mesma versão)')
                ja = c.execute(f'SELECT count(*) n FROM {t} WHERE {onde}', filtro).fetchone()['n']
                if ja:
                    raise ValueError(f'{t}: este nó já tem {ja} linha(s) do órgão {filtro["slug"]} — nada foi gravado')
                lista = ', '.join(f'"{x}"' for x in cols)
                serial = TABELAS[t][1]
                if serial and info_t['linhas']:  # ids do outro nó podem colidir com os daqui: grava com ids novos
                    sem = [x for x in cols if x != serial]
                    c.execute(f'CREATE TEMP TABLE _imp (LIKE {t} INCLUDING DEFAULTS) ON COMMIT DROP')
                    with c.cursor() as cur:
                        with cur.copy(f'COPY _imp ({lista}) FROM STDIN WITH (FORMAT csv)') as cp:
                            cp.write(dados[t])
                    s = ', '.join(f'"{x}"' for x in sem)
                    c.execute(f'INSERT INTO {t} ({s}) SELECT {s} FROM _imp ORDER BY "{serial}"')
                    c.execute('DROP TABLE _imp')
                elif info_t['linhas']:
                    with c.cursor() as cur:
                        with cur.copy(f'COPY {t} ({lista}) FROM STDIN WITH (FORMAT csv)') as cp:
                            cp.write(dados[t])
                depois = c.execute(f'SELECT count(*) n FROM {t} WHERE {onde}', filtro).fetchone()['n']
                if depois != info_t['linhas']:
                    raise ValueError(f'{t}: {depois} linha(s) gravadas, {info_t["linhas"]} no arquivo — nada foi gravado')
                feitas[t] = depois
    return man, feitas


def limpar_local(slug, orgao_id, mesmo_hospedado=False):
    """Apaga do banco local as linhas do órgão. Recusa se o órgão ainda for deste nó (licença no cache), salvo na
    EXCLUSÃO pedida pela gestão (mesmo_hospedado): aí a licença também sai daqui e o inventário confirma depois."""
    if not mesmo_hospedado and db.um(db.LOCAL, 'SELECT 1 x FROM licencas_cache WHERE orgao_id=%s', (orgao_id,)):
        raise SystemExit('o órgão ainda está neste nó (licença no cache): mude a hospedagem no console e espere até 5 minutos')
    filtro, feitas = {'id': orgao_id, 'slug': slug}, {}
    with db.conn(db.LOCAL) as c:
        with c.transaction():
            for t, (onde, _) in TABELAS.items():
                feitas[t] = c.execute(f'DELETE FROM {t} WHERE {onde}', filtro).rowcount
            c.execute('DELETE FROM dominios_publicados WHERE orgao_id=%s', (orgao_id,))
            if mesmo_hospedado:
                c.execute('DELETE FROM licencas_cache WHERE orgao_id=%s', (orgao_id,))
    return feitas


def main(a):
    if not a:
        print(__doc__, file=sys.stderr); return 2
    if config.PAPEL != 'no':
        print('mover_orgao roda num nó (PAPEL=no)', file=sys.stderr); return 2
    cmd = a[0]
    if cmd == 'info' and len(a) == 2:
        print(json.dumps(info(a[1]), ensure_ascii=False))
    elif cmd == 'orgaos' and len(a) == 1:   # órgãos com licença neste nó (o nó só é desinstalado sem nenhum)
        print(json.dumps(sorted(r['slug'] for r in db.todos(db.LOCAL, 'SELECT slug FROM licencas_cache'))))
    elif cmd == 'contar' and len(a) == 2:
        print(json.dumps(contar(a[1]), ensure_ascii=False, sort_keys=True))
    elif cmd == 'exportar-local' and len(a) == 3 and a[2] == '-':
        dados, man = exportar_local(a[1])
        sys.stdout.buffer.write(dados); sys.stdout.flush()
        print(' · '.join(f'{t}: {i["linhas"]}' for t, i in man['tabelas'].items()), file=sys.stderr)
    elif cmd == 'importar-local' and len(a) >= 2 and a[1] == '-':
        man, feitas = importar_local(sys.stdin.buffer.read())
        print(f"linhas do banco local do órgão {man['orgao']['slug']} importadas: " + ' · '.join(f'{t}: {n}' for t, n in feitas.items()))
    elif cmd == 'limpar-local' and len(a) in (3, 4):
        feitas = limpar_local(a[1], int(a[2]), mesmo_hospedado=a[3:] == ['--mesmo-hospedado'])
        print('linhas do banco local apagadas: ' + ' · '.join(f'{t}: {n}' for t, n in feitas.items()))
    else:
        print(__doc__, file=sys.stderr); return 2
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main(sys.argv[1:]))
    finally:
        db.fechar()
