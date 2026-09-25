const CACHE='revelo-agenda-4.3.34';
const SHELL='/mobile/?v=4.3.34';
const ASSETS=[SHELL,'/mobile/manifest.webmanifest','/mobile-static/style.css?v=4.3.34','/mobile-static/app.js?v=4.3.34','/static/doctor_isotype.png'];
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(ASSETS)).then(()=>self.skipWaiting())));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('revelo-agenda-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{
  if(e.request.method!=='GET')return;
  const u=new URL(e.request.url);
  if(u.pathname.startsWith('/api/'))return;
  if(!(u.pathname.startsWith('/mobile/')||u.pathname.startsWith('/mobile-static/')))return;
  e.respondWith(fetch(e.request,{cache:'no-store'}).then(resp=>{
    const copy=resp.clone();caches.open(CACHE).then(c=>c.put(e.request,copy));return resp;
  }).catch(async()=>{
    const exact=await caches.match(e.request);
    if(exact)return exact;
    if(e.request.mode==='navigate')return caches.match(SHELL);
    return Response.error();
  }));
});
