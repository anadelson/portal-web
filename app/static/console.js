/* Console — cadastro de órgão: busca o município no IBGE pelo código, sugere nome, identificador e município no TCESP,
   e mostra só os campos que valem para o tipo de órgão e o sistema escolhido. Sem JS, o servidor faz tudo ao cadastrar. */
(function () {
  var f = document.getElementById('form-cadastro'); if (!f) return;
  var tipo = document.getElementById('c-tipo'), ibge = document.getElementById('c-ibge'), bt = document.getElementById('c-buscar'), msg = document.getElementById('c-ibge-msg');
  var mun = document.getElementById('c-municipio'), uf = document.getElementById('c-uf'), nome = document.getElementById('c-nome'), slug = document.getElementById('c-slug');
  var tce = document.getElementById('c-tcesp'), sis = document.getElementById('c-sistema'), cor = document.getElementById('c-cor');
  var ultimo = null;
  bt.hidden = false;
  function sugestoes() {
    var ex = tipo.value === 'executivo';
    if (ultimo) { nome.placeholder = ex ? ultimo.nome_pm : ultimo.nome_cm; slug.placeholder = ex ? ultimo.slug_pm : ultimo.slug_cm; tce.placeholder = ultimo.tcesp; }
    cor.placeholder = ex ? '#1D4E89' : '#2F5233';
    tce.closest('label').hidden = !(ex && uf.value === 'SP');
    // um bloco por sistema da transparência (data-sistema): só o do sistema escolhido aparece; campos só de Câmara (data-so-tipo)
    f.querySelectorAll('[data-sistema]').forEach(function (b) { b.hidden = b.dataset.sistema !== sis.value; });
    f.querySelectorAll('[data-so-tipo]').forEach(function (l) { l.hidden = l.dataset.soTipo !== tipo.value; });
    f.querySelectorAll('[data-serve]').forEach(function (l) { var s = l.dataset.serve; l.hidden = !(s === 'ambos' || s === tipo.value); if (l.hidden) l.querySelector('input').checked = false; });
  }
  function buscar() {
    var c = ibge.value.replace(/\D/g, '');
    if (c.length !== 7) { msg.textContent = 'O código IBGE tem 7 dígitos.'; ibge.focus(); return; }
    msg.textContent = 'Consultando o IBGE…'; bt.disabled = true;
    fetch('/orgaos/ibge/' + c, { credentials: 'same-origin', headers: { 'Accept': 'application/json' } })
      .then(function (r) { return r.json().then(function (d) { return { ok: r.ok, d: d }; }); })
      .then(function (x) {
        bt.disabled = false;
        if (!x.ok) { msg.textContent = x.d.erro; ultimo = null; sugestoes(); return; }
        ultimo = x.d; mun.value = x.d.municipio; uf.value = x.d.uf;
        msg.textContent = 'IBGE: ' + x.d.municipio + ' (' + x.d.uf + ' — ' + x.d.uf_nome + '). Nome e identificador sugeridos abaixo; deixe vazio para usar a sugestão.';
        sugestoes();
      })
      .catch(function () { bt.disabled = false; msg.textContent = 'O IBGE não respondeu agora. Preencha o município e a UF; o cadastro confere de novo ao salvar.'; });
  }
  bt.addEventListener('click', buscar);
  ibge.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); buscar(); } });
  [tipo, uf, sis].forEach(function (el) { el.addEventListener('change', sugestoes); });
  sugestoes();
})();
