"""Refaz o PDF de uma edição de TESTE já publicada com o layout atual (capa nova, 2 colunas, carimbos) — 16/11/2026.

Só edições de TESTE (modo_teste): edição oficial publicada nunca é refeita (o PDF assinado é o documento legal).
Mantém número, data, código de verificação, atos e situação; guarda o PDF anterior ao lado (".anterior.pdf");
gera o PDF, converte para PDF/A, assina de novo cada etapa com os certificados de TESTE (com os carimbos laterais),
valida todas as assinaturas e só então grava. Registra na auditoria do órgão.

Uso (dentro do contêiner app):
  python -m deploy.refazer_edicao_teste <banco> <id_da_edicao> --simular   # gera, assina e valida em pasta temporária; não grava nada
  python -m deploy.refazer_edicao_teste <banco> <id_da_edicao>             # grava (PDF, hash, assinaturas, página de cada ato, auditoria)
"""
import hashlib, shutil, sys, tempfile
from datetime import datetime
from pathlib import Path
from psycopg.types.json import Jsonb
from app import assinatura as A, config, db, diario as D, diario_layout as L, diario_servico as DS, orgaos


def main(banco, eid, simular):
    o = next(x for x in orgaos.todos(ativos=False) if x['banco'] == banco)
    e = db.um(banco, 'SELECT * FROM diario_edicoes WHERE id=%s', (eid,))
    if not e:
        sys.exit('Edição não encontrada.')
    if not e['modo_teste']:
        sys.exit('Recusado: só edições de TESTE podem ser refeitas (edição oficial publicada é documento legal).')
    if not A.modo_teste():
        sys.exit('Recusado: o Diário não está em modo teste (certificados de teste indisponíveis).')
    atos = db.todos(banco, 'SELECT a.*, r.tipo rt, r.numero rn, ed.numero ren, ed.letra rel, ed.data red, r.pagina rp FROM diario_atos a LEFT JOIN diario_atos r ON r.id=a.retifica_ato_id '
                           'LEFT JOIN diario_edicoes ed ON ed.id=r.edicao_id WHERE a.edicao_id=%s ORDER BY a.caderno, a.id', (eid,))
    for a in atos:
        if a['retifica_ato_id']:
            a['retifica'] = f"retifica {a['rt']} {a['rn']}, publicado na edição nº {a['ren']}{a['rel'] or ''} de {a['red'].strftime('%d/%m/%Y') if a['red'] else '?'}{', página ' + str(a['rp']) if a['rp'] else ''}"
    ident = dict(db.cfg(banco, 'identidade', {}) or {}, dominio=o['dominio'])
    ini = db.um(banco, 'SELECT min(data) d FROM diario_edicoes WHERE modo_teste=%s', (e['modo_teste'],))['d']
    with tempfile.TemporaryDirectory() as tmp:
        caminho, _, cod, paginas = D.gerar_pdf(e, atos, ident, tmp, teste=True, brasao=DS.brasao_arquivo(o, ident), lei=D.regras(banco).get('lei'),
                                               orgao=o, ano_inicio=ini.year if ini else None)
        if e['codigo'] and cod != e['codigo']:
            sys.exit(f'Recusado: o código de verificação mudaria ({e["codigo"]} → {cod}).')
        pdfa = D.para_pdfa(caminho)
        pdf = Path(caminho).read_bytes()
        etapas = [x['etapa'] for x in e['assinaturas']]
        cad = [x for x in etapas if x != 'final']
        tk = L.tokens(ident.get('cor') or o.get('cor'))
        nova_lista = []
        for x in e['assinaturas']:
            et = x['etapa']
            car = {'rotulo': 'Assinatura final da edição' if et == 'final' else A.ETAPAS[et], 'lado': 'dir' if et == 'final' else 'esq',
                   'indice': cad.index(et) if et in cad else 0, 'n_cadernos': len(cad), 'cor': tk['cor'], 'esc': tk['esc']}
            pdf = A.assinar(pdf, et, DS.designacao(banco, et), f"{x['rotulo']} — Diário Oficial nº {e['numero']}{e['letra']}", ident.get('nome_curto') or o['municipio'], carimbo=car)
            val = A.validar(pdf)
            nova_lista.append(dict(x, feita=True, em=datetime.now().isoformat(timespec='seconds'), por='DTIC (layout novo da edição de teste)',
                                   signatario=val[-1]['signatario'] if val else '', carimbo=val[-1]['carimbo'] if val else None))
        val = A.validar(pdf)
        ok = len(val) == len(etapas) and all(v['integra'] and v['valida'] and v['confiavel'] and v.get('docmdp_ok') is not False for v in val)
        for v in val:
            print(f"  {v['campo']}: {v['signatario']} · íntegra={v['integra']} válida={v['valida']} confiável={v['confiavel']} modificação={v.get('modificacao')} carimbo do tempo={bool(v['carimbo_valido'])}")
        print(f"Edição nº {e['numero']}{e['letra']} · código {cod} · PDF/A={pdfa} · páginas dos atos {paginas} · {len(pdf)} bytes · assinaturas ok={ok}")
        if not ok:
            sys.exit('Recusado: alguma assinatura não validou. Nada foi gravado.')
        if simular:
            print('SIMULAÇÃO: nada foi gravado.')
            return
        atual = Path(e['pdf_arquivo'])
        guarda = atual.with_name(atual.stem + '.anterior.pdf')
        if atual.is_file() and not guarda.exists():
            shutil.copyfile(atual, guarda)
        atual.write_bytes(pdf)
        sha = hashlib.sha256(pdf).hexdigest()
        db.exe(banco, 'UPDATE diario_edicoes SET sha256=%s, pdfa=%s, assinaturas=%s WHERE id=%s', (sha, pdfa, Jsonb(nova_lista), eid))
        for aid, pag in paginas.items():
            db.exe(banco, 'UPDATE diario_atos SET pagina=%s WHERE id=%s', (pag, aid))
        db.exe(banco, 'INSERT INTO auditoria (usuario, acao, ip) VALUES (%s,%s,%s)',
               ('DTIC (manutenção)', f"Diário: edição de TESTE nº {e['numero']}{e['letra']} refeita com o layout novo (capa, 2 colunas, carimbos) e assinada de novo com certificados de teste; PDF anterior guardado", ''))
        print(f'Gravado: {atual} (anterior em {guarda.name}); sha256 {sha[:16]}…')


if __name__ == '__main__':
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], int(sys.argv[2]), '--simular' in sys.argv)
