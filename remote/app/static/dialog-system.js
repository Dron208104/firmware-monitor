(()=>{
let active=null;
const closeActive=()=>{if(active?.open)active.close('cancel')};
const build=({eyebrow='ПОДТВЕРЖДЕНИЕ',title,message,confirmText='Продолжить',danger=false,input=null,requireConfirmation=false,hideCancel=false})=>new Promise(resolve=>{
closeActive();
const dialog=document.createElement('dialog'),form=document.createElement('form'),header=document.createElement('header'),headCopy=document.createElement('div'),label=document.createElement('small'),heading=document.createElement('h2'),close=document.createElement('button'),body=document.createElement('div'),text=document.createElement('p'),footer=document.createElement('footer'),cancel=document.createElement('button'),confirm=document.createElement('button');
dialog.className=`app-dialog runtime-dialog${danger?' app-dialog--danger':''}`;form.method='dialog';label.textContent=eyebrow;heading.textContent=title;close.type='button';close.className='app-dialog__close';close.setAttribute('aria-label','Закрыть');close.textContent='×';headCopy.append(label,heading);header.append(headCopy,close);body.className='app-dialog__body';text.textContent=message;body.append(text);cancel.type='button';cancel.className='btn secondary';cancel.textContent='Отмена';confirm.type='submit';confirm.className=`btn ${danger?'danger':'primary'}`;confirm.textContent=confirmText;
let field=null;
if(input){const fieldLabel=document.createElement('label'),caption=document.createElement('span');caption.textContent=input.label;field=document.createElement('input');field.value=input.value||'';field.placeholder=input.placeholder||'';field.maxLength=input.maxLength||120;field.required=true;fieldLabel.append(caption,field);body.append(fieldLabel)}
if(requireConfirmation){const checkLabel=document.createElement('label'),check=document.createElement('input'),copy=document.createElement('span'),strong=document.createElement('strong'),hint=document.createElement('small');checkLabel.className='app-dialog__confirmation';check.type='checkbox';strong.textContent='Подтверждаю действие';hint.textContent='Это действие нельзя отменить.';copy.append(strong,hint);checkLabel.append(check,copy);body.append(checkLabel);confirm.disabled=true;check.onchange=()=>confirm.disabled=!check.checked}
if(!hideCancel)footer.append(cancel);footer.append(confirm);form.append(header,body,footer);dialog.append(form);document.body.append(dialog);active=dialog;
let settled=false;const finish=value=>{if(settled)return;settled=true;active=null;dialog.remove();resolve(value)};
cancel.onclick=()=>dialog.close('cancel');close.onclick=()=>dialog.close('cancel');dialog.addEventListener('click',event=>{if(event.target===dialog)dialog.close('cancel')});dialog.addEventListener('cancel',event=>{event.preventDefault();dialog.close('cancel')});dialog.addEventListener('close',()=>finish(dialog.returnValue==='confirm'?(field?field.value.trim():true):(field?null:false)));form.onsubmit=event=>{event.preventDefault();if(field&&!field.value.trim())return;dialog.close('confirm')};dialog.showModal();requestAnimationFrame(()=>field?.focus());
});
window.FirmwareDialog={
confirm:options=>build(options),
prompt:options=>build({...options,input:options.input||{label:'Значение'},confirmText:options.confirmText||'Сохранить'}),
alert:options=>build({...options,eyebrow:options.eyebrow||'СООБЩЕНИЕ',confirmText:'Закрыть',hideCancel:true}).then(()=>undefined),
};
})();
