// Portal: menu do celular (foco preso, Esc fecha), balões ⓘ dos indicadores e botão de Libras. Sem JavaScript, tudo continua acessível por links.
(function () {
  var foco = 'a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])';
  // ---- menu do celular ----
  var btn = document.querySelector('.btn-menu'), painel = document.getElementById('menu-cel');
  if (btn && painel) {
    btn.hidden = false;
    var abrir = function () { painel.hidden = false; btn.setAttribute('aria-expanded', 'true'); document.body.classList.add('menu-aberto'); painel.querySelector(foco).focus(); };
    var fechar = function () { painel.hidden = true; btn.setAttribute('aria-expanded', 'false'); document.body.classList.remove('menu-aberto'); btn.focus(); };
    btn.addEventListener('click', abrir);
    painel.querySelector('[data-fechar-menu]').addEventListener('click', fechar);
    painel.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { e.preventDefault(); fechar(); return; }
      if (e.key !== 'Tab') return;
      var f = [].slice.call(painel.querySelectorAll(foco)).filter(function (x) { return x.offsetParent !== null; });
      if (!f.length) return;
      if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
      else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
    });
  }
  // ---- balões ⓘ (toggletip): botão real; sem JS, o link leva à página do indicador ----
  var aberto = null;
  function fecharBalao(volta) { if (!aberto) return; var b = aberto; aberto = null; b.setAttribute('aria-expanded', 'false'); document.getElementById(b.getAttribute('aria-controls')).hidden = true; if (volta) b.focus(); }
  document.querySelectorAll('[data-info]').forEach(function (a) {
    var b = document.createElement('button');
    b.type = 'button'; b.className = 'ic-info'; b.textContent = 'i';
    b.setAttribute('aria-label', a.getAttribute('aria-label')); b.setAttribute('aria-expanded', 'false'); b.setAttribute('aria-controls', a.getAttribute('data-info'));
    a.replaceWith(b);
    b.addEventListener('click', function (e) {
      e.stopPropagation();
      var era = aberto === b; fecharBalao(false);
      if (era) return;
      var bal = document.getElementById(b.getAttribute('aria-controls')); bal.hidden = false; b.setAttribute('aria-expanded', 'true'); aberto = b;
      // dentro de uma fileira (trilho rolável) o balão seria cortado: fica fixo, logo abaixo do botão
      if (bal.closest('.fil-trilho') && window.innerWidth > 760) {
        var r = b.getBoundingClientRect();
        bal.style.position = 'fixed'; bal.style.right = 'auto'; bal.style.width = '320px';
        bal.style.top = Math.round(r.bottom + 8) + 'px';
        bal.style.left = Math.round(Math.max(8, Math.min(r.right - 320, window.innerWidth - 328))) + 'px';
      }
    });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && aberto) fecharBalao(true); });
  document.addEventListener('click', function (e) { if (aberto && !e.target.closest('.balao')) fecharBalao(false); });
  window.addEventListener('scroll', function () { if (aberto && document.getElementById(aberto.getAttribute('aria-controls')).style.position === 'fixed') fecharBalao(false); }, { passive: true, capture: true });
  // ---- Libras: abre/fecha o avatar do VLibras pelo botão da barra ----
  var lb = document.querySelector('[data-libras]');
  if (lb) lb.addEventListener('click', function () {
    var acesso = document.querySelector('[vw-access-button]'), fechar = document.querySelector('.vpw-settings-btn-close, [vp-close]');
    var on = lb.getAttribute('aria-pressed') === 'true';
    if (!on && acesso) acesso.click(); else if (on && fechar) fechar.click();
    lb.setAttribute('aria-pressed', on ? 'false' : 'true');
  });
})();

