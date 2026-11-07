"""Leitura de planilhas .xlsx em fluxo (sem biblioteca externa), para arquivos grandes como os do INEP.
Lê só a primeira aba, linha a linha, liberando memória a cada linha."""
import re, zipfile
from xml.etree.ElementTree import iterparse

NS = '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'

def _col(ref):
    n = 0
    for ch in re.match(r'[A-Z]+', ref).group(0):
        n = n * 26 + ord(ch) - 64
    return n - 1

def linhas(arquivo):
    """Gera (número da linha, [valores como texto]) da primeira aba de um .xlsx (caminho ou arquivo aberto)."""
    z = zipfile.ZipFile(arquivo)
    ss = []
    if 'xl/sharedStrings.xml' in z.namelist():
        for _, el in iterparse(z.open('xl/sharedStrings.xml')):
            if el.tag == NS + 'si':
                ss.append(''.join(t.text or '' for t in el.iter(NS + 't')))
                el.clear()
    aba = 'xl/worksheets/sheet1.xml' if 'xl/worksheets/sheet1.xml' in z.namelist() else sorted(n for n in z.namelist() if n.startswith('xl/worksheets/sheet'))[0]
    pai = None  # <sheetData>: as linhas são filhas dele; limpar a cada linha mantém a memória constante
    for ev, el in iterparse(z.open(aba), events=('start', 'end')):
        if ev == 'start':
            if el.tag == NS + 'sheetData':
                pai = el
            continue
        if el.tag != NS + 'row':
            continue
        r = {}
        for c in el.findall(NS + 'c'):
            v, t = c.find(NS + 'v'), c.get('t')
            if t == 'inlineStr':
                val = ''.join(x.text or '' for x in c.iter(NS + 't'))
            elif v is None:
                val = ''
            elif t == 's':
                val = ss[int(v.text)]
            else:
                val = v.text or ''
            r[_col(c.get('r'))] = val.strip()
        n = int(el.get('r'))
        el.clear()
        if pai is not None:
            pai.clear()
        yield n, ([r.get(i, '') for i in range(max(r) + 1)] if r else [])
