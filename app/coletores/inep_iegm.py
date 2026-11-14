"""Coletores do painel: planilhas oficiais do INEP (IDEB e Saeb por município) e IEG-M do TCESP.

INEP (fonte 'inep', anual): baixa a edição mais recente de
  https://download.inep.gov.br/ideb/resultados/divulgacao_{etapa}_municipios_{ANO}.zip
(a planilha traz a série histórica inteira), filtra o código IBGE do órgão e grava IDEB, Saeb de Matemática e de
Língua Portuguesa (rede Pública), com rendimento, nota padronizada, metas projetadas e rede responsável no detalhe.
O servidor do INEP não envia o certificado intermediário: ele fica em deploy/certs/ e só completa a cadeia (a
verificação TLS continua ligada). Arquivo já importado (mesma data de modificação) não é baixado de novo.

IEG-M (fonte 'iegm', anual): consulta do painel público do TCESP (Pentaho CDA, sem documentação oficial: pode mudar
sem aviso), com o acesso anônimo publicado pelo próprio Tribunal (uso autorizado pelo órgão em 07/11/2026). Credencial: a cadastrada no console do gestor (Credenciais de fontes, cifrada); reserva: IEGM_USUARIO/IEGM_SENHA do .env.
Sem credencial ou com o IEG-M em modo manual, não coleta (sem erro).
Colunas mapeadas por metadata[].colName; o mapeamento pode ser fixado no parâmetro 'colunas' da fonte."""
import re, ssl, tempfile, time, unicodedata
from datetime import date, timedelta
from pathlib import Path
import httpx
from .. import config, db
from .. import painel as P
from .comum import buscar, num, guardar_publico, anotar
from . import planilha

# ---------- INEP ----------
INEP_URL = 'https://download.inep.gov.br/ideb/resultados/divulgacao_{etapa}_municipios_{edicao}.zip'
ETAPAS = {'ai': 'anos_iniciais', 'af': 'anos_finais', 'em': 'ensino_medio'}
LIMITE_ARQUIVO = 200 * 1024 * 1024
AVISO_CERT_DIAS = 60
ND = 'não divulgado pelo INEP'

def certificados():
    return sorted(Path(config.CERTS_INTERMEDIARIOS).glob('*.pem'))

def contexto_tls():
    """Raízes confiáveis (certifi) + intermediários públicos de deploy/certs. Verificação de cadeia e de nome ligadas."""
    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    for f in certificados():
        ctx.load_verify_locations(cafile=str(f))
    return ctx

def validade_certificados(hoje=None):
    """[(arquivo, vence_em, dias_restantes)] dos intermediários guardados."""
    from cryptography import x509
    hoje = hoje or config.hoje()
    out = []
    for f in certificados():
        c = x509.load_pem_x509_certificate(f.read_bytes())
        fim = (c.not_valid_after_utc if hasattr(c, 'not_valid_after_utc') else c.not_valid_after).date()
        out.append((f.name, fim, (fim - hoje).days))
    return out

def aviso_certificado(hoje=None):
    avisos = [f'O certificado intermediário {n} (cadeia TLS do INEP) vence em {v.strftime("%d/%m/%Y")} ({d} dias). Troque-o seguindo deploy/certs/LEIAME.md.'
              for n, v, d in validade_certificados(hoje) if d <= AVISO_CERT_DIAS]
    return ' '.join(avisos)

def _tentar(f, tentativas=4):
    """O servidor do INEP derruba conexões de vez em quando: novas tentativas com espera crescente (1 por vez)."""
    import time
    erro = None
    for i in range(tentativas):
        try:
            return f()
        except (httpx.TransportError, httpx.RemoteProtocolError) as e:
            erro = e
            time.sleep(5 * (i + 1))
    raise erro

def cabecalho(url):
    """HEAD do arquivo: (status, last-modified, tamanho)."""
    def f():
        t0 = time.monotonic()
        with httpx.Client(timeout=60, verify=contexto_tls(), headers={'User-Agent': config.USER_AGENT}) as c:
            r = c.head(url)
        res = r.status_code, r.headers.get('last-modified', ''), int(r.headers.get('content-length') or 0)
        anotar('inep', url, None, res[0], int((time.monotonic() - t0) * 1000), {'last-modified': res[1], 'tamanho_bytes': res[2]}, metodo='HEAD')
        return res
    return _tentar(f)

