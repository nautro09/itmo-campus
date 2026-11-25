"use strict";
const form=document.getElementById("login-input");
const entry=document.getElementById("entry");
const feedback=document.getElementById("feedback");
form.addEventListener("submit",async event=>{
  event.preventDefault();
  const button=form.querySelector("button");
  if(button.disabled||!entry.value)return;
  button.disabled=true;
  try{
    const response=await fetch("/login/type",{method:"POST",body:entry.value,cache:"no-store"});
    feedback.textContent=response.ok?"Введено в выбранное поле.":response.status===409?"Сначала выбери поле на странице ИТМО.":"Открой окно входа заново.";
    if(response.ok)entry.value="";
  }catch{feedback.textContent="Нет связи с сервером."}
  finally{button.disabled=false}
});
window.addEventListener("pagehide",()=>{entry.value=""});
