(()=>{
  const updateStatuses=new Set(['Есть обновление','Доступно обновление']);
  const deviceRows=[...document.querySelectorAll('#device-rows tr[data-search]')];
  if(!deviceRows.length)return;

  const addressOf=row=>row.querySelector('[data-column="ip"]')?.childNodes[0]?.textContent.trim();
  const renderVersion=(row,device)=>{
    if(!updateStatuses.has(device.status)||!device.available_version)return;
    const versions=row.querySelector('.firmware-versions');
    if(!versions)return;
    let available=versions.querySelector('.firmware-available');
    let arrow=versions.querySelector('.firmware-arrow');
    if(!arrow){
      arrow=document.createElement('span');
      arrow.className='firmware-arrow';
      arrow.setAttribute('aria-hidden','true');
      arrow.textContent='→';
    }
    if(!available){
      available=document.createElement('span');
      available.className='firmware-available';
      available.innerHTML='<small>Доступна</small><b class="mono"></b>';
    }
    available.querySelector('b').textContent=device.available_version;
    const hidden=versions.querySelector('[data-column="available"]');
    versions.insertBefore(arrow,hidden);
    versions.insertBefore(available,hidden);
    if(hidden)hidden.textContent=device.available_version;
  };

  fetch('/api/devices')
    .then(response=>response.ok?response.json():Promise.reject(new Error('API unavailable')))
    .then(devices=>deviceRows.forEach(row=>{
      const device=devices.find(item=>item.address===addressOf(row));
      if(device)renderVersion(row,device);
    }))
    .catch(()=>{});
})();