def baixar(url, destino):
    """Baixa em fluxo para um arquivo temporário (limite de tamanho), com verificação TLS completa."""
    def f():
        n = 0
        with httpx.Client(timeout=300, verify=contexto_tls(), headers={'User-Agent': config.USER_AGENT}) as c:
            with c.stream('GET', url) as r:
                r.raise_for_status()
                with open(destino, 'wb') as fx:
                    for parte in r.iter_bytes(1 << 16):
                        n += len(parte)
                        if n > LIMITE_ARQUIVO:
                            raise ValueError('arquivo maior que o limite')
                        fx.write(parte)
        anotar('inep', url, None, 200, 0, {'arquivo_baixado_bytes': n})
        return n
    return _tentar(f)

def _n(v):
    s = (v or '').strip()
    if not s or not re.match(r'^-?\d', s):
        return None
    return float(s.replace(',', '.')) if s.count(',') == 1 and '.' not in s else float(s)

def _marca(v):
    s = (v or '').strip()
    return 'ND' if s.upper() == 'ND' else ('-' if s in ('-', '--', '') else '')

def responsavel(redes):
    tem_m, tem_e = 'Municipal' in redes, 'Estadual' in redes
    if tem_m and not tem_e:
        return 'rede municipal (responsabilidade da Prefeitura)'
    if tem_e and not tem_m:
        return 'rede estadual (responsabilidade do Governo do Estado)'
    if tem_m and tem_e:
        return 'redes municipal e estadual'
    return 'rede ' + ', '.join(r.lower() for r in redes) if redes else ''

def ler_planilha_inep(caminho_zip, ibge, etapa):
    """Linhas do município (por rede) da planilha do INEP. Devolve {rede: {codigo_coluna: valor}}."""
    import zipfile
    z = zipfile.ZipFile(caminho_zip)
    nome = [n for n in z.namelist() if n.lower().endswith('.xlsx')]
    if not nome:
        raise ValueError('zip do INEP sem planilha .xlsx')
    cod, redes = None, {}
    with z.open(nome[0]) as fx:
        import io
        dados = io.BytesIO(fx.read())
    for _, l in planilha.linhas(dados):
        if cod is None:
            if 'NO_MUNICIPIO' in l and 'REDE' in l:
                cod = l
            continue
        d = dict(zip(cod, l))
        if str(d.get('CO_MUNICIPIO', '')).strip() == str(ibge):
            redes[d.get('REDE', '').strip()] = d
    if cod is None:
        raise ValueError('cabeçalho com NO_MUNICIPIO/REDE não encontrado na planilha do INEP')
    return redes

def valores_inep(redes, etapa, edicao):
    """Série de IDEB e Saeb (rede Pública) para gravar. Edições sem nota ficam como 'não divulgado pelo INEP'."""
    pub = redes.get('Pública') or redes.get('Publica')
    if not pub:
        return []
    resp = responsavel([r for r in redes if r not in ('Pública', 'Publica')])
    anos = sorted({int(m.group(1)) for k in pub for m in [re.match(r'VL_OBSERVADO_(\d{4})$', k)] if m})
    out, iniciou = [], False
    for a in anos:
        ideb, mat, lp = pub.get(f'VL_OBSERVADO_{a}'), pub.get(f'VL_NOTA_MATEMATICA_{a}'), pub.get(f'VL_NOTA_PORTUGUES_{a}')
        proj = _n(pub.get(f'VL_PROJECAO_{a}'))
        if not iniciou and _n(ideb) is None and _n(mat) is None and proj is None:
            continue  # antes da primeira edição com resultado ou meta, a rede não aparece na série
        iniciou = True
        base = f'rede pública = {resp}; planilha do INEP, edição {edicao}' if resp else f'planilha do INEP, edição {edicao}'
        det = {'rendimento': _n(pub.get(f'VL_INDICADOR_REND_{a}')), 'nota_padronizada': _n(pub.get(f'VL_NOTA_MEDIA_{a}')), 'projecao': proj, 'responsavel': resp}
        for chave, v, casas in ((f'edu_ideb_{etapa}', ideb, 1), (f'edu_saeb_mat_{etapa}', mat, 2), (f'edu_saeb_lp_{etapa}', lp, 2)):
            x = _n(v)
            if x is None:
                m = _marca(v)
                nota = base + ('; “ND” na planilha: resultado não divulgado' if m == 'ND' else '; sem resultado na planilha (“-”)')
                out.append((chave, str(a), P.fim_do_ano(a), None, ND, nota, det if chave.startswith('edu_ideb') else None))
            else:
                out.append((chave, str(a), P.fim_do_ano(a), round(x, casas), '', base, det if chave.startswith('edu_ideb') else None))
    return out

