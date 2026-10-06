(()=>{
const sidebar=document.querySelector('#sidebar'),pin=document.querySelector('.sidebar-pin'),menu=document.querySelector('.menu');
if(!sidebar||!pin)return;
const key='firmware-sidebar-pinned';
const apply=pinned=>{
  document.body.classList.toggle('sidebar-unpinned',!pinned);
  if(pinned)document.body.classList.remove('menu-open');
  pin.setAttribute('aria-pressed',String(pinned));
  pin.setAttribute('aria-label',pinned?'Открепить боковое меню':'Закрепить боковое меню');
  pin.title=pin.getAttribute('aria-label');
};
let pinned=localStorage.getItem(key)!=='false';
apply(pinned);
pin.addEventListener('click',()=>{pinned=!pinned;localStorage.setItem(key,String(pinned));apply(pinned)});
menu?.addEventListener('click',()=>{if(!pinned)requestAnimationFrame(()=>pin.focus())});
})();
