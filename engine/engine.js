/* ===== DECK ENGINE JS — shared by every deck; edit here, then `deck refresh <deck>`. =====
   Keys: → / space next build or slide · ← back · F fullscreen · H counter · Home / End.
   Hash: #N opens slide N fully built · #N,start opens it unbuilt · ,bare hides the counter.
   Per-slide transition: <section class="slide" data-trans="dip">; deck default on <body data-trans>.
   Transitions: fade (default) · cut · dip (through the background) · slide · push · zoom · rise. */
(function(){
  var LOGO='__LOGO__';
  var stage=document.getElementById('stage');
  var slides=[].slice.call(stage.querySelectorAll('section.slide'));
  var i=0,busy=false;
  var body=document.body;

  /* stable ids so notes survive re-ordering */
  slides.forEach(function(s,n){ if(!s.dataset.id) s.dataset.id='s'+(n+1); });

  /* chrome: the ribbon (always) and the logo (body.show-logo) live inside every slide,
     so each slide's own colours apply to them and print/PDF gets them for free */
  slides.forEach(function(s){
    var r=document.createElement('div');r.className='ribbon';r.innerHTML='<i></i><i></i><i></i><i></i><i></i>';s.appendChild(r);
    var l=document.createElement('div');l.className='deck-logo';l.innerHTML='<img alt="Trilegal" src="'+LOGO+'">';s.appendChild(l);
  });

  var hud=document.createElement('div');hud.id='hud';document.body.appendChild(hud);
  function setHud(){hud.textContent=(i+1)+' / '+slides.length;}
  var hudT;function pokeHud(){body.classList.add('hud-on');clearTimeout(hudT);hudT=setTimeout(function(){body.classList.remove('hud-on');},1800);}
  addEventListener('mousemove',pokeHud);

  function fit(){var s=Math.min(innerWidth/1280,innerHeight/720);stage.style.transform='translate(-50%,-50%) scale('+s+')';}
  /* headless and embedded viewports can report 0×0 at first — refit whenever the viewport changes */
  addEventListener('resize',fit);addEventListener('load',fit);fit();
  if(window.ResizeObserver)new ResizeObserver(fit).observe(document.documentElement);

  function frags(s){return [].slice.call(s.querySelectorAll('.frag'));}
  function shown(s){return frags(s).filter(function(f){return f.classList.contains('shown');}).length;}
  function setFrags(s,k){frags(s).forEach(function(f,n){f.classList.toggle('shown',n<k);});}

  function transOf(s){return s.dataset.trans||body.dataset.trans||'fade';}
  function transition(o,n,dir){
    if(o===n)return;
    var t=transOf(n),D=t==='cut'?0:(t==='dip'?900:560),E='cubic-bezier(.4,0,.2,1)',g=dir>=0?1:-1;
    [o,n].forEach(function(el){el.getAnimations().forEach(function(a){a.cancel();});});
    n.classList.add('active');
    var ok=[{opacity:1},{opacity:0}],ik=[{opacity:0},{opacity:1}],io={};
    if(t==='slide'){ok=[{transform:'translateX(0)'},{transform:'translateX('+(-g*100)+'%)'}];ik=[{transform:'translateX('+(g*100)+'%)'},{transform:'none'}];}
    else if(t==='push'){ok=[{transform:'translateY(0)'},{transform:'translateY('+(-g*100)+'%)'}];ik=[{transform:'translateY('+(g*100)+'%)'},{transform:'none'}];}
    else if(t==='rise'){ok=[{opacity:1},{opacity:0,transform:'translateY('+(-g*40)+'px)'}];ik=[{opacity:0,transform:'translateY('+(g*40)+'px)'},{opacity:1,transform:'none'}];}
    else if(t==='zoom'){ok=[{opacity:1},{opacity:0,transform:'scale(1.06)'}];ik=[{opacity:0,transform:'scale(.95)'},{opacity:1,transform:'none'}];}
    else if(t==='dip'){ok=[{opacity:1},{opacity:0,offset:.45},{opacity:0}];ik=[{opacity:0},{opacity:0,offset:.55},{opacity:1}];}
    else if(t==='cut'){ok=[{opacity:0},{opacity:0}];ik=[{opacity:1},{opacity:1}];}
    if(D===0){o.classList.remove('active');return;}
    busy=true;
    var ao=o.animate(ok,{duration:D,easing:E,fill:'forwards'});
    ao.onfinish=function(){o.classList.remove('active');ao.cancel();};
    var ai=n.animate(ik,{duration:D,easing:E,fill:'forwards'});
    ai.onfinish=function(){ai.cancel();busy=false;};
  }
  function goTo(n,dir,full){
    n=Math.max(0,Math.min(slides.length-1,n));if(n===i&&slides[i].classList.contains('active'))return;
    var o=slides[i],s=slides[n];i=n;setFrags(s,full?frags(s).length:0);transition(o,s,dir);after(s);
  }
  function after(s){setHud();initChart(s);maybeQR(s);tell();}
  function next(){if(busy)return;var s=slides[i],k=shown(s);if(k<frags(s).length){frags(s)[k].classList.add('shown');tell();return;}if(i<slides.length-1)goTo(i+1,1,false);}
  function prev(){if(busy)return;var f=frags(slides[i]);for(var k=f.length-1;k>=0;k--){if(f[k].classList.contains('shown')){f[k].classList.remove('shown');tell();return;}}if(i>0)goTo(i-1,-1,true);}

  addEventListener('keydown',function(e){
    if(e.target&&e.target.isContentEditable)return;
    if(e.key==='ArrowRight'||e.key===' '||e.key==='PageDown'){e.preventDefault();next();}
    else if(e.key==='ArrowLeft'||e.key==='PageUp'){e.preventDefault();prev();}
    else if(e.key==='f'||e.key==='F'){document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen();}
    else if(e.key==='h'||e.key==='H'){pokeHud();}
    else if(e.key==='Home'){goTo(0,-1,false);}else if(e.key==='End'){goTo(slides.length-1,1,true);}
  });
  var tx=0,ty=0,lastTouch=0;
  stage.addEventListener('click',function(e){if(body.classList.contains('bare')||(e.target&&e.target.isContentEditable))return;if(Date.now()-lastTouch<600)return;(e.clientX<innerWidth/3)?prev():next();});
  addEventListener('touchstart',function(e){var t=e.changedTouches[0];tx=t.clientX;ty=t.clientY;},{passive:true});
  addEventListener('touchend',function(e){lastTouch=Date.now();var t=e.changedTouches[0],dx=t.clientX-tx,dy=t.clientY-ty;
    if(Math.abs(dx)>40&&Math.abs(dx)>Math.abs(dy)*1.4){dx<0?next():prev();}else if(Math.abs(dx)<10&&Math.abs(dy)<10){(t.clientX<innerWidth/3)?prev():next();}},{passive:true});

  /* screen stays awake while presenting fullscreen */
  var wl=null;document.addEventListener('fullscreenchange',function(){
    try{if(document.fullscreenElement&&'wakeLock' in navigator){navigator.wakeLock.request('screen').then(function(s){wl=s;}).catch(function(){});}else if(wl){wl.release();wl=null;}}catch(x){}});

  /* charts: a canvas[data-chart] plus a JSON script.chartcfg holding the Chart.js config.
     colour tokens: "$accent" "$ink" "$muted" "$grid" "$r1".."$r5" */
  function cssv(n){return getComputedStyle(body).getPropertyValue(n).trim();}
  function load(src,cb){var s=document.createElement('script');s.src=src;s.onload=cb;document.head.appendChild(s);}
  function initChart(s){
    var cv=s.querySelector('canvas[data-chart]');if(!cv||cv._done)return;
    if(typeof Chart==='undefined'){load('https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js',function(){initChart(s);});return;}
    var c=s.querySelector('script.chartcfg');if(!c)return;var txt=c.textContent;
    var m={'$accent':'--accent','$ink':'--fg','$muted':'--muted','$grid':'--hairline','$r1':'--r1','$r2':'--r2','$r3':'--r3','$r4':'--r4','$r5':'--r5'};
    for(var k in m)txt=txt.split('"'+k+'"').join(JSON.stringify(cssv(m[k])));
    Chart.defaults.font.family=cssv('--body')||'sans-serif';Chart.defaults.font.size=22;Chart.defaults.color=cssv('--muted');
    cv._done=true;new Chart(cv,JSON.parse(txt));
  }
  /* closing QR: <div id="qr" data-url="https://rahulmatthan.com"></div> */
  function maybeQR(s){
    var el=s.querySelector('#qr');if(!el||el._done)return;
    if(typeof QRCode==='undefined'){load('https://cdn.jsdelivr.net/npm/qrcodejs@1.0.0/qrcode.min.js',function(){maybeQR(s);});return;}
    el._done=true;new QRCode(el,{text:el.dataset.url||'https://rahulmatthan.com',width:180,height:180,colorDark:'#000',colorLight:'#fff'});
  }

  /* Deck Studio talks to the deck through postMessage */
  function tell(){try{if(parent!==window)parent.postMessage({deck:'at',i:i,id:slides[i].dataset.id,frag:shown(slides[i]),frags:frags(slides[i]).length,n:slides.length},'*');}catch(x){}}
  addEventListener('message',function(e){var d=e.data||{};
    if(d.deck==='goto'){var n=typeof d.id==='string'?slides.findIndex(function(s){return s.dataset.id===d.id;}):d.i;
      if(n<0)return;slides.forEach(function(s){s.getAnimations().forEach(function(a){a.cancel();});s.classList.remove('active');});
      i=n;slides[i].classList.add('active');setFrags(slides[i],d.start?0:frags(slides[i]).length);after(slides[i]);}
    else if(d.deck==='next')next();else if(d.deck==='prev')prev();
  });

  function applyHash(){
    var p=location.hash.replace('#','').split(',');
    if(p.indexOf('bare')>=0)body.classList.add('bare');
    var n=parseInt(p[0],10);
    if(!n){slides[0].classList.add('active');after(slides[0]);return;}
    i=Math.max(0,Math.min(slides.length-1,n-1));
    setFrags(slides[i],p.indexOf('start')>=0?0:frags(slides[i]).length);
    slides[i].classList.add('active');after(slides[i]);
  }
  applyHash();
})();