COMP_URL = {'BR': 'https://download.inep.gov.br/ideb/resultados/divulgacao_brasil_ideb_{edicao}.zip',
            'UF': 'https://download.inep.gov.br/ideb/resultados/divulgacao_regioes_ufs_ideb_{edicao}.zip'}
ABA_ETAPA = {'ai': 1, 'af': 2, 'em': 3}
UF_NOME = {'11': 'Rondônia', '12': 'Acre', '13': 'Amazonas', '14': 'Roraima', '15': 'Pará', '16': 'Amapá', '17': 'Tocantins', '21': 'Maranhão', '22': 'Piauí',
           '23': 'Ceará', '24': 'Rio Grande do Norte', '25': 'Paraíba', '26': 'Pernambuco', '27': 'Alagoas', '28': 'Sergipe', '29': 'Bahia', '31': 'Minas Gerais',
           '32': 'Espírito Santo', '33': 'Rio de Janeiro', '35': 'São Paulo', '41': 'Paraná', '42': 'Santa Catarina', '43': 'Rio Grande do Sul',
           '50': 'Mato Grosso do Sul', '51': 'Mato Grosso', '52': 'Goiás', '53': 'Distrito Federal'}

def _rede(v):
    return re.sub(r'\s*\(\d+\)\s*$', '', str(v or '')).strip()

def ler_comparacao(caminho_zip, etapa, alvo):
    """Linha da rede Pública da etapa: alvo = 'Brasil' ou o nome da UF. Devolve {ano: {ideb, mat, lp}} ou {}."""
    import zipfile, io
    z = zipfile.ZipFile(caminho_zip)
    nome = [n for n in z.namelist() if n.lower().endswith('.xlsx')][0]
    dados = io.BytesIO(z.read(nome))
    cod, achou = None, None
    for _, l in planilha.linhas(dados, ABA_ETAPA[etapa]):
        if cod is None:
            if any(str(c).startswith('VL_OBSERVADO_') for c in l):
                cod = l
            continue
        if len(l) > 1 and str(l[0]).strip() == alvo and _rede(l[1]) == 'Pública':
            achou = dict(zip(cod, l))
            break
    if not achou:
        return {}
    anos = sorted({int(k[-4:]) for k in achou if re.match(r'VL_OBSERVADO_\d{4}$', str(k))})
    out = {}
    for a in anos:
        v = {'ideb': _n(achou.get(f'VL_OBSERVADO_{a}')), 'mat': _n(achou.get(f'VL_NOTA_MATEMATICA_{a}')), 'lp': _n(achou.get(f'VL_NOTA_PORTUGUES_{a}'))}
        if any(x is not None for x in v.values()):
            out[str(a)] = v
    return out

def coletar_comparacao(ibge, edicao):
    """Brasil e UF do município (rede Pública, mesma etapa). Sem linha equivalente, não grava (o painel não mostra)."""
    uf = UF_NOME.get(str(ibge)[:2])
    res = []
    for escopo, url in COMP_URL.items():
        alvo = 'Brasil' if escopo == 'BR' else uf
        if not alvo:
            continue
        url = url.format(edicao=edicao)
        marca = db.um(db.LOCAL, "SELECT payload FROM dados_publicos WHERE ibge=%s AND fonte='inep_arquivo' AND chave=%s", (escopo if escopo == 'BR' else str(ibge)[:2], f'comparacao_{edicao}'))
        st, lm, tam = cabecalho(url)
        if st != 200:
            res.append(f'{escopo}: {st}')
            continue
        if marca and marca['payload'].get('last_modified') == lm:
            res.append(f'{escopo}: sem mudança')
            continue
        with tempfile.NamedTemporaryFile(suffix='.zip') as tmp:
            baixar(url, tmp.name)
            for etapa in ETAPAS:
                serie = ler_comparacao(tmp.name, etapa, alvo)
                if serie:
                    guardar_publico('BR' if escopo == 'BR' else str(ibge)[:2], 'ideb_comparacao', etapa, {'nome': alvo, 'rede': 'Pública', 'edicao': edicao, 'serie': serie})
        guardar_publico('BR' if escopo == 'BR' else str(ibge)[:2], 'inep_arquivo', f'comparacao_{edicao}', {'url': url, 'last_modified': lm})
        res.append(f'{escopo}: ok')
    return res

