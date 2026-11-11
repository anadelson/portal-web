"""Operação do Diário Oficial (Lei 910/2026 e decreto de 25/03/2026), usada pelo painel, pelo worker e pela API entre órgãos.

Fluxo: abrir edição → fechar (PDF + PDF/A + etapas de assinatura por caderno) → assinar cada etapa (A1, nuvem, A3 por upload;
em MODO TESTE, certificados de teste) → publicar só com a edição totalmente assinada. Edição de teste nunca fica pública como oficial."""
import hashlib
from datetime import date, datetime
from pathlib import Path
from psycopg.types.json import Jsonb
from . import config, db, diario as D, assinatura as A

APP = Path(__file__).parent

def brasao_arquivo(o, ident):
    url = ((ident.get('brasao') or {}).get('url') or '')
    if url.startswith('/static/'):
        p = APP / url[1:]
        png = p.with_suffix('.png')
        return str(png if png.is_file() else p)
    if url.startswith('/midia/'):
        return str(Path(config.DADOS_DIR) / o['slug'] / 'midia' / url.split('/')[-1])
    return None

def designacao(b, etapa):
    return db.um(b, 'SELECT * FROM designacoes WHERE caderno=%s AND ativo ORDER BY id DESC LIMIT 1', (etapa,))

def proxima_ordinaria(b):
    return db.um(b, "SELECT coalesce(max(numero),0)+1 n FROM diario_edicoes WHERE letra=''")['n']

def em_andamento(b):
    return db.um(b, "SELECT * FROM diario_edicoes WHERE situacao IN ('montagem','fechada') ORDER BY id DESC LIMIT 1")

def abrir(b, quem, extra=False, data=None):
    if em_andamento(b):
        raise ValueError('Já existe uma edição em andamento.')
    data = data or config.hoje()
    if not extra and not D.dia_util(b, data):
        raise ValueError(f"{data.strftime('%d/%m/%Y')} não é dia útil para o Diário (fim de semana, feriado ou dia sem expediente).")
    if extra:
        ult = db.um(b, "SELECT numero FROM diario_edicoes WHERE letra='' AND situacao IN ('publicada','invalidada') ORDER BY numero DESC LIMIT 1")
        if not ult:
            raise ValueError('Publique uma edição ordinária antes de criar uma extra.')
        num = ult['numero']
        l = db.um(b, 'SELECT max(letra) l FROM diario_edicoes WHERE numero=%s', (num,))['l'] or ''
        if l == 'Z':
            raise ValueError('Limite de edições extras (A–Z) para este número.')
        letra = chr(ord(l) + 1) if l else 'A'
    else:
        if db.um(b, "SELECT 1 FROM diario_edicoes WHERE data=%s AND letra='' AND situacao<>'invalidada'", (data,)):
            raise ValueError('Já existe edição ordinária nesta data: use uma edição extra.')
        num, letra = proxima_ordinaria(b), ''
    resp = designacao(b, 'final')
    return db.exe(b, 'INSERT INTO diario_edicoes (numero, letra, data, responsavel, modo_teste) VALUES (%s,%s,%s,%s,%s) RETURNING *',
                  (num, letra, data, (resp['nome'] if resp else quem), A.modo_teste()))

def fechar(o, e, quem):
    """Inclui os atos aprovados com data-alvo até a data da edição (extra: todos os aprovados), gera PDF/A e define as etapas de assinatura."""
    b = o['banco']
    if e['letra']:
        db.exe(b, "UPDATE diario_atos SET edicao_id=%s WHERE situacao='aprovado' AND edicao_id IS NULL", (e['id'],))
    else:
        db.exe(b, "UPDATE diario_atos SET edicao_id=%s WHERE situacao='aprovado' AND edicao_id IS NULL AND coalesce(data_alvo, %s) <= %s", (e['id'], e['data'], e['data']))
    atos = db.todos(b, 'SELECT a.*, r.tipo rt, r.numero rn, ed.numero ren, ed.letra rel, ed.data red, r.pagina rp FROM diario_atos a LEFT JOIN diario_atos r ON r.id=a.retifica_ato_id LEFT JOIN diario_edicoes ed ON ed.id=r.edicao_id WHERE a.edicao_id=%s ORDER BY a.caderno, a.id', (e['id'],))
    for a in atos:
        if a['retifica_ato_id']:
            a['retifica'] = f"retifica {a['rt']} {a['rn']}, publicado na edição nº {a['ren']}{a['rel'] or ''} de {a['red'].strftime('%d/%m/%Y') if a['red'] else '?'}{', página ' + str(a['rp']) if a['rp'] else ''}"
    ident = dict(db.cfg(b, 'identidade', {}) or {}, dominio=o['dominio'])
    conf = db.cfg(b, 'diario', {}) or {}
    caminho, _, cod, paginas = D.gerar_pdf(e, atos, ident, str(Path(config.DADOS_DIR) / o['slug'] / 'diario'), teste=e['modo_teste'], brasao=brasao_arquivo(o, ident), lei=conf.get('lei'))
    pdfa = D.para_pdfa(caminho)
    for aid, pag in paginas.items():
        db.exe(b, 'UPDATE diario_atos SET pagina=%s WHERE id=%s', (pag, aid))
    etapas = [x for x in ('executivo', 'legislativo') if any(a['caderno'] == x for a in atos)] + ['final']
    lista = []
    for et in etapas:
        d = designacao(b, et)
        lista.append({'etapa': et, 'rotulo': A.ETAPAS[et], 'nome': d['nome'] if d else '', 'cargo': d['cargo'] if d else '', 'ato': (d['ato'] + (f" de {d['ato_data'].strftime('%d/%m/%Y')}" if d and d['ato_data'] else '')) if d else '',
                      'provedor': 'teste' if e['modo_teste'] else (d['provedor'] if d else ''), 'feita': False})
    sha = hashlib.sha256(Path(caminho).read_bytes()).hexdigest()
    db.exe(b, "UPDATE diario_edicoes SET situacao='fechada', sem_atos=%s, pdf_arquivo=%s, sha256=%s, codigo=%s, assinatura='pendente', assinaturas=%s, pdfa=%s WHERE id=%s",
           (len(atos) == 0, caminho, sha, cod, Jsonb(lista), pdfa, e['id']))
    return len(atos), cod, pdfa

