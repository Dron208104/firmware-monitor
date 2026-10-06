(()=>{
  const tooltip=document.createElement('div');
  tooltip.id='device-description-tooltip';
  tooltip.className='device-description-tooltip';
  tooltip.setAttribute('role','tooltip');
  tooltip.hidden=true;
  document.body.append(tooltip);

  const show=target=>{
    const text=target?.dataset.description?.trim();
    if(!text)return;
    tooltip.textContent=text;
    tooltip.hidden=false;
    const anchor=target.getBoundingClientRect();
    const tip=tooltip.getBoundingClientRect();
    const left=Math.max(10,Math.min(innerWidth-tip.width-10,anchor.left));
    const above=anchor.top-tip.height-9;
    tooltip.style.left=`${left}px`;
    tooltip.style.top=`${above>10?above:anchor.bottom+9}px`;
  };
  const hide=()=>{tooltip.hidden=true};

  document.addEventListener('mouseover',event=>{
    const target=event.target.closest('.device-name.has-description');
    if(target)show(target);
  });
  document.addEventListener('mouseout',event=>{
    if(event.target.closest('.device-name.has-description'))hide();
  });
  document.addEventListener('focusin',event=>{
    const target=event.target.closest('.device-name.has-description');
    if(target)show(target);
  });
  document.addEventListener('focusout',event=>{
    if(event.target.closest('.device-name.has-description'))hide();
  });
  document.addEventListener('keydown',event=>{if(event.key==='Escape')hide()});
  addEventListener('scroll',hide,{passive:true});
  addEventListener('resize',hide);
})();