def edicoes_candidatas(hoje):
    """O IDEB é bienal (anos ímpares) e sai no ano seguinte: tenta da mais recente possível para trás."""
    return [a for a in range(hoje.year - 1, hoje.year - 8, -1) if a % 2 == 1]

def coletar_inep(o, p, hoje=None):
    hoje = hoje or config.hoje()
    ibge = str(p.get('ibge') or o['ibge'])
    res, aviso = [], aviso_certificado(hoje)
    for etapa, nome in ETAPAS.items():
        chaves = [f'edu_ideb_{etapa}', f'edu_saeb_mat_{etapa}', f'edu_saeb_lp_{etapa}']
        try:
            achou = None
            for ed in edicoes_candidatas(hoje):
                url = INEP_URL.format(etapa=nome, edicao=ed)
                st, lm, tam = cabecalho(url)
                if st == 200:
                    achou = (ed, url, lm, tam)
                    break
            if not achou:
                raise ValueError('nenhuma edição encontrada no servidor do INEP')
            ed, url, lm, tam = achou
            marca = db.um(db.LOCAL, "SELECT payload FROM dados_publicos WHERE ibge=%s AND fonte='inep_arquivo' AND chave=%s", (ibge, f'{etapa}_{ed}'))
            if marca and marca['payload'].get('last_modified') == lm:
                n = P.copiar_publicos(o['banco'], ibge, chaves)
                P.marcar_coleta(o['banco'], 'inep', True, f'edição {ed} já importada' + (f' · {aviso}' if aviso else ''), chaves)
                res.append((etapa, True, n, f'{nome}: edição {ed} sem mudança (já importada)' + (f' · ATENÇÃO: {aviso}' if aviso else '')))
                continue
            with tempfile.NamedTemporaryFile(suffix='.zip') as tmp:
                baixar(url, tmp.name)
                redes = ler_planilha_inep(tmp.name, ibge, etapa)
            vals = valores_inep(redes, etapa, ed)
            if not vals:
                raise ValueError(f'município {ibge} sem linha da rede pública na planilha')
            for chave, per, dref, v, texto, nota, det in vals:
                P.gravar_publico(ibge, chave, per, dref, 'inep', v, texto=texto, detalhe=det, nota=nota)
            guardar_publico(ibge, 'inep_arquivo', f'{etapa}_{ed}', {'url': url, 'last_modified': lm, 'tamanho': tam, 'redes': sorted(redes)})
            n = P.copiar_publicos(o['banco'], ibge, chaves)
            P.marcar_coleta(o['banco'], 'inep', True, f'edição {ed}: {len(vals)} valores' + (f' · {aviso}' if aviso else ''), chaves)
            res.append((etapa, True, n, f'{nome}: edição {ed}, {len(vals)} valores (redes: {", ".join(sorted(redes))})' + (f' · ATENÇÃO: {aviso}' if aviso else '')))
        except Exception as e:
            P.marcar_coleta(o['banco'], 'inep', False, f'{type(e).__name__}: {str(e)[:120]}', chaves)
            res.append((etapa, False, 0, f'{nome}: {type(e).__name__}: {str(e)[:150]}'))
    edicao = next((int(m.group(1)) for x in res for m in [re.search(r'edição (\d{4})', x[3])] if m), None)
    if edicao:
        try:
            r = coletar_comparacao(ibge, edicao)
            res.append(('comparacao', True, 0, f'comparação com UF e Brasil (rede pública), edição {edicao}: ' + ', '.join(r)))
        except Exception as e:
            res.append(('comparacao', False, 0, f'comparação com UF e Brasil: {type(e).__name__}: {str(e)[:120]}'))
    return res

