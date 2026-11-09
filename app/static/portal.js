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
    });
  });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && aberto) fecharBalao(true); });
  document.addEventListener('click', function (e) { if (aberto && !e.target.closest('.balao')) fecharBalao(false); });
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
