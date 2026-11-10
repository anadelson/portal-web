/* Painel — página inicial: mapa do layout que acompanha a lista (antes de salvar). Sem JS, cada botão salva na hora. */
(function () {
  var lista = document.getElementById('lista-blocos'), mapa = document.getElementById('pg-mapa');
  if (!lista || !mapa) return;
  var form = document.getElementById('form-blocos'), pend = document.getElementById('pendentes'), mudancas = 0;
  document.documentElement.classList.add('js');
  form.querySelectorAll('.so-js').forEach(function (e) { e.hidden = false; });
  var det = document.getElementById('mapa');
  if (window.matchMedia('(max-width: 900px)').matches) det.removeAttribute('open');
  function itens() { return Array.prototype.slice.call(lista.children); }
  function desenhar() {
    mapa.querySelectorAll('.r:not(.cab)').forEach(function (r) { r.remove(); });
    itens().forEach(function (li, k) {
      li.querySelector('.n').textContent = k + 1;
      var vis = li.querySelector('input[type=checkbox]'); var on = vis ? vis.checked : true;
      li.classList.toggle('off', !on);
      if (li.dataset.regiao === 'topo') return;
      var r = document.createElement('div');
      r.className = 'r ' + (li.dataset.largura || '') + (on ? '' : ' off') + (li.dataset.regiao === 'rodape' ? ' rod' : '') + (li.dataset.chave === 'hero' ? ' hero' : '');
      r.dataset.id = li.dataset.id; r.textContent = li.dataset.nome + (on ? '' : ' (desligado)');
      r.addEventListener('mouseenter', function () { marcar(li.dataset.id); });
      r.addEventListener('click', function () { li.focus(); li.scrollIntoView({ block: 'nearest' }); marcar(li.dataset.id); });
      mapa.appendChild(r);
    });
  }
  function marcar(id) {
    itens().forEach(function (li) { li.classList.toggle('on', li.dataset.id === id); });
    mapa.querySelectorAll('.r').forEach(function (r) { r.classList.toggle('on', r.dataset.id === id); });
  }
  function sujo() { mudancas++; pend.hidden = false; pend.textContent = mudancas + (mudancas > 1 ? ' mudanças não salvas' : ' mudança não salva'); desenhar(); }
  lista.addEventListener('click', function (e) {
    var b = e.target.closest('button'); if (!b || !b.value) return;
    var p = b.value.split(':'); if (p[0] !== 'subir' && p[0] !== 'descer') return;
    e.preventDefault();
    var li = b.closest('li'), alvo = p[0] === 'subir' ? li.previousElementSibling : li.nextElementSibling;
    if (!alvo || alvo.dataset.regiao !== li.dataset.regiao) return;
    if (p[0] === 'subir') lista.insertBefore(li, alvo); else lista.insertBefore(alvo, li);
    b.focus(); sujo(); marcar(li.dataset.id);
  });
  lista.addEventListener('change', function (e) { if (e.target.type === 'checkbox') sujo(); });
  lista.addEventListener('focusin', function (e) { var li = e.target.closest('li'); if (li) marcar(li.dataset.id); });
  lista.addEventListener('mouseover', function (e) { var li = e.target.closest('li'); if (li) marcar(li.dataset.id); });
  window.addEventListener('beforeunload', function (e) { if (mudancas && !form.dataset.enviando) { e.preventDefault(); e.returnValue = ''; } });
  form.addEventListener('submit', function () { form.dataset.enviando = '1'; });
  desenhar();
})();

