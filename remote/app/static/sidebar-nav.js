(()=>{
  const overview=document.querySelector('[data-nav-overview]');
  const devices=document.querySelector('[data-nav-devices]');
  if(!overview||!devices||location.pathname!=='/')return;
  const sync=()=>{
    const equipment=location.hash==='#equipment';
    overview.classList.toggle('active',!equipment);
    devices.classList.toggle('active',equipment);
  };
  addEventListener('hashchange',sync);
  sync();
})();