# ---------- IEG-M (TCESP) ----------
IEGM_URL = 'https://painel.tce.sp.gov.br/pentaho/plugin/cda/api/doQuery'
IEGM_CONSULTA = {'path': '/public/ieg_m/iegm.cda', 'dataAccessId': 'faixaTodosMunicipiosPeriodo', 'outputType': 'json', 'parampRegiao': '-1'}
IEGM_PRIMEIRO_ANO_BASE = 2014
IEGM_CHAVES = [k for k, _ in P._IEGM]
# padrões (sem acento, minúsculos) que identificam cada dimensão no nome da coluna ou no valor de uma coluna "dimensão"
# Nome normalizado (sem acento, só letras e números, sem prefixos faixa/nota/vl) -> indicador. Só estes nomes são aceitos:
# coluna desconhecida é IGNORADA (com aviso na coleta), nunca encaixada por falta de regra.
IEGM_DIM = [('gestao_iegm', r'^(iegm|iegmgeral|geral)$'), ('gestao_iegm_educ', r'^i?educ'), ('gestao_iegm_saude', r'^i?saude'),
            ('gestao_iegm_planej', r'^i?planej'), ('gestao_iegm_fiscal', r'^i?fiscal'), ('gestao_iegm_amb', r'^i?amb'),
            ('gestao_iegm_cidade', r'^i?cidade'), ('gestao_iegm_ti', r'^i?gov(ti)?$|^i?govti|^i?tecnologia')]
# colunas de identificação (não são indicadores)
IEGM_IDENT = re.compile(r'^(exercicioref|exercicio|anoapuracao|anobase|ano|codigomunicipio|codmunicipio|codibge|codigoibge|ibge|nome|municipio|nomemunicipio|regiao|periodo)$')
FAIXA = re.compile(r'^(A|B\+|B|C\+|C)$')

def _sem_acento(s):
    return unicodedata.normalize('NFKD', str(s or '')).encode('ascii', 'ignore').decode().lower()

def origem_credencial():
    """De onde vem a credencial do IEG-M: 'plataforma' (console do gestor), 'env' (reserva) ou None (coleta desligada)."""
    from .. import credenciais as CR
    if CR.obter('iegm'):
        return 'plataforma'
    if config.IEGM_USUARIO and config.IEGM_SENHA:
        return 'env'
    return None

def credenciais():
    """Ordem: credencial cadastrada no console; senão IEGM_USUARIO/IEGM_SENHA do .env; senão nenhuma."""
    from .. import credenciais as CR
    c = CR.obter('iegm')
    if c:
        return c
    return (config.IEGM_USUARIO, config.IEGM_SENHA) if config.IEGM_USUARIO and config.IEGM_SENHA else None

def modo_automatico(banco):
    r = db.um(banco, "SELECT modo FROM indicadores WHERE chave='gestao_iegm'")
    return bool(r and r['modo'] == 'automatico')

def _faixa(v):
    s = str(v or '').strip().upper().replace(' ', '')
    return s if FAIXA.match(s) else ''

def _chave_col(nome):
    n = re.sub(r'[^a-z0-9]', '', _sem_acento(nome))
    n = re.sub(r'^(faixa|nota|vl|indice)', '', n) or n
    return n

def _dim(nome):
    n = _chave_col(nome)
    return next((k for k, p in IEGM_DIM if re.search(p, n)), None)

