"""Worker: roda as coletas de cada órgão conforme as fontes configuradas (tabela `fontes`) e a frequência de cada uma.

  python -m app.worker           # laço contínuo
  python -m app.worker uma-vez   # roda todas as fontes uma vez e sai
A falha de uma fonte (ou de uma base) só é registrada em `coletas`; o portal continua com a última coleta válida."""
import sys, time, traceback
from datetime import datetime
from . import config, db
from . import agenda as AG
from .coletores import fiorilli, govbr, pncp, siconfi, tcesp, numeros, comum, indicadores, youtube, redes, tempo

MODULOS = {'fiorilli': fiorilli, 'govbr': govbr, 'pncp': pncp, 'siconfi': siconfi, 'tcesp': tcesp, 'youtube': youtube, 'redes': redes, 'tempo': tempo, **indicadores.MODULOS}
# fontes do painel de indicadores: só rodam para órgão com o módulo "bi" contratado e ligado
PAINEL = set(indicadores.MODULOS)
# padrão quando o órgão não escolheu agenda (ver app/agenda.py, que é a referência); o YouTube usa só esta tabela
# fonte -> (a cada N minutos, horas permitidas)
FREQ = {'fiorilli': (60, range(7, 20)), 'govbr': (180, range(6, 22)), 'pncp': (360, range(0, 24)), 'siconfi': (24 * 60, range(0, 24)), 'tcesp': (24 * 60, range(0, 24)),
        # painel: dados anuais (IBGE) e mensais (CNES, MDS) consultados uma vez por semana; números do próprio órgão a cada hora
        'ibge': (7 * 24 * 60, range(2, 6)), 'cnes': (7 * 24 * 60, range(2, 6)), 'mds': (7 * 24 * 60, range(2, 6)), 'pni': (7 * 24 * 60, range(2, 6)),
        'painel': (60, range(7, 20)),
        # dados anuais/bienais: INEP (planilhas, só baixa se mudarem) e IEG-M do TCESP, verificados a cada 30 dias
        'inep': (30 * 24 * 60, range(2, 6)), 'iegm': (30 * 24 * 60, range(2, 6)),
        # série mensal das finanças (Fiorilli): uma vez por dia, de madrugada
        'financas': (20 * 60, range(1, 5)), 'financas_prefeitura': (20 * 60, range(1, 5)),
        # YouTube: tique de 2 min; o coletor só consulta dentro das janelas da agenda (ou com transmissão ao vivo) e na varredura diária
        'youtube': (2, range(0, 24)),
        # redes sociais: últimas publicações (só com credencial e conta informada), a cada 6 h
        'redes': (6 * 60, range(6, 23)),
        # previsão do tempo (Open-Meteo): de hora em hora; Prefeitura e Câmara do mesmo município compartilham a coleta
        'tempo': (60, range(0, 24))}

def pronta(f, agora, ultimo):
    """A fonte deve rodar agora? Usa a agenda escolhida pelo órgão no painel (fontes.agenda) ou o padrão do sistema.
    O YouTube mantém o tique de 2 minutos (o coletor só consulta dentro da janela de cada transmissão)."""
    if f['fonte'] in AG.FIXAS:
        cada, horas = FREQ[f['fonte']]
        return agora.hour in horas and (ultimo is None or (agora - ultimo).total_seconds() >= cada * 60)
    return AG.deve_rodar(AG.da_fonte(f), agora, ultimo)

def fontes_ativas():
    """Fontes ligadas dos órgãos ativos (o órgão vem do cadastro: controle no papel "tudo", licenças no papel "no")."""
    from . import orgaos
    por_id = {o['id']: o for o in orgaos.todos()}
    return [dict(por_id[f['orgao_id']], fonte=f['fonte'], params=f['params'], agenda=f['agenda'])
            for f in db.todos(db.LOCAL, 'SELECT orgao_id, fonte, params, agenda FROM fontes WHERE ativo ORDER BY orgao_id, fonte') if f['orgao_id'] in por_id]

