# Escala tipográfica (10/11/2026): portal, painel e console usam só variáveis de tamanho; nenhum valor abaixo de 12 px (exceto "exemplo").
# Sem banco:  PYTHONPATH=. python tests/teste_escala.py
# A medição no navegador (todo texto visível >= 12 px) é feita nas capturas da conferência.
import re, sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)

# 1) templates: nenhum font-size em px/clamp solto (só var(--fs-...))
for p in sorted((RAIZ / 'app' / 'templates').rglob('*.html')):
    for i, l in enumerate(p.read_text().split('\n'), 1):
        for m in re.finditer(r'font-size:\s*([^;"}]+)', l):
            checa(m.group(1).strip().startswith('var(--fs-'), f'{p.relative_to(RAIZ)}:{i}: font-size solto ({m.group(1).strip()})')

# 2) folhas: font-size só por variável (exceto unidades relativas como .92em); variáveis com mínimo de 12 px
for nome in ('portal.css', 'admin.css'):
    css = (RAIZ / 'app' / 'static' / nome).read_text()
    raiz = ''.join(re.findall(r':root\{[^}]*--fs-[^}]*\}', css))
    checa(raiz, f'{nome}: escala em variáveis no :root')
    corpo = re.sub(r':root\{[^}]*\}', '', css)
    for m in re.finditer(r'font-size:\s*([^;}!]+)', corpo):
        v = m.group(1).strip()
        checa(v.startswith('var(--fs-') or v.endswith('em') or v == 'inherit', f'{nome}: font-size solto ({v})')
    for var, val in re.findall(r'(--fs-[a-z0-9-]+):\s*([^;}]+)', raiz):
        px = [float(x) for x in re.findall(r'([\d.]+)px', val)]
        if px and var != '--fs-exemplo':
            checa(min(px) >= 12, f'{nome}: {var} abaixo de 12 px ({val})')

# 3) valores do pedido
p = (RAIZ / 'app' / 'static' / 'portal.css').read_text()
for frag in ('--fs-base:17px', '--lh-base:1.55', '--fs-acess:13px', '--fs-inst:15px', '--fs-menu:16px', '--fs-hero:clamp(34px,6vw,50px)', '--fs-lead:19px',
             '--fs-h1:clamp(28px,4.2vw,36px)', '--fs-intro:18px', '--fs-h2:clamp(22px,2.6vw,26px)', '--fs-h2-gestao:clamp(24px,3vw,28px)',
             '--fs-h2-destaque:clamp(24px,3vw,30px)', '--fs-h2-cartao:22px', '--fs-desc:15px', '--fs-meta:13px', '--fs-etq:12px', '--fs-exemplo:11px',
             '--fs-btn:17px', '--fs-num:28px', 'nav.menu a{font-size:var(--fs-menu)}', '.home .sub{font-size:var(--fs-desc)}'):
    checa(frag in p, f'portal.css: {frag}')
a = (RAIZ / 'app' / 'static' / 'admin.css').read_text()
for frag in ('--fs-base:15px', '--fs-tela:23px', '--fs-secao:18px', '--fs-rotulo:14px', '--fs-campo:15px', '--fs-tab-cab:13px', '--fs-nota:12px',
             '--fs-btn:15px', '--alt-btn:40px', '.btn,.principal button{font-size:var(--fs-btn);font-weight:600;min-height:var(--alt-btn)}'):
    checa(frag in a, f'admin.css: {frag}')

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('escala: tudo ok')