def mapear_iegm(d, ibge, fixo=None):
    """De uma resposta do CDA ({metadata, resultset}), extrai do município {indicador: (faixa, nota)}.
    Devolve (valores, colunas, info) com info = {'ano_base', 'edicao', 'ignoradas'}.
    Tabela larga (uma coluna por dimensão) ou longa (uma linha por dimensão). Colunas de identificação ficam de fora;
    colunas desconhecidas são ignoradas e listadas; duas colunas para o mesmo indicador = erro (nada é gravado)."""
    meta = d.get('metadata') or []
    cols = [m.get('colName', '') for m in sorted(meta, key=lambda m: m.get('colIndex', 0))]
    linhas = d.get('resultset') or []
    norm = [_chave_col(c) for c in cols]
    fixo = fixo or {}
    info = {'ano_base': None, 'edicao': None, 'ignoradas': []}
    alvo = {str(ibge), str(ibge)[:6]}
    if fixo.get('codigo') in cols:
        ic = cols.index(fixo['codigo'])
    else:
        ic = next((i for i, c in enumerate(norm) if re.match(r'^(codigomunicipio|codmunicipio|codibge|codigoibge|ibge)$', c)), None)
        if ic is None:
            ic = next((i for i in range(len(cols)) if any(str(l[i]).strip() in alvo for l in linhas if i < len(l))), None)
    if ic is None:
        return {}, cols, info
    minhas = [l for l in linhas if ic < len(l) and str(l[ic]).strip() in alvo]
    if not minhas:
        return {}, cols, info
    l0 = minhas[0]
    for i, c in enumerate(norm):
        if c in ('exercicioref', 'exercicio', 'anobase') and info['ano_base'] is None:
            info['ano_base'] = int(num(l0[i])) if num(l0[i]) is not None else None
        if c == 'anoapuracao':
            info['edicao'] = int(num(l0[i])) if num(l0[i]) is not None else None
    def tipo(i):
        vs = [l[i] for l in minhas if i < len(l) and l[i] not in (None, '')]
        if vs and all(_faixa(v) for v in vs):
            return 'faixa'
        if vs and all(isinstance(v, (int, float)) or num(v) is not None for v in vs):
            return 'nota'
        return 'texto'
    out = {}
    def por(chave, t, v, origem):
        fx, nt = out.get(chave, ('', None))
        if (t == 'faixa' and fx) or (t == 'nota' and nt is not None):
            raise ValueError(f'duas colunas para o mesmo indicador ({chave}, {t}): {origem}')
        out[chave] = (_faixa(v), nt) if t == 'faixa' else (fx, num(v))
    # mapeamento fixo pelo parâmetro da fonte: {'gestao_iegm': {'faixa': 'colName', 'nota': 'colName'}, ...}
    if any(k in fixo for k in IEGM_CHAVES):
        for chave in IEGM_CHAVES:
            f = fixo.get(chave) or {}
            if f.get('faixa') in cols:
                por(chave, 'faixa', l0[cols.index(f['faixa'])], f['faixa'])
            if f.get('nota') in cols:
                por(chave, 'nota', l0[cols.index(f['nota'])], f['nota'])
        return {k: v for k, v in out.items() if v[0] or v[1] is not None}, cols, info
    # tabela longa: uma coluna de texto com o nome da dimensão
    idim = next((i for i in range(len(cols)) if i != ic and not IEGM_IDENT.match(norm[i]) and tipo(i) == 'texto'
                 and all(_dim(l[i]) for l in minhas if i < len(l))), None)
    if idim is not None:
        ifx = next((i for i in range(len(cols)) if tipo(i) == 'faixa'), None)
        inota = next((i for i in range(len(cols)) if i not in (ic, idim) and not IEGM_IDENT.match(norm[i]) and tipo(i) == 'nota'), None)
        for l in minhas:
            chave = _dim(l[idim])
            if ifx is not None:
                por(chave, 'faixa', l[ifx], l[idim])
            if inota is not None:
                por(chave, 'nota', l[inota], l[idim])
        info['ignoradas'] = [cols[i] for i in range(len(cols)) if i not in (ic, idim, ifx, inota) and not IEGM_IDENT.match(norm[i])]
        return {k: v for k, v in out.items() if v[0] or v[1] is not None}, cols, info
    # tabela larga: só colunas com nome de indicador conhecido
    for i, c in enumerate(norm):
        if i == ic or IEGM_IDENT.match(c):
            continue
        chave, t = _dim(cols[i]), tipo(i)
        if not chave or t not in ('faixa', 'nota'):
            info['ignoradas'].append(cols[i])
            continue
        por(chave, t, l0[i], cols[i])
    return {k: v for k, v in out.items() if v[0] or v[1] is not None}, cols, info

def distribuicao_iegm(d):
    """Contagem de municípios por faixa do resultado geral (só números agregados; nenhum município identificado)."""
    meta = d.get('metadata') or []
    cols = [m.get('colName', '') for m in sorted(meta, key=lambda m: m.get('colIndex', 0))]
    ig = next((i for i, c in enumerate(cols) if _dim(c) == 'gestao_iegm' and not IEGM_IDENT.match(_chave_col(c))), None)
    if ig is None:
        return None
    cont = {f: 0 for f in P.FAIXAS_IEGM}
    for l in d.get('resultset') or []:
        f = _faixa(l[ig]) if ig < len(l) else ''
        if f:
            cont[f] += 1
    total = sum(cont.values())
    return {'faixas': cont, 'total': total} if total else None