def tcesp_pendente(o, p):
    """TCESP: mensal (dia 20) ou enquanto faltar algum ano configurado."""
    if config.hoje().day == 20:
        return True
    return any(not db.um(o['banco'], "SELECT 1 FROM receitas WHERE fonte='tcesp' AND ano=%s LIMIT 1", (a,)) for a in p.get('anos', []))

def bi_ligado(o):
    from .web import modulos_do_orgao
    try:
        return bool(modulos_do_orgao(o).get('bi'))
    except Exception:
        return False

def rodar(o, fonte, p):
    inicio = datetime.now()
    comum.ORGAO.set(o['slug'])  # a amostra da última resposta de cada consulta fica associada ao órgão
    try:
        res = MODULOS[fonte].coletar(o, p)
    except Exception as e:
        res = [(fonte, False, 0, f'{type(e).__name__}: {e}')]
        traceback.print_exc()
    for base, ok, n, msg in res:
        comum.registrar(o['slug'], f'{fonte}:{base}', ok, n, msg, inicio)
        print(datetime.now(), 'OK' if ok else 'FALHA', o['slug'], f'{fonte}:{base}', n, msg, flush=True)
    if o['tipo'] == 'executivo' and fonte in ('fiorilli', 'govbr', 'siconfi'):
        try:
            numeros.atualizar(o)
        except Exception:
            traceback.print_exc()
    return res

def ultimas_execucoes():
    """Lembra a última coleta de cada fonte (no banco), para um reinício não repetir as fontes à toa."""
    r = {}
    for x in db.todos(db.LOCAL, "SELECT orgao_slug, split_part(fonte, ':', 1) f, max(inicio) t FROM coletas WHERE fonte LIKE '%%:%%' GROUP BY 1, 2"):
        r[(x['orgao_slug'], x['f'])] = x['t'].astimezone().replace(tzinfo=None)
    return r

def diario_tick(agora):
    """Rotina do Diário Oficial, nos horários de cada órgão (padrão 16h, 16h30 e 17h): edição sem atos, alerta e publicação, só com edição assinada."""
    from . import diario_servico as DS
    from .web import modulos_do_orgao
    from . import orgaos
    for o in orgaos.todos():  # qualquer órgão com o módulo (a Câmara pode ter Diário próprio, 23/11/2026)
        try:
            if not modulos_do_orgao(o).get('diario'):
                continue
            for r in DS.tick(o, agora):
                comum.registrar(o['slug'], 'diario:rotina', True, 1, r)
                print(agora, 'DIÁRIO', o['slug'], r, flush=True)
        except Exception as e:
            comum.registrar(o['slug'], 'diario:rotina', False, 0, f'{type(e).__name__}: {e}')
            traceback.print_exc()

def licencas_tick(estado):
    """Papel "no": busca as licenças na gestão a cada 5 minutos. Falha só é registrada: o portal segue com a última licença válida."""
    if config.PAPEL != 'no' or time.monotonic() - estado.get('t', -1e9) < 300:
        return
    estado['t'] = time.monotonic()
    from . import licenca
    try:
        msg = licenca.puxar()
        comum.registrar('', 'licencas:gestao', 'RECUSADA' not in msg, 0, msg)
    except Exception as e:
        comum.registrar('', 'licencas:gestao', False, 0, f'{type(e).__name__}: {str(e)[:200]}')

def ordens_tick(estado):
    """Papel "no": busca e executa as ordens da gestão a cada minuto (depois das licenças, para o órgão novo já ser conhecido)."""
    if config.PAPEL != 'no' or time.monotonic() - estado.get('t', -1e9) < 60:
        return
    estado['t'] = time.monotonic()
    from . import ordens
    try:
        msg = ordens.puxar()
        if not msg.startswith('0 ordem') or 'RECUSADA' in msg:
            comum.registrar('', 'ordens:gestao', 'RECUSADA' not in msg, 0, msg)
    except Exception as e:
        comum.registrar('', 'ordens:gestao', False, 0, f'{type(e).__name__}: {str(e)[:200]}')