def _concluir_etapa(b, e, etapa, novo_pdf: bytes, quem, validacao):
    Path(e['pdf_arquivo']).write_bytes(novo_pdf)
    lista = e['assinaturas']
    for x in lista:
        if x['etapa'] == etapa:
            x.update(feita=True, em=datetime.now().isoformat(timespec='seconds'), por=quem, signatario=validacao[-1]['signatario'] if validacao else '', carimbo=validacao[-1]['carimbo'] if validacao else None)
    completa = all(x['feita'] for x in lista)
    situacao = ('teste' if e['modo_teste'] else 'assinada') if completa else 'parcial'
    db.exe(b, 'UPDATE diario_edicoes SET assinaturas=%s, assinatura=%s, sha256=%s WHERE id=%s', (Jsonb(lista), situacao, hashlib.sha256(novo_pdf).hexdigest(), e['id']))
    return completa

def proxima_etapa(e):
    return next((x for x in e['assinaturas'] if not x['feita']), None)

def assinar_etapa(o, e, quem):
    """Assina a próxima etapa pendente no servidor (A1, nuvem ou certificados de teste). A3 usa receber_a3()."""
    b = o['banco']
    x = proxima_etapa(e)
    if not x:
        raise ValueError('Todas as etapas já estão assinadas.')
    ident = db.cfg(b, 'identidade', {}) or {}
    pdf = Path(e['pdf_arquivo']).read_bytes()
    novo = A.assinar(pdf, x['etapa'], designacao(b, x['etapa']), f"{x['rotulo']} — Diário Oficial nº {e['numero']}{e['letra']}", ident.get('nome_curto') or o['municipio'])
    return x['rotulo'], _concluir_etapa(b, e, x['etapa'], novo, quem, A.validar(novo))

def receber_a3(o, e, dados: bytes, quem):
    b = o['banco']
    x = proxima_etapa(e)
    if not x:
        raise ValueError('Todas as etapas já estão assinadas.')
    val = A.aceitar_upload_a3(Path(e['pdf_arquivo']).read_bytes(), dados, designacao(b, x['etapa']))
    return x['rotulo'], _concluir_etapa(b, e, x['etapa'], dados, quem, val)

def publicar(o, e, quem):
    b = o['banco']
    if e['situacao'] != 'fechada':
        raise ValueError('Feche a edição antes de publicar.')
    if e['assinatura'] not in ('assinada', 'teste'):
        raise ValueError('A edição só pode ser publicada depois de assinada em todas as etapas (lei municipal do Diário Oficial).')
    db.exe(b, "UPDATE diario_edicoes SET situacao='publicada', publicada_em=now() WHERE id=%s", (e['id'],))
    db.exe(b, "UPDATE diario_atos SET situacao='publicado' WHERE edicao_id=%s", (e['id'],))
    try:  # Fase 8: leis, decretos etc. entram sozinhos na página Legislação
        from . import fase8
        fase8.sincronizar(b)
    except Exception:
        pass  # a página Legislação sincroniza de novo ao ser aberta
    return e['modo_teste']

def invalidar(o, e, ato, comunicado, prorrogacao, quem):
    if e['situacao'] != 'publicada':
        raise ValueError('Só uma edição publicada pode ser invalidada.')
    if not ato or len(comunicado or '') < 20:
        raise ValueError('Informe o ato do Prefeito que invalida a edição e o comunicado de indisponibilidade.')
    db.exe(o['banco'], "UPDATE diario_edicoes SET situacao='invalidada', invalidacao=%s WHERE id=%s",
           (Jsonb({'ato': ato[:200], 'comunicado': comunicado[:2000], 'prorrogacao': (prorrogacao or '')[:1000], 'por': quem, 'em': datetime.now().isoformat(timespec='seconds')}), e['id']))

