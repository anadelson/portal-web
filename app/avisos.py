"""Ajustes da Fase 8: avisos de configuração para o administrador (o que falta para cada recurso aparecer no portal)."""
from . import db

def transmissoes(o, mods):
    """Lista do que falta para as Transmissões aparecerem (cabeçalho e página inicial)."""
    from . import credenciais as CR
    falta = []
    if not (mods.get('transm') or mods.get('audiencias')):
        falta.append('o módulo de transmissões (“Transmissão de audiências”) não está contratado para este órgão — contratação no console do gestor')
    if not ((db.cfg(o['banco'], 'transmissao', {}) or {}).get('canal')):
        falta.append('o ID do canal oficial no YouTube (UC…) não foi informado em Painel → Transmissões')
    try:
        if not CR.situacao_orgao(o['banco'], 'youtube'):
            falta.append('a chave da YouTube Data API do órgão não foi cadastrada em Administração → Credenciais de API — sem ela, o “ao vivo” só funciona pelo botão manual')
    except Exception:
        pass
    return falta