/* Galeria do "Conheça": ampliação acessível em <dialog> (Esc fecha, setas navegam, foco volta à miniatura). Sem JS, o link abre a imagem. */
(function () {
  var dlg = document.querySelector('dialog.ampliada');
  var dadosEl = document.getElementById('fotos-dados'), legEl = document.getElementById('fotos-leg');
  if (!dlg || !dadosEl || typeof dlg.showModal !== 'function') return;
  var urls = JSON.parse(dadosEl.textContent || '[]'), legs = JSON.parse((legEl && legEl.textContent) || '[]');
  var img = dlg.querySelector('img'), cap = dlg.querySelector('figcaption'), pos = dlg.querySelector('[data-amp-pos]');
  var atual = 0, origem = null;
  function mostrar(i) {
    atual = (i + urls.length) % urls.length;
    img.src = urls[atual]; img.alt = legs[atual] || '';
    cap.textContent = legs[atual] || '';
    pos.textContent = 'Foto ' + (atual + 1) + ' de ' + urls.length;
  }
  document.querySelectorAll('a[data-galeria]').forEach(function (a) {
    a.addEventListener('click', function (e) {
      e.preventDefault(); origem = a;
      mostrar(parseInt(a.getAttribute('data-galeria'), 10) || 0);
      dlg.showModal();
      dlg.querySelector('[data-amp-fechar]').focus();
    });
  });
  dlg.querySelectorAll('[data-amp]').forEach(function (b) {
    b.addEventListener('click', function () { mostrar(atual + parseInt(b.getAttribute('data-amp'), 10)); });
  });
  dlg.querySelector('[data-amp-fechar]').addEventListener('click', function () { dlg.close(); });
  dlg.addEventListener('keydown', function (e) {
    if (e.key === 'ArrowRight') { mostrar(atual + 1); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { mostrar(atual - 1); e.preventDefault(); }
  });
  dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
  dlg.addEventListener('close', function () { if (origem) origem.focus(); });
  if (urls.length < 2) dlg.querySelectorAll('[data-amp]').forEach(function (b) { b.hidden = true; });
})();

/* Busca compacta (cabeçalho cheio): botão "Buscar" com o campo vazio só abre o campo */
(function () {
  var f = document.getElementById('form-busca');
  if (!f) return;
  f.addEventListener('submit', function (e) {
    var i = f.querySelector('input[name=q]');
    if (i && !i.value.trim() && f.closest('.topo.cheio')) { e.preventDefault(); i.focus(); }
  });
})();

/* Avaliação: envia sem recarregar e mostra a resposta no lugar do formulário (sem JS, volta à página com a mensagem no mesmo lugar) */
(function () {
  var f = document.querySelector('form.aval-form'), msg = document.querySelector('.aval-msg');
  if (!f || !msg || !window.fetch) return;
  f.addEventListener('submit', function (e) {
    var bt = e.submitter; if (!bt || !bt.value) return;
    e.preventDefault();
    var dados = new FormData(f); dados.set('util', bt.value);
    f.querySelectorAll('button').forEach(function (b) { b.disabled = true; });
    fetch(f.action, { method: 'POST', body: dados, headers: { 'Accept': 'application/json' }, credentials: 'same-origin' })
      .then(function (r) { return r.json(); })
      .then(function (d) { msg.textContent = d.msg; msg.hidden = false; f.remove(); })
      .catch(function () { msg.textContent = 'Não foi possível enviar agora. Tente de novo.'; msg.hidden = false; f.querySelectorAll('button').forEach(function (b) { b.disabled = false; }); });
  });
})();

/* Fileira de cartões: setas e "1–5 de 8" só quando o trilho transborda; setas do teclado só com o foco dentro do trilho.
   Sem rolagem automática; com "reduzir movimento", sem animação. Sem JS, o trilho continua rolável (setas ficam ocultas). */
(function () {
  var reduz = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  document.querySelectorAll('[data-fileira]').forEach(function (f) {
    var t = f.querySelector('.fil-trilho'), nav = f.querySelector('[data-fil-nav]');
    if (!t || !nav) return;
    var cards = [].slice.call(t.children), n = cards.length, cont = nav.querySelector('.fil-cont');
    var bts = nav.querySelectorAll('[data-fil]');
    function passo() { var g = parseFloat(getComputedStyle(t).columnGap) || 0; return cards[0].getBoundingClientRect().width + g; }
    function porVez() { var p = passo(), pl = parseFloat(getComputedStyle(t).paddingLeft) || 0; return Math.max(1, Math.floor((t.clientWidth - 2 * pl + (parseFloat(getComputedStyle(t).columnGap) || 0)) / p + 0.02)); }
    function atualiza() {
      var rola = t.scrollWidth > t.clientWidth + 2;
      nav.hidden = !rola;
      if (!rola) return;
      var i = Math.round(t.scrollLeft / passo()), v = porVez();
      var ate = Math.min(n, i + v); cont.textContent = (ate > i + 1 ? (i + 1) + '–' + ate : (i + 1)) + ' de ' + n;
      bts[0].disabled = t.scrollLeft <= 2;
      bts[1].disabled = t.scrollLeft >= t.scrollWidth - t.clientWidth - 2;
    }
    bts.forEach(function (b) {
      b.addEventListener('click', function () {
        t.scrollBy({ left: parseInt(b.getAttribute('data-fil'), 10) * porVez() * passo(), behavior: reduz ? 'auto' : 'smooth' });
      });
    });
    var pend = null;
    t.addEventListener('scroll', function () { if (pend) return; pend = requestAnimationFrame(function () { pend = null; atualiza(); }); }, { passive: true });
    if (window.ResizeObserver) new ResizeObserver(atualiza).observe(t); else window.addEventListener('resize', atualiza);
    t.addEventListener('keydown', function (e) {
      if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
      if (/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName)) return;
      var atual = cards.findIndex(function (c) { return c.contains(e.target); });
      if (atual < 0) return;
      var alvo = cards[atual + (e.key === 'ArrowRight' ? 1 : -1)];
      var foco = alvo && alvo.querySelector('a[href],button:not([disabled]),select,input');
      if (!foco && alvo && alvo.matches('a[href]')) foco = alvo;
      if (!foco) return;
      e.preventDefault();
      foco.focus({ preventScroll: true });
      alvo.scrollIntoView({ block: 'nearest', inline: 'nearest', behavior: reduz ? 'auto' : 'smooth' });
    });
    atualiza();
  });
})();