def ler_iegm(ibge, anos_base, auth, fixo=None):
    """{ano_base: (valores, edicao)}, colunas vistas (só nomes) e colunas ignoradas. Ano-base e edição vêm de
    exercicio_ref e ano_apuracao da própria resposta; edição repetida é recusada."""
    out, colunas, ignoradas = {}, [], set()
    ler_iegm.distribuicoes = {}
    for a in anos_base:
        d = buscar('iegm', IEGM_URL, {**IEGM_CONSULTA, 'parampExercicio_mapa': a}, auth=auth, tentativas=2)
        if not isinstance(d, dict) or 'resultset' not in d:
            raise ValueError('a consulta do TCESP mudou: resposta sem "resultset"')
        vals, cols, info = mapear_iegm(d, ibge, fixo)
        colunas = cols or colunas
        ignoradas.update(info['ignoradas'])
        if not vals:
            continue
        ab = info['ano_base'] or a
        if ab != a:
            raise ValueError(f'ano-base pedido {a}, resposta com exercicio_ref {ab}')
        if ab in out:
            raise ValueError(f'edição repetida para o ano-base {ab}')
        out[ab] = (vals, info['edicao'] or ab + 1)
        dist = distribuicao_iegm(d)
        if dist:
            ler_iegm.distribuicoes[ab] = dict(dist, edicao=info['edicao'] or ab + 1)
    edicoes = [e for _, e in out.values()]
    if len(edicoes) != len(set(edicoes)):
        raise ValueError('a mesma edição (ano_apuracao) apareceu para anos-base diferentes')
    return out, colunas, sorted(ignoradas)

def coletar_iegm(o, p, hoje=None):
    """Sem credencial ou com o IEG-M em modo manual: não coleta e não registra erro (lista vazia)."""
    hoje = hoje or config.hoje()
    auth = credenciais()
    if not auth or not modo_automatico(o['banco']):
        return []
    ibge = str(p.get('ibge') or o['ibge'])
    feitos = {x['periodo'] for x in db.todos(db.LOCAL, "SELECT DISTINCT periodo FROM indicadores_publicos WHERE ibge=%s AND fonte='iegm' AND indicador='gestao_iegm'", (ibge,))}
    ultimo = hoje.year - 1
    anos = [a for a in range(IEGM_PRIMEIRO_ANO_BASE, ultimo + 1) if str(a) not in feitos or a >= ultimo - 1]
    try:
        vals, cols, ignoradas = ler_iegm(ibge, anos, auth, p.get('colunas'))
    except Exception as e:
        msg = f'consulta do TCESP falhou ({type(e).__name__}); mantido o último valor válido. Consulta sem documentação oficial: pode ter mudado.'
        P.marcar_coleta(o['banco'], 'iegm', False, msg)
        return [('iegm', False, 0, msg + f' Detalhe: {str(e)[:160]}')]
    if not vals:
        msg = f"município {ibge} não encontrado ou colunas não reconhecidas (colunas recebidas: {', '.join(cols)[:300]})"
        P.marcar_coleta(o['banco'], 'iegm', False, msg)
        return [('iegm', False, 0, msg)]
    n = 0
    for a, (por, edicao) in vals.items():
        for chave, (fx, nt) in por.items():
            nota = f'edição {edicao} (ano-base {a})' + (f'; nota {str(nt).replace(".", ",")}' if nt is not None else '')
            P.gravar_publico(ibge, chave, str(a), P.fim_do_ano(a), 'iegm', nt, texto=fx, nota=nota)
            n += 1
    for a, dist in getattr(ler_iegm, 'distribuicoes', {}).items():
        guardar_publico(ibge[:2], 'iegm_distribuicao', str(a), dist)  # por UF (código IBGE de 2 dígitos): só contagens
    copiados = P.copiar_publicos(o['banco'], ibge, IEGM_CHAVES)
    achadas = sorted({k for por, _ in vals.values() for k in por})
    faltam = [k for k in IEGM_CHAVES if k not in achadas]
    msg = (f"{n} valores em {len(vals)} edição(ões)" + (f"; sem dado nesta consulta: {', '.join(faltam)}" if faltam else '')
           + (f"; AVISO: colunas desconhecidas ignoradas: {', '.join(ignoradas)}" if ignoradas else ''))
    P.marcar_coleta(o['banco'], 'iegm', True, msg, achadas)
    return [('iegm', True, copiados, msg)]
