(()=>{
  const logoutForm=document.querySelector('.current-user form[action="/logout"]');
  if(!logoutForm)return;
  const csrf=logoutForm.elements.csrf?.value;
  const idleMs=15*60*1000;
  const touchIntervalMs=60*1000;
  let idleTimer,lastTouch=Date.now(),touchPending=false,expired=false;

  const expire=()=>{
    if(expired)return;
    expired=true;
    const data=new FormData(logoutForm);
    fetch('/logout',{method:'POST',body:data,credentials:'same-origin',keepalive:true})
      .finally(()=>location.replace('/login?expired=1'));
  };
  const arm=()=>{
    clearTimeout(idleTimer);
    idleTimer=setTimeout(expire,idleMs);
  };
  const activity=()=>{
    if(expired)return;
    arm();
    const current=Date.now();
    if(touchPending||current-lastTouch<touchIntervalMs)return;
    lastTouch=current;touchPending=true;
    fetch('/api/session/touch',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf})})
      .then(response=>{if(response.status===401)expire()})
      .catch(()=>{})
      .finally(()=>{touchPending=false});
  };
  ['pointerdown','keydown','touchstart','scroll'].forEach(name=>addEventListener(name,activity,{passive:true}));
  arm();
})();