def alerta(b, tipo, msg):
    db.exe(b, 'INSERT INTO diario_alertas (tipo, mensagem) VALUES (%s,%s)', (tipo, msg))

def tick(o, agora: datetime):
    """Rotina do worker (a cada minuto, só órgãos com Diário), nos horários do órgão (padrão 16h, 16h30 e 17h):
    corte       dia útil sem edição e sem atos para hoje → gera, assina (A1 ou teste) a edição "sem atos";
    alerta      edição do dia sem assinatura completa → alerta ao responsável (painel);
    publicação  edição do dia fechada e totalmente assinada → publica (teste: só como teste, nunca oficial)."""
    if A.modo_teste() and not config.DIARIO_AUTOMATICO_TESTE:
        return []  # modo teste em produção: não gasta a numeração oficial com edições automáticas de teste
    b = o['banco']; hoje = agora.date(); res = []
    r = D.regras(b)
    if not D.dia_util(b, hoje) or agora.time() < r['t_corte']:
        return res
    ed = db.um(b, "SELECT * FROM diario_edicoes WHERE data=%s AND letra='' AND situacao<>'invalidada' ORDER BY id DESC LIMIT 1", (hoje,))
    if not ed and not em_andamento(b):
        pend = db.um(b, "SELECT count(*) n FROM diario_atos WHERE situacao IN ('revisao','aprovado') AND edicao_id IS NULL AND coalesce(data_alvo, %s) <= %s", (hoje, hoje))['n']
        if pend == 0:
            ed = abrir(b, 'worker (edição sem atos)', data=hoje)
            fechar(o, ed, 'worker')
            ed = db.um(b, 'SELECT * FROM diario_edicoes WHERE id=%s', (ed['id'],))
            try:
                while proxima_etapa(ed):
                    assinar_etapa(o, ed, 'worker'); ed = db.um(b, 'SELECT * FROM diario_edicoes WHERE id=%s', (ed['id'],))
                res.append(f"edição nº {ed['numero']} sem atos gerada e assinada")
            except A.NaoConfigurado as e:
                alerta(b, 'assinatura', f"Edição nº {ed['numero']} (sem atos) gerada, mas não assinada automaticamente: {e}")
                res.append('edição sem atos gerada; assinatura pendente')
    if ed:
        ed = db.um(b, 'SELECT * FROM diario_edicoes WHERE id=%s', (ed['id'],))
        if agora.time() >= r['t_alerta'] and ed['situacao'] != 'publicada' and ed['assinatura'] not in ('assinada', 'teste') and not ed['alerta_assinatura']:
            alerta(b, 'assinatura', f"{r['alerta_txt']}: a edição nº {ed['numero']} de hoje ainda não está assinada. Sem assinatura ela não será publicada.")
            db.exe(b, 'UPDATE diario_edicoes SET alerta_assinatura=TRUE WHERE id=%s', (ed['id'],))
            res.append('alerta de assinatura')
        if agora.time() >= r['t_publicacao'] and ed['situacao'] == 'fechada' and ed['assinatura'] in ('assinada', 'teste'):
            publicar(o, ed, 'worker')
            res.append(f"edição nº {ed['numero']} publicada" + (' (TESTE, não oficial)' if ed['modo_teste'] else ''))
    return res

def limpar_teste(o):
    """Ao passar para DIARIO_MODO=oficial: apaga as edições de TESTE (e os atos nelas) para a numeração oficial começar do nº 1."""
    b = o['banco']
    eds = db.todos(b, 'SELECT id, pdf_arquivo FROM diario_edicoes WHERE modo_teste')
    ids = [e['id'] for e in eds]
    if ids:
        db.exe(b, 'UPDATE diario_atos SET retifica_ato_id=NULL WHERE retifica_ato_id IN (SELECT id FROM diario_atos WHERE edicao_id = ANY(%s))', (ids,))
        db.exe(b, 'DELETE FROM diario_atos WHERE edicao_id = ANY(%s)', (ids,))
        db.exe(b, 'DELETE FROM diario_edicoes WHERE id = ANY(%s)', (ids,))
        for e in eds:
            if e['pdf_arquivo']:
                Path(e['pdf_arquivo']).unlink(missing_ok=True)
    return len(ids)

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'limpar-teste':
        if not A.modo_teste() or '--forcar' in sys.argv:
            for o in db.todos(db.PLATAFORMA, "SELECT * FROM orgaos WHERE tipo='executivo'"):
                print(o['slug'], ':', limpar_teste(o), 'edição(ões) de teste apagada(s)')
        else:
            print('Ainda em DIARIO_MODO=teste: troque para oficial no .env (ou use --forcar) antes de limpar.')
