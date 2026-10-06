(()=>{
  const results=document.querySelector('[data-equipment-results]');
  if(!results)return;
  const buttons=[...document.querySelectorAll('[data-quick-filter]')];
  const search=document.querySelector('#device-search');
  const activate=mode=>{
    const current=results.dataset.quickFilter||'all';
    const next=mode==='updates'&&current==='updates'?'all':mode;
    results.dataset.quickFilter=next;
    buttons.forEach(button=>{
      const active=button.dataset.quickFilter===next;
      button.classList.toggle('active',active);
      button.setAttribute('aria-pressed',String(active));
    });
    search?.dispatchEvent(new Event('input',{bubbles:true}));
    document.querySelector('#equipment')?.scrollIntoView({behavior:'smooth',block:'start'});
  };
  buttons.forEach(button=>button.addEventListener('click',()=>activate(button.dataset.quickFilter)));
})();
