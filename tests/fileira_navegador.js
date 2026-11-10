// Fileira de cartões no navegador: abre fileira.html (gerado por teste_fileira.py com SAIDA=) e mede 1, 2, 3, 5 e 8 cartões.
// Uso (contêiner do Playwright): PAGINA=file:///caminho/fileira.html node fileira_navegador.js
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROME || '/ms-playwright/chromium-1148/chrome-linux/chrome' });
  const erros = [];
  const esperado = { 1920: { 1: 1, 2: 2, 3: 3, 5: 5, 8: 5 }, 1366: { 1: 1, 2: 2, 3: 3, 5: 5, 8: 5 }, 768: { 1: 1, 2: 2, 3: 3, 5: 3, 8: 3 }, 390: { 1: 1, 2: 1.5, 3: 1.5, 5: 1.5, 8: 1.5 } };
  for (const w of [1920, 1366, 768, 390]) {
    const p = await b.newPage({ viewport: { width: w, height: 900 } });
    await p.goto(process.env.PAGINA);
    await p.waitForTimeout(200);
    const r = await p.evaluate(() => [...document.querySelectorAll('[data-caso]')].map(s => {
      const t = s.querySelector('.fil-trilho'), cs = getComputedStyle(t), pl = parseFloat(cs.paddingLeft), pr = parseFloat(cs.paddingRight);
      const util = t.clientWidth - pl - pr, cards = [...t.children].map(c => c.getBoundingClientRect());
      const nav = s.querySelector('[data-fil-nav]');
      return { n: +s.dataset.caso, util, larg: cards.map(c => c.width), alt: cards.map(c => c.height), rola: t.scrollWidth > t.clientWidth + 2,
               setas: !!nav && !nav.hidden, cont: nav ? nav.querySelector('.fil-cont').textContent : null,
               visiveis: util / (cards[0].width + parseFloat(cs.columnGap || 0)) };
    }).concat([{ pagina: document.documentElement.scrollWidth }]));
    const pag = r.pop().pagina;
    if (pag > w) erros.push(`${w}: rolagem horizontal na página (${pag})`);
    for (const c of r) {
      const k = `${w}/${c.n}`;
      if (Math.max(...c.larg) - Math.min(...c.larg) > 1) erros.push(`${k}: larguras diferentes ${c.larg}`);
      if (Math.max(...c.alt) - Math.min(...c.alt) > 1) erros.push(`${k}: alturas diferentes ${c.alt}`);
      const e = esperado[w][c.n];
      if (Number.isInteger(e) && c.n <= e) {  // cabe tudo: N colunas sem sobra
        const soma = c.larg.reduce((a, x) => a + x, 0) + (c.n - 1) * 14;
        if (Math.abs(soma - c.util) > 2) erros.push(`${k}: sobra à direita (${soma} de ${c.util})`);
        if (c.rola || c.setas) erros.push(`${k}: não devia rolar nem ter setas`);
      } else {
        const v = (c.util + 14) / (c.larg[0] + 14);
        if (Math.abs(v - e) > 0.08) erros.push(`${k}: ${v.toFixed(2)} por vez (esperado ${e})`);
        if (!c.rola || !c.setas) erros.push(`${k}: devia ser carrossel com setas`);
        if (c.cont !== `1–${Math.floor(e)} de ${c.n}`) erros.push(`${k}: contagem "${c.cont}"`);
      }
    }
    if (w === 1920) {  // setas: próximo leva a "4–8 de 8"; teclado só dentro do trilho
      await p.click('[data-caso="8"] [data-fil="1"]');
      await p.waitForTimeout(900);
      const c = await p.textContent('[data-caso="8"] .fil-cont');
      if (c !== '4–8 de 8') erros.push(`1920/8: após "Próximos", contagem "${c}"`);
      await p.focus('[data-caso="8"] .fil-trilho > li:nth-child(1) a');
      await p.keyboard.press('ArrowRight');
      const f = await p.evaluate(() => document.activeElement.textContent);
      if (f !== 'Cartão 2') erros.push(`1920/8: seta do teclado levou a "${f}"`);
    }
    await p.close();
  }
  await b.close();
  if (erros.length) { console.log('ERROS:', erros.length); erros.forEach(e => console.log(e)); process.exit(1); }
  console.log('fileira no navegador: tudo ok');
})();
