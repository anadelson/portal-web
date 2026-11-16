"""Texto dos atos do Diário (16/11/2026): junta as quebras manuais do texto de origem em parágrafos e separa assinatura e registro.

O conteúdo não muda (as mesmas palavras, na mesma ordem); muda só onde ficam as quebras de linha:
- junta as linhas de um mesmo parágrafo; mantém a quebra quando a linha termina em ponto ou dois-pontos,
  antes de "Art.", "§", "Parágrafo", incisos (I –, II -) e alíneas (a), b)) e antes de linhas só em maiúsculas
  terminadas em dois-pontos (RESOLVE:, DECRETA:);
- "Publique-se / e / Cumpra-se." vira uma linha só (sai naturalmente da regra acima);
- depois da linha de local e data ("Borá, 13 de novembro de 2026."): as linhas em maiúsculas são a assinatura
  (nome e cargo); o que vem depois é o registro ("Registrada nesta Secretaria..."), com o nome de quem registrou.
Textos formatados no editor (campo html) não passam por aqui: já têm parágrafos e alinhamento próprios."""
import re

MESES = 'janeiro|fevereiro|março|marco|abril|maio|junho|julho|agosto|setembro|outubro|novembro|dezembro'
DATA = re.compile(rf'^[^\d,]{{2,80}},\s*(em\s+)?\d{{1,2}}º?\s+de\s+({MESES})\s+de\s+\d{{4}}\.?$', re.I)
QUEBRA_ANTES = re.compile(r'^(Art\.?\s*\d|§|Parágrafo|[IVXLC]{1,6}\s*[-–—.)]\s|[a-z]\)\s)')
CHAMADA = re.compile(r'^[A-ZÀ-Ý ]{4,40}:$')  # RESOLVE:, DECRETA:, TORNA PÚBLICO:


def _maiusculas(s):
    letras = [c for c in s if c.isalpha()]
    return len(letras) >= 3 and sum(c.isupper() for c in letras) / len(letras) >= 0.85


def _juntar(linhas):
    pars, acc = [], ''
    def fecha():
        nonlocal acc
        if acc.strip():
            pars.append(acc.strip())
        acc = ''
    for l in linhas:
        if not l:
            fecha(); continue
        if acc and (QUEBRA_ANTES.match(l) or CHAMADA.match(l)):
            fecha()
        if acc.endswith('-') and not acc.endswith(' -'):
            acc += l          # palavra composta quebrada no hífen: "Educação-" + "Conselho"
        else:
            acc = f'{acc} {l}' if acc else l
        if l.endswith(('.', ':')) or CHAMADA.match(l):
            fecha()
    fecha()
    return pars


def estrutura(texto):
    """Texto simples do ato -> {'corpo': [parágrafos], 'data': str|None, 'assinatura': [nome, cargo...], 'registro': str|None, 'registro_ass': [...]}."""
    linhas = [l.strip() for l in (texto or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')]
    d = next((i for i, l in enumerate(linhas) if DATA.match(l)), None)
    if d is None:
        return {'corpo': _juntar(linhas), 'data': None, 'assinatura': [], 'registro': None, 'registro_ass': []}
    depois = [l for l in linhas[d + 1:] if l]
    ass = []
    while depois and _maiusculas(depois[0]) and len(ass) < 3 and len(depois[0]) <= 80:
        ass.append(depois.pop(0))
    reg_ass = []
    while depois and _maiusculas(depois[-1]) and len(depois[-1]) <= 80 and len(reg_ass) < 2:
        reg_ass.insert(0, depois.pop())
    reg = ' '.join(_juntar(depois)) if depois else None
    if not reg and reg_ass:  # só nomes depois da assinatura: são parte dela
        ass, reg_ass = ass + reg_ass, []
    return {'corpo': _juntar(linhas[:d]), 'data': linhas[d], 'assinatura': ass, 'registro': reg, 'registro_ass': reg_ass}


def texto_plano(texto):
    """Só as palavras, sem quebras (para comparar o texto antes e depois da diagramação)."""
    return ' '.join((texto or '').split())
