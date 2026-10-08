(()=>{
  const modal=document.querySelector('#device-modal'),form=document.querySelector('#device-create-form'),toast=document.querySelector('#toast');
  if(!modal||!form)return;
  const showToast=text=>{if(!toast)return;toast.textContent=text;toast.classList.add('show');setTimeout(()=>toast.classList.remove('show'),2600)};
  const waitFor=(predicate,timeout=3500)=>new Promise((resolve,reject)=>{const started=performance.now(),check=()=>{if(predicate())return resolve();if(performance.now()-started>timeout)return reject(new Error('Не удалось подготовить форму копирования'));requestAnimationFrame(check)};check()});
  const setMode=copy=>{const eyebrow=modal.querySelector('header em'),title=modal.querySelector('#device-modal-title'),submit=form.querySelector('button[type="submit"]');if(eyebrow)eyebrow.textContent=copy?'КОПИЯ УСТРОЙСТВА':'НОВОЕ УСТРОЙСТВО';if(title)title.textContent=copy?'Копировать устройство':'Добавить устройство';if(submit)submit.textContent=copy?'Добавить копию':'Добавить устройство'};
  document.querySelectorAll('a[href="/devices/new"]').forEach(link=>link.addEventListener('click',()=>setMode(false)));

  const fillTemplate=async data=>{
    form.elements.name.value='';
    form.elements.address.value='';
    const icon=form.querySelector(`[name="icon_type"][value="${CSS.escape(data.icon_type||'switch')}"]`);if(icon)icon.checked=true;
    form.elements.vendor_id.value=data.vendor_id?String(data.vendor_id):'other';
    form.elements.vendor_id.dispatchEvent(new Event('change',{bubbles:true}));
    await waitFor(()=>data.vendor_id?[...form.elements.model_id.options].some(option=>option.value===String(data.model_id)):!form.elements.custom_model.disabled);
    if(data.vendor_id){form.elements.model_id.value=String(data.model_id||'');form.elements.model_id.dispatchEvent(new Event('change',{bubbles:true}));if(data.hardware_revision)form.elements.hardware_revision.value=data.hardware_revision}else form.elements.custom_model.value=data.custom_model||'';
    const source=form.querySelector(`[name="version_source"][value="${CSS.escape(data.version_source||'snmp')}"]`);if(source){source.checked=true;source.dispatchEvent(new Event('change',{bubbles:true}))}
    form.elements.profile_id.value=data.profile_id?String(data.profile_id):'';form.elements.profile_id.dispatchEvent(new Event('change',{bubbles:true}));
    form.elements.snmp_version.value=data.snmp_version||'2c';form.elements.security_level.value=data.security_level||'noAuthNoPriv';form.elements.snmp_version.dispatchEvent(new Event('change',{bubbles:true}));
    form.elements.snmp_port.value=data.snmp_port||161;form.elements.snmpv3_username.value=data.snmpv3_username||'';form.elements.auth_protocol.value=data.auth_protocol||'SHA';form.elements.privacy_protocol.value=data.privacy_protocol||'AES';
    form.elements.community.value='';form.elements.auth_password.value='';form.elements.privacy_password.value='';
    form.elements.installed_version.value=data.installed_version||'';form.elements.folder_id.value=data.folder_id?String(data.folder_id):'';form.elements.description.value=data.description||'';form.elements.auto_check.checked=Boolean(data.auto_check)&&data.version_source==='snmp';
    setMode(true);form.elements.name.focus();
  };

  const copyDevice=async(button,id)=>{button.disabled=true;button.closest('details')?.removeAttribute('open');try{const response=await fetch(`/api/devices/${id}/copy-template`),data=await response.json();if(!response.ok)throw new Error(data.detail||data.error||'Не удалось получить данные устройства');document.querySelector('a[href="/devices/new"]')?.click();await waitFor(()=>!modal.hidden&&document.activeElement===form.elements.name&&form.elements.vendor_id.options.length>1&&(!data.profile_id||[...form.elements.profile_id.options].some(option=>option.value===String(data.profile_id)))&&(!data.folder_id||[...form.elements.folder_id.options].some(option=>option.value===String(data.folder_id))));await fillTemplate(data)}catch(error){showToast(error.message||'Не удалось скопировать устройство')}finally{button.disabled=false}};

  const decorate=()=>document.querySelectorAll('.action-menu').forEach(menu=>{if(menu.querySelector('[data-copy-device]'))return;const edit=[...menu.querySelectorAll('a')].find(link=>link.textContent.includes('Редактировать устройство')),match=edit?.getAttribute('href')?.match(/\/devices\/(\d+)\/edit$/);if(!match)return;const button=document.createElement('button');button.type='button';button.dataset.copyDevice=match[1];button.textContent='Копировать устройство';button.onclick=()=>copyDevice(button,match[1]);edit.insertAdjacentElement('afterend',button)});
  const observer=new MutationObserver(()=>queueMicrotask(decorate));observer.observe(document.body,{childList:true,subtree:true});decorate();
})();
