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
    if (!cor || !hex || !aa) return;  // grupo sem cor (largura máxima)
    function atualizar(v) {
      if (!/^#[0-9A-Fa-f]{6}$/.test(v)) return;
      var c = contraste(v, alvo), ok = c >= 4.5;
      aa.innerHTML = 'contraste ' + c.toFixed(1).replace('.', ',') + ':1 <span class="chip ' + (ok ? 'ok' : 'erro') + '">' + (ok ? 'AA' : 'abaixo de 4,5:1') + '</span>';
      prev.style.setProperty(fs.dataset.var || (hex.name === 'cor' ? '--p-cor' : '--p-dest'), v);
    }
    cor.addEventListener('input', function () { hex.value = cor.value.toUpperCase(); atualizar(hex.value); });
    hex.addEventListener('input', function () { if (/^#[0-9A-Fa-f]{6}$/.test(hex.value)) cor.value = hex.value; atualizar(hex.value); });
  });
})();

/* Editor de texto (Fase 9; ampliado em 15/11/2026): contenteditable com lista fechada de formatação; o servidor limpa de novo (nh3).
   Alinhamento vira classe (al-centro, al-dir, al-just), nunca style; vídeo do YouTube é um link marcado que o portal mostra como player. */
(function () {
  var PERMITIDAS = { H2: 1, H3: 1, H4: 1, P: 1, BR: 1, STRONG: 1, B: 1, EM: 1, I: 1, U: 1, S: 1, STRIKE: 1, DEL: 1, SUB: 1, SUP: 1, MARK: 1, HR: 1, UL: 1, OL: 1, LI: 1, A: 1, BLOCKQUOTE: 1,
    TABLE: 1, THEAD: 1, TBODY: 1, TR: 1, TH: 1, TD: 1, FIGURE: 1, IMG: 1, FIGCAPTION: 1, CAPTION: 1 };
  var TROCA = { B: 'STRONG', I: 'EM', STRIKE: 'S', DEL: 'S', H1: 'H2', H5: 'H4', H6: 'H4' };
  var ALINHA = ['al-centro', 'al-dir', 'al-just'], COM_CLASSE = { P: 1, H2: 1, H3: 1, H4: 1, FIGURE: 1, TD: 1, TH: 1, LI: 1, BLOCKQUOTE: 1 };
  var BLOCOS = 'P,H2,H3,H4,BLOCKQUOTE,LI,FIGURE,TD,TH';
  function renomear(n, t) { var s = document.createElement(t); while (n.firstChild) s.appendChild(n.firstChild); Array.prototype.slice.call(n.attributes).forEach(function (a) { s.setAttribute(a.name, a.value); }); n.replaceWith(s); return s; }
  function limpar(no) {
    Array.prototype.slice.call(no.childNodes).forEach(function (n) {
      if (n.nodeType === 8) { n.remove(); return; }
      if (n.nodeType !== 1) return;
      limpar(n);
      var t = n.tagName;
      if (TROCA[t]) { n = renomear(n, TROCA[t]); t = n.tagName; }
      if (!PERMITIDAS[t]) { if (/^(SCRIPT|STYLE|META|LINK|XML|O:P|IFRAME|OBJECT)$/.test(t)) { n.remove(); return; } while (n.firstChild) n.parentNode.insertBefore(n.firstChild, n); n.remove(); return; }
      var alinhado = (n.style && n.style.textAlign) || n.getAttribute('align') || '';
      Array.prototype.slice.call(n.attributes).forEach(function (a) {
        var ok = (t === 'A' && a.name === 'href') || (t === 'IMG' && (a.name === 'src' || a.name === 'alt')) || (t === 'TH' && a.name === 'scope') || a.name === 'class';
        if (!ok) n.removeAttribute(a.name);
      });
      var cl = (n.getAttribute('class') || '').split(/\s+/).filter(function (c) { return (COM_CLASSE[t] && ALINHA.indexOf(c) >= 0) || (t === 'A' && c === 'video'); });
      if (COM_CLASSE[t] && !cl.length && /center|right|justify/.test(alinhado)) cl = [{ center: 'al-centro', right: 'al-dir', justify: 'al-just' }[alinhado.match(/center|right|justify/)[0]]];
      if (cl.length) n.setAttribute('class', cl.join(' ')); else n.removeAttribute('class');
    });
    return no;
  }
  function youtube(u) { var m = /^https:\/\/(?:www\.)?(?:youtube\.com\/watch\?v=|youtu\.be\/|youtube\.com\/shorts\/|youtube\.com\/embed\/|youtube-nocookie\.com\/embed\/)([\w-]{11})/.exec((u || '').trim()); return m ? m[1] : ''; }
  document.querySelectorAll('[data-editor]').forEach(function (ed) {
    var simples = ed.querySelector('.ed-simples'), oculto = ed.querySelector('[data-ed-html]'), area = ed.querySelector('.ed-area'), barra = ed.querySelector('.ed-barra');
    var fonte = ed.querySelector('.ed-fonte'), rodape = ed.querySelector('.ed-rodape'), conta = ed.querySelector('.ed-conta'), modo = ed.querySelector('.ed-modo');
    var dlg = ed.querySelector('dialog.ed-img:not(.ed-link):not(.ed-video)'), dlgL = ed.querySelector('dialog.ed-link'), dlgV = ed.querySelector('dialog.ed-video');
    var sel = barra.querySelector('[data-bloco]'), tabGrupo = barra.querySelector('.ed-tab'), form = ed.closest('form'), salvo = null;
    simples.hidden = true; area.hidden = false; barra.hidden = false; rodape.hidden = false; ed.querySelector('.ed-ajuda').hidden = false;
    ed.querySelector('label[for]').addEventListener('click', function (e) { e.preventDefault(); area.focus(); });
    if (oculto.value) area.innerHTML = oculto.value;
    else area.innerHTML = simples.value.split(/\n{2,}/).filter(function (x) { return x.trim(); }).map(function (x) { var p = document.createElement('p'); p.textContent = x; return p.outerHTML; }).join('');
    try { document.execCommand('defaultParagraphSeparator', false, 'p'); } catch (e) {}
    function guardar() { var s = window.getSelection(); if (s.rangeCount && area.contains(s.anchorNode)) salvo = s.getRangeAt(0).cloneRange(); }
    function restaurar() { area.focus(); if (salvo) { var s = window.getSelection(); s.removeAllRanges(); s.addRange(salvo); } }
    function cmd(c, v) { restaurar(); document.execCommand(c, false, v || null); estado(); contar(); }
    function noCursor() { var s = window.getSelection(); if (!s.rangeCount) return null; var n = s.anchorNode; if (!n || !area.contains(n)) return null; return n.nodeType === 1 ? n : n.parentNode; }
    function blocoAtual() { var n = noCursor(); return n && n !== area ? n.closest(BLOCOS) : null; }
    function blocosDaSelecao() {
      var s = window.getSelection(); if (!s.rangeCount) return [];
      var r = s.getRangeAt(0), lista = [];
      area.querySelectorAll(BLOCOS).forEach(function (b) { if (r.intersectsNode(b) && !b.querySelector(BLOCOS)) lista.push(b); });
      if (!lista.length) { var b = blocoAtual(); if (b) lista.push(b); }
      return lista;
    }
    function alinhar(c) {
      restaurar();
      var bs = blocosDaSelecao();
      if (!bs.length) { document.execCommand('formatBlock', false, 'P'); bs = blocosDaSelecao(); }
      bs.forEach(function (b) { ALINHA.forEach(function (a) { b.classList.remove(a); }); if (c !== 'al-esq') b.classList.add(c); if (!b.getAttribute('class')) b.removeAttribute('class'); });
      estado();
    }
    function marcar() {
      restaurar();
      var s = window.getSelection(); if (!s.rangeCount || s.isCollapsed) return;
      var dentro = noCursor() && noCursor().closest('mark');
      if (dentro) { while (dentro.firstChild) dentro.parentNode.insertBefore(dentro.firstChild, dentro); dentro.remove(); return; }
      var r = s.getRangeAt(0), m = document.createElement('mark'); m.appendChild(r.extractContents()); r.insertNode(m);
      s.removeAllRanges(); var nr = document.createRange(); nr.selectNodeContents(m); s.addRange(nr);
    }
    function celula() { var n = noCursor(); return n ? n.closest('td,th') : null; }
    function tabela(acao) {
      var c = celula(); if (!c) return;
      var tr = c.parentNode, tab = c.closest('table'), i = Array.prototype.indexOf.call(tr.children, c);
      if (acao === 'lin+') { var nova = document.createElement('tr'); Array.prototype.forEach.call(tr.children, function () { var td = document.createElement('td'); td.innerHTML = '<br>'; nova.appendChild(td); });
        if (tr.parentNode.tagName === 'THEAD') { var tb = tab.querySelector('tbody') || tab.appendChild(document.createElement('tbody')); tb.insertBefore(nova, tb.firstChild); } else tr.after(nova); }
      if (acao === 'col+') tab.querySelectorAll('tr').forEach(function (l) { var ref = l.children[i], n = document.createElement(ref && ref.tagName === 'TH' ? 'th' : 'td'); if (n.tagName === 'TH') n.setAttribute('scope', 'col'); n.innerHTML = '<br>'; if (ref) ref.after(n); else l.appendChild(n); });
      if (acao === 'lin-') { if (tab.querySelectorAll('tr').length <= 1) tab.remove(); else tr.remove(); }
      if (acao === 'col-') { if (tr.children.length <= 1) tab.remove(); else tab.querySelectorAll('tr').forEach(function (l) { if (l.children[i]) l.children[i].remove(); }); }
      contar();
    }
    function estado() {
      ['bold', 'italic', 'underline', 'strikeThrough', 'superscript', 'subscript', 'insertUnorderedList', 'insertOrderedList'].forEach(function (c) {
        var b = barra.querySelector('[data-cmd="' + c + '"]'); var on = false; try { on = document.queryCommandState(c); } catch (e) {}
        b.setAttribute('aria-pressed', on ? 'true' : 'false');
      });
      var n = noCursor(), bl = blocoAtual(), topo = n ? n.closest('h2,h3,h4,blockquote,p') : null;
      sel.value = topo ? topo.tagName : 'P';
      var al = bl ? (ALINHA.filter(function (a) { return bl.classList.contains(a); })[0] || 'al-esq') : 'al-esq';
      ['al-esq', 'al-centro', 'al-dir', 'al-just'].forEach(function (a) { barra.querySelector('[data-cmd="' + a + '"]').setAttribute('aria-pressed', a === al ? 'true' : 'false'); });
      barra.querySelector('[data-cmd="marca"]').setAttribute('aria-pressed', n && n.closest('mark') ? 'true' : 'false');
      tabGrupo.hidden = !celula();
    }
    function contar() { var t = (area.innerText || '').trim(), n = t ? t.split(/\s+/).length : 0; conta.textContent = n + (n === 1 ? ' palavra' : ' palavras') + ' · ' + t.length + ' caracteres'; }
    function verCodigo(ligar) {
      if (ligar) { fonte.value = limpar(area.cloneNode(true)).innerHTML.replace(/(<\/(p|h2|h3|h4|li|tr|blockquote|figure|table|ul|ol)>)/g, '$1\n'); fonte.hidden = false; area.hidden = true; modo.textContent = 'Editando o código HTML'; fonte.focus(); }
      else { var d = new DOMParser().parseFromString(fonte.value, 'text/html'); area.innerHTML = limpar(d.body).innerHTML; fonte.hidden = true; area.hidden = false; modo.textContent = ''; area.focus(); contar(); }
      barra.querySelectorAll('button,select').forEach(function (b) { if (b.dataset.cmd !== 'codigo' && b.dataset.cmd !== 'cheio') b.disabled = ligar; });
      barra.querySelector('[data-cmd="codigo"]').setAttribute('aria-pressed', ligar ? 'true' : 'false');
    }
    function telaCheia(ligar) { ed.classList.toggle('ed-cheio', ligar); document.documentElement.classList.toggle('ed-cheio-aberto', ligar); barra.querySelector('[data-cmd="cheio"]').setAttribute('aria-pressed', ligar ? 'true' : 'false'); (fonte.hidden ? area : fonte).focus(); }
    barra.addEventListener('mousedown', function (e) { if (e.target.closest('button')) e.preventDefault(); });  // não perde a seleção
    sel.addEventListener('focus', guardar);
    sel.addEventListener('change', function () { cmd('formatBlock', sel.value); });
    barra.addEventListener('click', function (e) {
      var b = e.target.closest('button'); if (!b) return; var c = b.dataset.cmd;
      if (c === 'codigo') return verCodigo(fonte.hidden);
      if (c === 'cheio') return telaCheia(!ed.classList.contains('ed-cheio'));
      if (/^al-/.test(c)) return alinhar(c);
      if (c === 'marca') return marcar();
      if (/^(lin|col)[+-]$/.test(c)) return tabela(c);
      if (c === 'link') { guardar(); var a = noCursor() && noCursor().closest('a'); dlgL.querySelector('[data-link-url]').value = a ? a.getAttribute('href') : ''; dlgL.querySelector('[data-link-txt]').value = '';
        dlgL.querySelector('.ed-link-erro').hidden = true; dlgL.showModal(); return; }
      if (c === 'video') { guardar(); dlgV.querySelector('[data-video-url]').value = ''; dlgV.querySelector('[data-video-tit]').value = ''; dlgV.querySelector('.ed-video-erro').hidden = true; dlgV.showModal(); return; }
      if (c === 'tabela') return cmd('insertHTML', '<table><thead><tr><th scope="col">Coluna 1</th><th scope="col">Coluna 2</th><th scope="col">Coluna 3</th></tr></thead><tbody><tr><td><br></td><td><br></td><td><br></td></tr><tr><td><br></td><td><br></td><td><br></td></tr></tbody></table><p><br></p>');
      if (c === 'hr') return cmd('insertHTML', '<hr><p><br></p>');
      if (c === 'limpar') { cmd('removeFormat'); var m = noCursor() && noCursor().closest('mark'); if (m) marcar(); return; }
      if (c === 'preformatar') {
        if (!fonte.hidden) verCodigo(false);
        var msg = ed.querySelector('.ed-pref-msg'), antes = area.innerHTML, fd = new FormData();
        fd.append('csrf', form.querySelector('[name=csrf]').value); fd.append('html', limpar(area.cloneNode(true)).innerHTML);
        b.disabled = true;
        fetch(ed.dataset.preformatar, { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
          .then(function (r) { return r.json(); })
          .then(function (d) {
            if (!d.html) { msg.textContent = 'Nada para pré-formatar: escreva ou cole o texto do ato primeiro.'; msg.hidden = false; return; }
            area.innerHTML = d.html; estado(); contar();
            msg.innerHTML = 'Texto pré-formatado no padrão do Diário. Confira e ajuste o que precisar. <button type="button" class="btn sec pequeno">Voltar ao texto anterior</button>';
            msg.hidden = false;
            msg.querySelector('button').addEventListener('click', function () { area.innerHTML = antes; msg.hidden = true; estado(); contar(); area.focus(); });
          })
          .catch(function () { msg.textContent = 'Não foi possível pré-formatar agora (verifique a conexão).'; msg.hidden = false; })
          .then(function () { b.disabled = false; });
        return;
      }
      if (c === 'imagem') { guardar(); dlg.querySelector('.ed-img-erro').hidden = true; dlg.showModal(); return; }
      cmd(c);
    });
    area.addEventListener('keyup', function () { guardar(); estado(); });
    area.addEventListener('mouseup', function () { guardar(); estado(); });
    area.addEventListener('input', contar);
    area.addEventListener('blur', guardar);
    ed.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && ed.classList.contains('ed-cheio') && !ed.querySelector('dialog[open]')) { e.preventDefault(); telaCheia(false); }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' && e.target === area) { e.preventDefault(); barra.querySelector('[data-cmd="link"]').click(); }
    });
    area.addEventListener('paste', function (e) {
      var h = e.clipboardData && e.clipboardData.getData('text/html'); if (!h) return;
      e.preventDefault();
      var doc = new DOMParser().parseFromString(h, 'text/html');
      cmd('insertHTML', limpar(doc.body).innerHTML);
    });
    // link
    dlgL.querySelector('[data-link-ok]').addEventListener('click', function () {
      var u = dlgL.querySelector('[data-link-url]').value.trim(), t = dlgL.querySelector('[data-link-txt]').value.trim(), erro = dlgL.querySelector('.ed-link-erro');
      if (u && !/^(https:\/\/|mailto:|\/)/.test(u)) { if (/^www\./.test(u)) u = 'https://' + u; else { erro.textContent = 'Use um endereço que comece com https://, mailto: ou / (página do portal).'; erro.hidden = false; return; } }
      dlgL.close(); restaurar();
      var a = noCursor() && noCursor().closest('a');
      if (!u) { if (a) { var r = document.createRange(); r.selectNodeContents(a); var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); } document.execCommand('unlink'); return; }
      if (a) { a.setAttribute('href', u); if (t) a.textContent = t; return; }
      var s = window.getSelection();
      if (t || s.isCollapsed) { var n = document.createElement('a'); n.href = u; n.textContent = t || u; document.execCommand('insertHTML', false, n.outerHTML); }
      else document.execCommand('createLink', false, u);
      contar();
    });
    dlgL.querySelector('[data-link-cancelar]').addEventListener('click', function () { dlgL.close(); restaurar(); });
    // vídeo
    dlgV.querySelector('[data-video-ok]').addEventListener('click', function () {
      var u = dlgV.querySelector('[data-video-url]').value.trim(), t = dlgV.querySelector('[data-video-tit]').value.trim(), id = youtube(u), erro = dlgV.querySelector('.ed-video-erro');
      if (!id) { erro.textContent = 'Cole o endereço de um vídeo do YouTube (youtube.com/watch?v=… ou youtu.be/…).'; erro.hidden = false; return; }
      if (!t) { erro.textContent = 'Escreva o título do vídeo.'; erro.hidden = false; return; }
      dlgV.close(); var a = document.createElement('a'); a.className = 'video'; a.href = 'https://www.youtube.com/watch?v=' + id; a.textContent = 'Vídeo: ' + t;
      cmd('insertHTML', '<p>' + a.outerHTML + '</p><p><br></p>');
    });
    dlgV.querySelector('[data-video-cancelar]').addEventListener('click', function () { dlgV.close(); restaurar(); });
    // imagem
    dlg.querySelector('[data-img-ok]').addEventListener('click', function (e) {
      e.preventDefault();
      var arq = dlg.querySelector('[data-img-arq]').files[0], alt = dlg.querySelector('[data-img-alt]').value.trim(), erro = dlg.querySelector('.ed-img-erro');
      var pos = (dlg.querySelector('input[name="ed-img-pos"]:checked') || {}).value || '';
      if (!arq) { erro.textContent = 'Escolha o arquivo da imagem.'; erro.hidden = false; return; }
      var fd = new FormData(); fd.append('csrf', form.querySelector('[name=csrf]').value); fd.append('arquivo', arq); fd.append('alt', alt);
      fd.append('credito', dlg.querySelector('[data-img-cred]').value);
      fetch('/admin/editor/imagem', { method: 'POST', body: fd, credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (!d.url) { erro.textContent = d.erro || 'Não foi possível enviar.'; erro.hidden = false; return; }
          var leg = [dlg.querySelector('[data-img-leg]').value.trim(), dlg.querySelector('[data-img-cred]').value.trim()].filter(Boolean).join(' · ');
          var fig = document.createElement('figure'), img = document.createElement('img'); img.src = d.url; img.alt = alt; fig.appendChild(img); if (pos) fig.className = pos;
          if (leg) { var fc = document.createElement('figcaption'); fc.textContent = leg; fig.appendChild(fc); }
          dlg.close(); cmd('insertHTML', fig.outerHTML + '<p><br></p>');
        })
        .catch(function () { erro.textContent = 'Não foi possível enviar (verifique a conexão).'; erro.hidden = false; });
    });
    dlg.querySelector('[data-img-cancelar]').addEventListener('click', function () { dlg.close(); restaurar(); });
    form.addEventListener('submit', function () {
      if (!fonte.hidden) verCodigo(false);
      oculto.value = limpar(area.cloneNode(true)).innerHTML; simples.value = area.innerText;
    });
    contar(); estado();
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

// Ponto focal (14/11/2026): clique na imagem (ou setas do teclado) define foco_x/foco_y; as prévias do formulário acompanham.
(function () {
  document.querySelectorAll('[data-foco]').forEach(function (box) {
    var form = box.closest('form'), area = box.querySelector('.foco-img'), img = area.querySelector('img'), ponto = area.querySelector('.foco-ponto'),
        ix = box.querySelector('[name=foco_x]'), iy = box.querySelector('[name=foco_y]'), centro = box.querySelector('[data-foco-centro]'), sem = box.querySelector('.foco-sem');
    if (ix.disabled) return;
    function aplicar(x, y) {
      x = Math.max(0, Math.min(100, Math.round(x))); y = Math.max(0, Math.min(100, Math.round(y)));
      ix.value = x; iy.value = y; ponto.style.left = x + '%'; ponto.style.top = y + '%';
      form.querySelectorAll('[data-foco-previa]').forEach(function (p) { p.style.objectPosition = x + '% ' + y + '%'; });
    }
    area.addEventListener('click', function (e) { var r = img.getBoundingClientRect(); aplicar((e.clientX - r.left) / r.width * 100, (e.clientY - r.top) / r.height * 100); });
    area.addEventListener('keydown', function (e) {
      var d = { ArrowLeft: [-5, 0], ArrowRight: [5, 0], ArrowUp: [0, -5], ArrowDown: [0, 5] }[e.key];
      if (d) { e.preventDefault(); aplicar(+ix.value + d[0], +iy.value + d[1]); }
    });
    centro.addEventListener('click', function () { aplicar(50, 50); });
    var arq = form.querySelector('input[type=file]');
    if (arq) arq.addEventListener('change', function () {
      var f = arq.files[0]; if (!f || !/^image\//.test(f.type)) return;
      var url = URL.createObjectURL(f); img.src = url; area.hidden = false; centro.hidden = false; if (sem) sem.hidden = true;
      form.querySelectorAll('[data-foco-previa]').forEach(function (p) { p.src = url; });
      aplicar(50, 50);
    });
  });
})();

/* Identidade — seção Rodapé: prévia ao vivo (camada, mascote, celular) e contraste AA no pior trecho da imagem de fundo */
(function () {
  var form = document.getElementById('form-rodape'), pv = document.getElementById('rod-pv');
  if (!form || !pv) return;
  var $ = function (i) { return document.getElementById(i); };
  function lin(x) { x /= 255; return x <= 0.03928 ? x / 12.92 : Math.pow((x + 0.055) / 1.055, 2.4); }
  function lum(c) { return 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]); }
  function ct(a, b) { var x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
  function hex(h) { return [1, 3, 5].map(function (i) { return parseInt(h.substr(i, 2), 16); }); }
  var ROD = form.dataset.rgb.split(' ').map(Number), TIT = hex(form.dataset.titulo), TX = hex(form.dataset.texto),
      tem = !!form.dataset.fundo, g = 255 * (form.dataset.lum95 === '' ? 1 : parseFloat(form.dataset.lum95)), salvar = $('r-salvar');
  function fundo(a) { return ROD.map(function (v) { return Math.round(a * v + (1 - a) * g); }); }
  function pior(a) { var f = fundo(a); return [ct(f, TX), ct(f, TIT)]; }
  function minimo() { for (var a = 0; a <= 100; a += 5) { var p = pior(a / 100); if (Math.min(p[0], p[1]) >= 4.5) return a; } return 100; }
  function br(n) { return n.toFixed(1).replace('.', ','); }
  function at() {
    var cam = $('r-cam'), a = tem ? cam.value / 100 : 1;
    pv.style.setProperty('--a', a); $('o-cam').textContent = (tem ? cam.value : 100) + '%';
    pv.style.setProperty('--alt', $('r-alt').value + 'px'); $('o-alt').textContent = $('r-alt').value + ' px';
    pv.style.setProperty('--op', $('r-op').value / 100); $('o-op').textContent = $('r-op').value + '%';
    var lado = form.querySelector('[name=mascote_lado]:checked');
    pv.classList.toggle('dir', !!lado && lado.value === 'dir');
    if (!$('r-exib').disabled) pv.classList.toggle('sem-m', !$('r-exib').checked);
    pv.classList.toggle('m-cel', $('r-cel').checked);
    var aa = $('r-aa');
    if (!tem) { aa.innerHTML = ''; if (salvar) salvar.disabled = false; return; }
    var p = pior(a), ok = Math.min(p[0], p[1]) >= 4.5, m = minimo();
    aa.innerHTML = 'Contraste no trecho mais claro da imagem: textos ' + br(p[0]) + ':1 · títulos ' + br(p[1]) + ':1 <span class="chip ' + (ok ? 'ok">AA' : 'erro">abaixo de 4,5:1') + '</span>' +
      (ok ? '' : '<br><span class="chip erro">Mínimo seguro: ' + m + '%</span> <button type="button" class="btn sec pequeno" id="r-min">Usar o mínimo seguro</button>');
    if (salvar) salvar.disabled = !ok;
    var b = $('r-min'); if (b) b.onclick = function () { cam.value = m; at(); cam.focus(); };
  }
  form.addEventListener('input', at); form.addEventListener('change', at);
  document.querySelectorAll('[data-pv]').forEach(function (b) {
    b.addEventListener('click', function () {
      document.querySelectorAll('[data-pv]').forEach(function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      pv.classList.toggle('cel', b.dataset.pv === 'c');
    });
  });
  at();
})();

/* Identidade — imagens (16/11/2026): prévia local do arquivo escolhido no quadro (antes de salvar) e "decorativa" desativa o texto alternativo */
(function () {
  document.querySelectorAll('input[type=file][data-previa-local]').forEach(function (arq) {
    var quadro = arq.form && arq.form.querySelector('[data-previa-quadro]');
    if (!quadro) return;
    arq.addEventListener('change', function () {
      var f = arq.files && arq.files[0];
      if (!f || !/^image\/(png|jpeg|webp)$/.test(f.type)) return;
      var img = document.createElement('img'); img.src = URL.createObjectURL(f); img.alt = 'Prévia da imagem escolhida (ainda não salva)';
      quadro.textContent = ''; quadro.appendChild(img);
      var nota = document.createElement('span'); nota.className = 'prev-nota'; nota.textContent = 'Prévia (não salva)'; quadro.appendChild(nota);
    });
  });
  document.querySelectorAll('input[type=checkbox][data-decorativa]').forEach(function (cx) {
    var alt = document.getElementById(cx.dataset.decorativa), nota = document.getElementById('nota-' + cx.dataset.decorativa);
    if (!alt) return;
    function at() { alt.disabled = cx.checked || cx.disabled; if (nota) nota.hidden = !cx.checked; }
    cx.addEventListener('change', at); at();
  });
})();