/* Rodapé (16/11/2026): o mascote nunca cobre texto — reduz a altura até caber na área livre abaixo da coluna do lado escolhido */
(function () {
  var fx = document.querySelector('.f2-faixa'), m = fx && fx.querySelector('.f2-masc img');
  if (!m) return;
  var dir = fx.querySelector('.f2-masc').classList.contains('dir');
  function ajustar() {
    m.style.height = '';
    if (window.innerWidth < 768) return;  // no celular a faixa reserva espaço para o mascote (CSS)
    var cols = fx.querySelectorAll('.f2 .fcol'); if (!cols.length) return;
    var c = dir ? cols[cols.length - 1] : cols[0], fim = c.lastElementChild || c;
    var livre = fx.getBoundingClientRect().bottom - fim.getBoundingClientRect().bottom - 24;
    var alvo = parseFloat(getComputedStyle(m).height);
    if (livre < alvo) m.style.height = Math.max(0, Math.floor(livre)) + 'px';
    m.hidden = livre < 48;  // sem espaço útil: não mostra
  }
  if (m.complete) ajustar(); else m.addEventListener('load', ajustar);
  window.addEventListener('resize', ajustar);
})();

/* Galeria de vídeos e câmeras ao vivo (26/11/2026): o player do YouTube (youtube-nocookie) e o vídeo da câmera só carregam no clique */
(function(){
  function el(tag, attrs, txt){var e=document.createElement(tag);for(var k in attrs){e.setAttribute(k, attrs[k])}if(txt){e.textContent=txt}return e}
  document.querySelectorAll('[data-galeria]').forEach(function(g){
    var palco=g.querySelector('.vg-palco');
    g.addEventListener('click', function(ev){
      var b=ev.target.closest('.vg-capa'); if(!b||!g.contains(b)) return;
      var id=b.getAttribute('data-yt')||'', tit=b.getAttribute('data-titulo')||'';
      var moldura=el('div', {'class':'vg-frame'});
      if(/^[A-Za-z0-9_-]{11}$/.test(id)){
        moldura.appendChild(el('iframe', {src:'https://www.youtube-nocookie.com/embed/'+id+'?rel=0&autoplay=1', title:'Vídeo: '+tit, allow:'autoplay; encrypted-media; picture-in-picture; fullscreen', allowfullscreen:'', referrerpolicy:'strict-origin-when-cross-origin'}));
      } else {
        moldura.classList.add('vg-ex'); moldura.appendChild(el('span', {}, 'Vídeo de exemplo: quando os vídeos do canal oficial forem cadastrados no painel, eles tocam aqui.'));
      }
      palco.innerHTML=''; palco.appendChild(moldura); palco.appendChild(el('p', {'class':'vg-agora'}, tit));
      g.querySelectorAll('.vg-lista .vg-capa').forEach(function(x){x.removeAttribute('aria-current')});
      if(b.closest('.vg-lista')){b.setAttribute('aria-current','true')}
      var r=palco.getBoundingClientRect(); if(r.top<0||r.top>window.innerHeight*0.6){palco.scrollIntoView({behavior:'smooth', block:'start'})}
      var f=palco.querySelector('iframe'); if(f){f.focus()}
    });
  });
  document.addEventListener('click', function(ev){
    var b=ev.target.closest('.cam-play'); if(!b) return;
    var c=b.closest('.cam'), u=c&&c.getAttribute('data-cam'); if(!u||!/^\/cameras\/\d+\/$/.test(u)) return;
    c.innerHTML=''; c.classList.add('tocando');
    var f=el('iframe', {src:u, title:c.getAttribute('data-titulo')||'Câmera ao vivo', allow:'autoplay; fullscreen', allowfullscreen:''}); c.appendChild(f); f.focus();
  });
  /* Aviso de cookies e privacidade (LGPD): só cookies necessários; a resposta fica no próprio navegador */
  var a=document.getElementById('aviso-cookies');
  if(a){var visto=false;try{visto=localStorage.getItem('aviso_cookies')==='1'}catch(e){}
    if(!visto){a.hidden=false}
    var ok=a.querySelector('[data-ok]'); if(ok){ok.addEventListener('click', function(){try{localStorage.setItem('aviso_cookies','1')}catch(e){}a.hidden=true})}}
})();