def relatorio_tick(estado):
    """Papel "no": relatório técnico para a gestão a cada 5 minutos (a cada minuto com publicação de domínio em andamento)."""
    if config.PAPEL != 'no':
        return
    from . import relatorio
    intervalo = 60 if relatorio.com_pressa() else 300
    if time.monotonic() - estado.get('t', -1e9) < intervalo:
        return
    estado['t'] = time.monotonic()
    try:
        relatorio.enviar()
    except Exception as e:
        comum.registrar('', 'relatorio:gestao', False, 0, f'{type(e).__name__}: {str(e)[:200]}')

def convites_tick():
    """Gestão: manda os convites de primeiro acesso prontos (ordem executada e domínio do órgão no ar)."""
    if config.PAPEL == 'no':
        return
    from . import convites, instalacao
    try:
        instalacao.limpar()  # pacotes de segredos vencidos ou já baixados saem do disco
        n = convites.tick()
        if n:
            print(datetime.now(), 'CONVITES', n, 'enviado(s)', flush=True)
    except Exception:
        traceback.print_exc()

def mudancas_tick(estado):
    """Gestão: leva adiante as mudanças de órgão entre nós (uma etapa por vez, a cada minuto)."""
    if config.PAPEL == 'no' or time.monotonic() - estado.get('t', -1e9) < 60:
        return
    estado['t'] = time.monotonic()
    from . import mudancas, remocoes
    try:
        mudancas.avancar_todas()
        remocoes.avancar_todas()
    except Exception:
        traceback.print_exc()

def atendimento_tick(agora):
    """e-SIC/Ouvidoria (23/11/2026): a cada minuto, a fila de e-mails de cada órgão desta instalação; uma vez por dia (a partir
    das 7h), encerra complementos vencidos e manda à equipe o resumo dos prazos que vencem em até 2 dias."""
    from . import atendimento as A, orgaos
    for o in orgaos.todos():
        try:
            if agora.hour >= 7:
                r = A.rotina_diaria(o)
                if r:
                    comum.registrar(o['slug'], 'atendimento:rotina', True, r['encerrados'] + r['resumo'], f"{r['encerrados']} complemento(s) vencido(s) encerrado(s); {r['resumo']} prazo(s) no resumo")
            A.enviar_fila(o)
        except Exception as e:
            comum.registrar(o['slug'], 'atendimento:rotina', False, 0, f'{type(e).__name__}: {str(e)[:200]}')
            traceback.print_exc()

def portal_antigo_tick():
    """Busca no portal antigo (24/11/2026): avança as buscas em andamento por até 45 s a cada minuto, 1 pedido por segundo."""
    try:
        from . import portal_antigo
        portal_antigo.tick(45)
    except Exception:
        traceback.print_exc()

def main():
    ultimo = ultimas_execucoes()
    mud = {}
    lic, ords, rel = {}, {}, {}
    print('worker iniciado', flush=True)
    while True:
        licencas_tick(lic)
        ordens_tick(ords)
        relatorio_tick(rel)
        convites_tick()
        mudancas_tick(mud)
        agora = datetime.now()
        try:
            for f in fontes_ativas():
                k = (f['slug'], f['fonte'])
                if not pronta(f, agora, ultimo.get(k)):
                    continue
                if f['fonte'] in PAINEL and not bi_ligado(f):
                    ultimo[k] = agora
                    continue
                if f['fonte'] == 'tcesp' and not tcesp_pendente(f, f['params']):
                    ultimo[k] = agora
                    continue
                rodar(f, f['fonte'], f['params'])
                ultimo[k] = agora
        except Exception:
            traceback.print_exc()
        diario_tick(datetime.now())
        atendimento_tick(datetime.now())
        portal_antigo_tick()
        time.sleep(60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'uma-vez':
        so = set(sys.argv[2:])  # opcional: só estas fontes (ex.: uma-vez fiorilli pncp)
        for f in fontes_ativas():
            if (not so or f['fonte'] in so) and (f['fonte'] not in PAINEL or bi_ligado(f)):
                rodar(f, f['fonte'], f['params'])
        db.fechar()
    else:
        main()