/* Identidade — cores: seletor visual + hexadecimal sincronizados, contraste AA calculado na hora e prévia ao vivo */
(function () {
  var form = document.getElementById('form-cores'), prev = document.getElementById('previa-tema');
  if (!form || !prev) return;
  function lum(h) { var c = [1, 3, 5].map(function (i) { var x = parseInt(h.substr(i, 2), 16) / 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); });
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]; }
  function contraste(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  form.querySelectorAll('.cor-campo').forEach(function (fs) {
    var cor = fs.querySelector('input[type=color]'), hex = fs.querySelector('input[name]'), aa = fs.querySelector('.aa'), alvo = fs.dataset.alvo;
    function atualizar(v) {
      if (!/^#[0-9A-Fa-f]{6}$/.test(v)) return;
      var c = contraste(v, alvo), ok = c >= 4.5;
      aa.innerHTML = 'contraste ' + c.toFixed(1).replace('.', ',') + ':1 <span class="chip ' + (ok ? 'ok' : 'erro') + '">' + (ok ? 'AA' : 'abaixo de 4,5:1') + '</span>';
      prev.style.setProperty(hex.name === 'cor' ? '--p-cor' : '--p-dest', v);
    }
    cor.addEventListener('input', function () { hex.value = cor.value.toUpperCase(); atualizar(hex.value); });
    hex.addEventListener('input', function () { if (/^#[0-9A-Fa-f]{6}$/.test(hex.value)) cor.value = hex.value; atualizar(hex.value); });
  });
})();

/* Editor de texto (Fase 9): contenteditable com lista fechada de formatação; o servidor limpa de novo (nh3). */
(function () {
  var PERMITIDAS = { H2: 1, H3: 1, P: 1, BR: 1, STRONG: 1, B: 1, EM: 1, I: 1, UL: 1, OL: 1, LI: 1, A: 1, BLOCKQUOTE: 1, TABLE: 1, THEAD: 1, TBODY: 1, TR: 1, TH: 1, TD: 1, FIGURE: 1, IMG: 1, FIGCAPTION: 1 };
  function limpar(no) {
    Array.prototype.slice.call(no.childNodes).forEach(function (n) {
      if (n.nodeType === 8) { n.remove(); return; }
      if (n.nodeType !== 1) return;
      limpar(n);
      var t = n.tagName;
      if (t === 'B') { var s = document.createElement('strong'); while (n.firstChild) s.appendChild(n.firstChild); n.replaceWith(s); n = s; t = 'STRONG'; }
      if (t === 'I') { var e = document.createElement('em'); while (n.firstChild) e.appendChild(n.firstChild); n.replaceWith(e); n = e; t = 'EM'; }
      if (t === 'H1') t = 'H2';
      if (!PERMITIDAS[t]) { if (/^(SCRIPT|STYLE|META|LINK|XML|O:P)$/.test(t)) { n.remove(); return; } while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n); n.remove(); return; }
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var ok = (t === 'A' && a.name === 'href') || (t === 'IMG' && (a.name === 'src' || a.name === 'alt')) || (t === 'TH' && a.name === 'scope');
        if (!ok) n.removeAttribute(a.name);
      });
    });
    return no;
  }
  document.querySelectorAll('[data-editor]').forEach(function (ed) {
    var simples = ed.querySelector('.ed-simples'), oculto = ed.querySelector('[data-ed-html]'), area = ed.querySelector('.ed-area'), barra = ed.querySelector('.ed-barra');
    var dlg = ed.querySelector('dialog.ed-img'), form = ed.closest('form');
    simples.hidden = true; area.hidden = false; barra.hidden = false; ed.querySelector('.ed-ajuda').hidden = false;
    ed.querySelector('label[for]').addEventListener('click', function (e) { e.preventDefault(); area.focus(); });
    if (oculto.value) area.innerHTML = oculto.value;
    else area.innerHTML = simples.value.split(/\n{2,}/).filter(function (x) { return x.trim(); }).map(function (x) { var p = document.createElement('p'); p.textContent = x; return p.outerHTML; }).join('');
    function cmd(c, v) { area.focus(); document.execCommand(c, false, v || null); }
    barra.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; var c = b.dataset.cmd;
      if (c === 'h2' || c === 'h3' || c === 'p' || c === 'blockquote') cmd('formatBlock', c.toUpperCase());
      else if (c === 'link') { var u = window.prompt('Endereço do link (https://…)'); if (u && /^(https:\/\/|mailto:|\/)/.test(u)) cmd('createLink', u); }
      else if (c === 'tabela') cmd('insertHTML', '<table><thead><tr><th scope="col">Coluna 1</th><th scope="col">Coluna 2</th></tr></thead><tbody><tr><td>…</td><td>…</td></tr></tbody></table><p></p>');
      else if (c === 'limpar') cmd('removeFormat');
      else if (c === 'imagem') { var sel = window.getSelection(); ed._range = sel.rangeCount ? sel.getRangeAt(0) : null; dlg.querySelector('.ed-img-erro').hidden = true; dlg.showModal(); }
      else cmd(c);
    });
    area.addEventListener('paste', function (e) {
      var h = e.clipboardData && e.clipboardData.getData('text/html'); if (!h) return;
      e.preventDefault();
      var doc = new DOMParser().parseFromString(h, 'text/html');
      cmd('insertHTML', limpar(doc.body).innerHTML);
    });
    dlg.querySelector('[data-img-ok]').addEventListener('click', function (e) {
      e.preventDefault();
      var arq = dlg.querySelector('[data-img-arq]').files[0], alt = dlg.querySelector('[data-img-alt]').value.trim(), erro = dlg.querySelector('.ed-img-erro');
      if (!arq || alt.length < 5) { erro.textContent = 'Escolha o arquivo e escreva o texto alternativo (pelo menos 5 caracteres).'; erro.hidden = false; return; }
      var fd = new FormData(); fd.append('csrf', form.querySelector('[name=csrf]').value); fd.append('arquivo', arq); fd.append('alt', alt);
      fd.append('credito', dlg.querySelector('[data-img-cred]').value);
      fetch('/admin/editor/imagem', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.url) { erro.textContent = d.erro || 'Não foi possível enviar.'; erro.hidden = false; return; }
          var leg = [dlg.querySelector('[data-img-leg]').value.trim(), dlg.querySelector('[data-img-cred]').value.trim()].filter(Boolean).join(' · ');
          var fig = document.createElement('figure'), img = document.createElement('img'); img.src = d.url; img.alt = alt; fig.appendChild(img);
          if (leg) { var fc = document.createElement('figcaption'); fc.textContent = leg; fig.appendChild(fc); }
          if (ed._range) { var s = window.getSelection(); s.removeAllRanges(); s.addRange(ed._range); }
          cmd('insertHTML', fig.outerHTML + '<p></p>'); dlg.close();
        });
    });
    dlg.querySelector('[data-img-cancelar]').addEventListener('click', function () { dlg.close(); });
    form.addEventListener('submit', function () { oculto.value = limpar(area.cloneNode(true)).innerHTML; simples.value = area.innerText; });
  });
})();

