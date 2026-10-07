(()=>{
  const results=document.querySelector('[data-equipment-results]');
  if(!results)return;
  const buttons=[...document.querySelectorAll('[data-quick-filter]')];
  const search=document.querySelector('#device-search');
  const filterToggle=document.querySelector('[data-filter-toggle]');
  const advancedFilters=document.querySelector('#equipment-filters');
  const advancedInputs=[...document.querySelectorAll('#vendor-filter,#status-filter')];
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
  const syncAdvancedState=()=>{
    const active=advancedInputs.some(input=>Boolean(input.value));
    filterToggle?.classList.toggle('active',active);
  };
  filterToggle?.addEventListener('click',()=>{
    const open=advancedFilters?.hasAttribute('hidden');
    advancedFilters?.toggleAttribute('hidden',!open);
    filterToggle.setAttribute('aria-expanded',String(open));
  });
  advancedInputs.forEach(input=>input.addEventListener('change',syncAdvancedState));
  document.addEventListener('keydown',event=>{
    if(event.key!=='Escape'||advancedFilters?.hasAttribute('hidden'))return;
    advancedFilters?.setAttribute('hidden','');
    filterToggle?.setAttribute('aria-expanded','false');
    filterToggle?.focus();
  });
  if(advancedInputs.some(input=>Boolean(input.value))){
    advancedFilters?.removeAttribute('hidden');
    filterToggle?.setAttribute('aria-expanded','true');
  }
  syncAdvancedState();
  const activityPanel=document.querySelector('.activity-panel');
  const equipmentPanel=document.querySelector('.dashboard-equipment');
  if(activityPanel&&equipmentPanel){
    const desktopLayout=matchMedia('(min-width:1551px)');
    const syncActivityHeight=()=>{
      if(!desktopLayout.matches){activityPanel.style.removeProperty('height');activityPanel.style.removeProperty('max-height');return}
      const available=Math.max(280,innerHeight-activityPanel.getBoundingClientRect().top-20);
      const height=Math.min(Math.max(440,Math.ceil(equipmentPanel.getBoundingClientRect().height)),available);
      activityPanel.style.height=`${height}px`;
      activityPanel.style.maxHeight=`${height}px`;
    };
    new ResizeObserver(syncActivityHeight).observe(equipmentPanel);
    desktopLayout.addEventListener('change',syncActivityHeight);
    addEventListener('resize',syncActivityHeight,{passive:true});
    requestAnimationFrame(syncActivityHeight);
  }
})();
