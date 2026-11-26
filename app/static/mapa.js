/* Mapas das câmeras ao vivo (26/11/2026), com Leaflet 1.9.4 (/static/vendor) e mapa do OpenStreetMap.
   - [data-mapa-cameras]: página /cameras-ao-vivo; pontos vêm do <script type="application/json" id="dados-mapa">
     (só nome, local e posição; nunca endereço da câmera). Clicar no marcador leva ao cartão da câmera na lista.
   - [data-mapa-escolher="id-do-campo"]: painel; clicar no mapa preenche o campo "latitude, longitude".
   Sem JavaScript ou sem o mapa carregar, a lista de câmeras e o campo de texto continuam funcionando. */
(function(){
  if(!window.L) return;
  var OSM='https://tile.openstreetmap.org/{z}/{x}/{y}.png';
  var ATRIB='&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>';
  function base(el, lat, lon, zoom, travar){
    var op={scrollWheelZoom:false};
    if(travar){op={minZoom:zoom, maxZoom:zoom, zoomControl:false, scrollWheelZoom:false, doubleClickZoom:false, touchZoom:false, boxZoom:false, keyboardZoomOffset:0}}
    var m=L.map(el, op).setView([lat, lon], zoom);
    if(travar){L.tileLayer(OSM, {maxZoom:19, attribution:ATRIB}).addTo(m); return m}
    L.tileLayer(OSM, {maxZoom:19, attribution:ATRIB}).addTo(m);
    m.on('focus', function(){m.scrollWheelZoom.enable()}); m.on('blur', function(){m.scrollWheelZoom.disable()});
    return m;
  }
  function txt(s){var d=document.createElement('div'); d.textContent=s==null?'':String(s); return d.innerHTML}

  var el=document.querySelector('[data-mapa-cameras]'), dados=document.getElementById('dados-mapa');
  if(el && dados){
    var d; try{d=JSON.parse(dados.textContent)}catch(e){d=null}
    if(d && d.centro){
      var v=d.visao, m=v?base(el, v.lat, v.lon, v.zoom, v.travar):base(el, d.centro.lat, d.centro.lon, 15), limites=[];
      (d.pontos||[]).forEach(function(p){
        if(typeof p.lat!=='number'||typeof p.lon!=='number') return;
        var mk=L.marker([p.lat, p.lon], {title:p.nome, alt:'Câmera: '+p.nome, keyboard:true}).addTo(m);
        var h='<strong>'+txt(p.nome)+'</strong>'+(p.local?'<br>'+txt(p.local):'')+
              (p.exemplo?'<br><em>exemplo'+(p.ilustrativa?' (posição ilustrativa)':'')+'</em>':'')+
              '<br><a href="#cam-'+(+p.id)+'" data-ir-cam="'+(+p.id)+'">'+(p.exemplo?'Ver na lista':'Assistir ao vivo')+'</a>';
        mk.bindPopup(h); limites.push([p.lat, p.lon]);
      });
      // visão fixa do painel: abre sempre nela; sem ela, enquadra as câmeras
      if(!v){if(limites.length>1){m.fitBounds(limites, {padding:[40,40], maxZoom:17})}
      else if(limites.length===1){m.setView(limites[0], 16)}}
      el.addEventListener('click', function(ev){
        var a=ev.target.closest('[data-ir-cam]'); if(!a) return;
        ev.preventDefault();
        var li=document.getElementById('cam-'+a.getAttribute('data-ir-cam')); if(!li) return;
        li.scrollIntoView({behavior:'smooth', block:'center'});
        var b=li.querySelector('.cam-play'); (b||li).focus({preventScroll:true});
        li.classList.add('destacada'); setTimeout(function(){li.classList.remove('destacada')}, 2200);
      });
    }
  }

  // painel: escolher a visão inicial do mapa das câmeras (centro + zoom vão para os campos ocultos)
  var vbox=document.querySelector('[data-mapa-visao]');
  if(vbox){
    var vc=(vbox.getAttribute('data-centro')||'').split(','), vz=+vbox.getAttribute('data-zoom')||15;
    if(vc.length===2&&isFinite(+vc[0])&&isFinite(+vc[1])){
      var vm=base(vbox, +vc[0], +vc[1], vz);
      var fl=document.getElementById('visao-lat'), fo=document.getElementById('visao-lon'), fz=document.getElementById('visao-zoom'), ft=document.getElementById('visao-zoom-txt');
      vm.on('moveend zoomend', function(){var c=vm.getCenter(); fl.value=c.lat.toFixed(6); fo.value=c.lng.toFixed(6); fz.value=vm.getZoom(); if(ft){ft.textContent=vm.getZoom()}});
    }else{vbox.hidden=true}
  }

  document.querySelectorAll('[data-mapa-escolher]').forEach(function(box){
    var campo=document.getElementById(box.getAttribute('data-mapa-escolher')); if(!campo) return;
    var c=(box.getAttribute('data-centro')||'').split(','), atual=(campo.value||'').split(/[,;\s]+/).filter(Boolean);
    var tem=atual.length===2&&!isNaN(+atual[0])&&!isNaN(+atual[1]);
    var lat=tem?+atual[0]:+c[0], lon=tem?+atual[1]:+c[1];
    if(isNaN(lat)||isNaN(lon)||!isFinite(lat)||!isFinite(lon)){box.hidden=true; return}
    var iniciado=false, m, mk;
    function iniciar(){
      if(iniciado) return; iniciado=true;
      m=base(box, lat, lon, tem?17:15);
      if(tem){mk=L.marker([lat, lon]).addTo(m)}
      m.on('click', function(ev){
        var la=ev.latlng.lat.toFixed(6), lo=ev.latlng.lng.toFixed(6);
        campo.value=la+', '+lo;
        if(mk){mk.setLatLng(ev.latlng)}else{mk=L.marker(ev.latlng).addTo(m)}
      });
    }
    // dentro de <details> fechado o mapa não tem tamanho: só monta quando abrir
    var det=box.closest('details');
    if(det && !det.open){det.addEventListener('toggle', function(){if(det.open){iniciar(); m.invalidateSize()}})}
    else{iniciar()}
  });
})();