/* Menu do painel (10/11/2026): no celular, botão "Menu" abre o menu por cima (foco preso, Esc fecha). Sem JS, o menu aparece acima do conteúdo.
   Grupos do menu lembram se estavam abertos ou fechados (só neste navegador). */
(function () {
  var nav = document.getElementById('menu-painel'), bt = document.querySelector('.btn-menu');
  if (!nav) return;
  try {
    var salvo = JSON.parse(localStorage.getItem('painel-grupos') || '{}');
    nav.querySelectorAll('details.grupo').forEach(function (d) {
      var k = d.dataset.grupo;
      if (salvo[k] === false && !d.querySelector('[aria-current]')) d.removeAttribute('open');
      d.addEventListener('toggle', function () { salvo[k] = d.open; try { localStorage.setItem('painel-grupos', JSON.stringify(salvo)); } catch (e) {} });
    });
  } catch (e) {}
  if (!bt) return;
  var mq = window.matchMedia('(max-width: 820px)'), foco = 'a[href],button:not([disabled]),summary';
  document.documentElement.classList.add('js-menu');
  bt.hidden = false;
  function abrir() { nav.classList.add('aberto'); bt.setAttribute('aria-expanded', 'true'); document.body.classList.add('menu-aberto'); var f = nav.querySelector(foco); if (f) f.focus(); }
  function fechar() { nav.classList.remove('aberto'); bt.setAttribute('aria-expanded', 'false'); document.body.classList.remove('menu-aberto'); bt.focus(); }
  bt.addEventListener('click', function () { nav.classList.contains('aberto') ? fechar() : abrir(); });
  nav.addEventListener('keydown', function (e) {
    if (!mq.matches || !nav.classList.contains('aberto')) return;
    if (e.key === 'Escape') { e.preventDefault(); fechar(); return; }
    if (e.key !== 'Tab') return;
    var f = [].slice.call(nav.querySelectorAll(foco)).filter(function (x) { return x.offsetParent !== null; });
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
    else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
  });
  document.addEventListener('click', function (e) { if (mq.matches && nav.classList.contains('aberto') && !nav.contains(e.target) && e.target !== bt && !bt.contains(e.target)) fechar(); });
})();
