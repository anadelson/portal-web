# Fileira de cartões (partials/fileira.html): teste do componente com 1, 2, 3, 5 e 8 cartões.
# Parte 1 (aqui, sem banco): HTML gerado — colunas, setas só marcadas como carrossel com 6+, ocultas sem JS, rótulos e ids.
# Parte 2 (navegador): com SAIDA=<pasta>, grava fileira.html (CSS e JS reais do portal) para tests/fileira_navegador.js medir
# larguras iguais, sem sobra à direita, setas só com 6+ e "1–5 de 8".   Uso: PYTHONPATH=. python tests/teste_fileira.py
import os, re, sys
from pathlib import Path
from jinja2 import Environment, FileSystemLoader

RAIZ = Path(__file__).resolve().parent.parent
env = Environment(loader=FileSystemLoader(str(RAIZ / 'app' / 'templates')), autoescape=True)
pagina = env.from_string('''{% from 'partials/fileira.html' import fileira_cartoes %}
{% for n in ns %}<section data-caso="{{ n }}"><h2>{{ n }} cartão(ões)</h2>
{% call fileira_cartoes(n, 'Teste com ' ~ n, 'fil-t' ~ n, tag='ul') %}{% for i in range(n) %}<li class="cartao-t"><a href="#c{{ n }}-{{ i }}">Cartão {{ i + 1 }}</a>{% if i % 2 %}<p>Texto mais longo para testar a mesma altura dos cartões da fileira.</p>{% endif %}</li>{% endfor %}{% endcall %}
</section>{% endfor %}''')
NS = (1, 2, 3, 5, 8)
html = pagina.render(ns=NS)
erros = []
def checa(c, nome):
    if not c:
        erros.append(nome)
for n in NS:
    b = html[html.find(f'data-caso="{n}"'):]
    b = b[:b.find('</section>')]
    checa(f'--n:{min(n, 5)}' in b, f'{n}: --n = {min(n, 5)} colunas')
    checa(b.count('class="cartao-t"') == n, f'{n}: {n} cartões no trilho')
    checa(f'id="fil-t{n}"' in b and f'aria-label="Teste com {n}"' in b, f'{n}: trilho com id e rótulo')
    nav = re.search(r'<div class="fil-nav"[^>]*>', b)
    if n == 1:
        checa(not nav, '1: sem setas')
    else:
        checa(nav and ' hidden' in nav.group(0), f'{n}: setas ocultas sem JavaScript')
        checa(nav and (('data-carrossel' in nav.group(0)) == (n > 5)), f'{n}: carrossel só com 6+')
        checa(b.count(f'aria-controls="fil-t{n}"') == 2 and 'aria-label="Anteriores: Teste com' in b and 'aria-label="Próximos: Teste com' in b, f'{n}: setas com aria-label e aria-controls')
        checa(f'1–{min(n, 5)} de {n}' in b, f'{n}: contagem "1–{min(n, 5)} de {n}"')
# o componente é o único jeito de montar as fileiras da página inicial e das páginas internas
usos = {p.name: p.read_text().count('fileira_cartoes(') for p in (RAIZ / 'app' / 'templates' / 'portal').glob('*.html')}
for t, minimo in (('home.html', 8), ('governo.html', 1), ('transparencia.html', 1), ('painel.html', 1)):
    checa(usos.get(t, 0) >= minimo, f'{t}: usa fileira_cartoes ({usos.get(t, 0)})')
css = (RAIZ / 'app' / 'static' / 'portal.css').read_text()
home = (RAIZ / 'app' / 'templates' / 'portal' / 'home.html').read_text()
checa('fil-atalhos' not in home and '<nav class="atalhos' in home, 'atalhos do topo fora da fileira (exceção)')
checa('grid-template-columns:repeat(auto-fit,minmax(230px,280px));justify-content:center' in css and 'max-width:1200px;margin:-72px auto' in css, 'atalhos: 230–280 px, centralizados, sobre a foto')
checa('grid-auto-columns:calc((100% - (var(--v) - 1) * var(--gap)) / var(--v))' in css and 'scroll-snap-type:x mandatory' in css, 'CSS: colunas iguais e scroll-snap')
checa(not re.search(r'animation[^;]*fil|setInterval', (RAIZ / 'app' / 'static' / 'portal.js').read_text()), 'JS: sem rolagem automática')

if os.environ.get('SAIDA'):
    d = Path(os.environ['SAIDA']); d.mkdir(parents=True, exist_ok=True)
    (d / 'fileira.html').write_text('<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>Teste da fileira</title><link rel="stylesheet" href="portal.css"><style>.cartao-t{background:#fff;border:1px solid #ccc;border-radius:12px;padding:12px}</style></head>'
        '<body><main style="width:100%;max-width:var(--largura-max);margin:0 auto;box-sizing:border-box;padding:32px var(--margem)">' + html + '</main><script src="portal.js"></script></body></html>')
    for f in ('portal.css', 'portal.js'):
        (d / f).write_text((RAIZ / 'app' / 'static' / f).read_text())

if erros:
    print('ERROS:', len(erros)); [print(e) for e in erros]; sys.exit(1)
print('fileira: tudo ok')
