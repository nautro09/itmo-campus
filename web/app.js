"use strict";
(() => {
  const $ = (selector, at=document) => at.querySelector(selector);
  const main = $("#content"), dialog = $("#dialog"), toast = $("#toast");
  const demo = new URLSearchParams(location.search).get("demo") === "1";
  const paths = {
    today:'<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
    week:'<rect x="3" y="5" width="18" height="16" rx="3"/><path d="M7 3v4m10-4v4M3 10h18M7 14h2m3 0h2m-7 3h2"/>',
    tasks:'<rect x="3" y="3" width="18" height="18" rx="4"/><path d="m7.3 12 3.3 3.2 6.6-7"/>',
    mail:'<rect x="3" y="5" width="18" height="14" rx="3"/><path d="m4 7 8 6 8-6"/>',
    profile:'<circle cx="12" cy="8" r="3.5"/><path d="M5 20a7 7 0 0 1 14 0"/>',
    arrow:'<path d="M4 12h15m-6-6 6 6-6 6"/>',chev:'<path d="m9 5 7 7-7 7"/>',down:'<path d="m5 9 7 7 7-7"/>',
    refresh:'<path d="M20 7v5h-5M4 17v-5h5"/><path d="M5.2 8a7.5 7.5 0 0 1 12.4-3L20 8m-.9 8A7.5 7.5 0 0 1 6.4 19L4 16"/>',
    pin:'<path d="M19 10c0 5-7 11-7 11S5 15 5 10a7 7 0 1 1 14 0Z"/><circle cx="12" cy="10" r="2"/>',
    group:'<circle cx="9" cy="8" r="3"/><path d="M3 19a6 6 0 0 1 12 0m.5-13a3 3 0 0 1 0 5.5M17 14a5 5 0 0 1 4 5"/>',
    check:'<path d="m4 12 5 5L20 6"/>',plus:'<path d="M12 4v16M4 12h16"/>',close:'<path d="m5 5 14 14M19 5 5 19"/>',
    edit:'<path d="m4 16-1 5 5-1L20 8l-4-4L4 16Zm10-10 4 4"/>',trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',
    compass:'<circle cx="12" cy="12" r="9"/><path d="m15.5 7.5-2 6-5 3 2-6Z"/>',
    bell:'<path d="M5 17h14l-2-4V9A5 5 0 0 0 7 9v4l-2 4Zm5 3a2 2 0 0 0 4 0"/>',
    book:'<path d="M3 5c4-1 7 0 9 2 2-2 5-3 9-2v14c-4-1-6 0-9 2-3-2-5-3-9-2V5Zm9 2v14"/>',
    send:'<path d="m2 11 20-8-7 19-4-8-9-3Zm9 3L22 3"/>',file:'<path d="M5 2h9l5 5v15H5zM14 2v6h5M8 12h8m-8 4h6"/>',
    clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',undo:'<path d="M8 3 3 8l5 5M3 8h11a6 6 0 0 1 0 12"/>',
    change:'<path d="M4 6h9m4 0h3M4 12h3m4 0h9M4 18h9m4 0h3"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="15" cy="18" r="2"/>',
    message:'<path d="M3 4h18v13H9l-5 4v-4H3zM7 8h10m-10 4h7"/>'
  };
  const names={today:"Сегодня",week:"Расписание",tasks:"Задания",mail:"Почта",profile:"Профиль"};
  const esc = value => String(value??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const ico = name => '<svg class="ico" aria-hidden="true" viewBox="0 0 24 24">'+(paths[name]||"")+'</svg>';
  const attr = (key,value) => ` data-${key}="${esc(value)}"`;
  const btn = (action,text,icon,cls="",extra={}) => `<button type="button" class="btn ${cls}" data-action="${action}"${Object.entries(extra).map(([k,v])=>attr(k,v)).join("")}>${icon?ico(icon):""}${esc(text)}</button>`;
  const iconBtn = (action,label,icon,extra={}) => `<button type="button" class="icon-btn" title="${esc(label)}" aria-label="${esc(label)}" data-action="${action}"${Object.entries(extra).map(([k,v])=>attr(k,v)).join("")}>${ico(icon)}</button>`;
  const tabLink = (tab,text) => `<button class="link" type="button" data-tab="${tab}">${esc(text)} ${ico("arrow")}</button>`;
  const themes = {paper:["Бумага","#eeeae4","#b7a4cd","#cedf8a"],night:["Полночь","#252724","#bdabdd","#d4e99d"],mint:["Шалфей","#e2ece1","#9ab9a0","#dce8a7"]};
  let tab=Object.hasOwn(names,location.hash.slice(1))?location.hash.slice(1):"today";
  let state, tg=null, initData="", busy=false, toastTimer, selectedDay="", filter="active", category="", expandedTask="", expandedMail="";
  const isoDate=d=>d.toISOString().slice(0,10);
  function addDays(day,n){const d=new Date(day+"T12:00:00Z");d.setUTCDate(d.getUTCDate()+n);return isoDate(d)}
  function dateFmt(day, opts={day:"numeric",month:"long"}){if(!day)return "—";const d=new Date(String(day).slice(0,10)+"T12:00:00Z");return Number.isNaN(+d)?String(day):new Intl.DateTimeFormat("ru-RU",{...opts,timeZone:"UTC"}).format(d)}
  const cap=s=>s?s[0].toUpperCase()+s.slice(1):s;
  const initials=name=>String(name||"П").trim().split(/\s+/).slice(0,2).map(x=>x[0]||"").join("").toUpperCase();
  const plural=(n,one,few,many)=>n%100>=11&&n%100<=14?many:n%10===1?one:n%10>=2&&n%10<=4?few:many;
  const idsame=(a,b)=>String(a)===String(b);
  const taskBy=id=>state.tasks.find(t=>idsame(t.id,id));
  function normalize(data){
    const today=data.today||isoDate(new Date());
    return {...data,today,profile:data.profile||{},settings:{theme:"paper",interval:1,morning_time:"07:30",travel_minutes:35,campus_minutes:{},...data.settings},services:data.services||{},days:Array.isArray(data.days)?data.days:[],tasks:Array.isArray(data.tasks)?data.tasks:[],mail:Array.isArray(data.mail)?data.mail:[],categories:Array.isArray(data.categories)?data.categories:[]};
  }
  function moscowTime(){
    const d=new Date(state.now||Date.now());
    return Number.isNaN(+d)?"00:00":new Intl.DateTimeFormat("ru-RU",{timeZone:"Europe/Moscow",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(d);
  }
  function clockMinutes(s){const [h,m]=String(s||"0:0").split(":").map(Number);return (h*60+m)||0}
  function dueText(s){if(!s)return "Без срока";const [d,t]=s.replace("T"," ").split(" ");let label=d===state.today?"Сегодня":d===addDays(state.today,1)?"Завтра":dateFmt(d,{day:"numeric",month:"short"});return label+(t?" · "+t.slice(0,5):"")}
  function dayData(d){return state.days.find(x=>x.date===d)}
  function demoModel(){
    const d="2026-11-18", tasks=[
      {id:1,title:"Подготовить прототип интерфейса",category:"Дизайн",due:d+" 20:00",lead:60,done:false,steps:[{id:1,title:"Собрать референсы",done:true},{id:2,title:"Собрать кликабельный прототип",done:false}]},
      {id:2,title:"Оформить отчёт по физике",category:"Лабораторные",due:addDays(d,1)+" 18:00",lead:1440,done:false,steps:[]},
      {id:3,title:"Решить задачи к семинару",category:"Учёба",due:addDays(d,3)+" 12:00",lead:60,done:false,steps:[]},
      {id:4,title:"Выбрать тему проекта",category:"Дизайн",due:addDays(d,-1)+" 15:00",lead:0,done:true,steps:[]}
    ];
    function lesson(subject,start,end,room,type,group="Поток Д-2",building="Кронверкский пр., 49"){return {subject,time_start:start,time_end:end,room,work_type:type,group,building,teacher_name:"Преподаватель курса"}}
    return normalize({today:d,now:d+"T09:10:00+03:00",profile:{name:"Александра Соколова",isu:"000000"},settings:{theme:"paper",morning_on:true,morning_time:"07:30",interval:1,travel_on:true,travel_minutes:35,campus_minutes:{},weekly_on:true,mail_on:true},
      services:{itmo:{ok:true,detail:"Демонстрационное подключение"},isu:{ok:true,detail:"Демонстрационные входящие ИСУ"},mail:{ok:true,detail:"Демонстрационный ящик"},telegram:{ok:true,detail:"Демонстрационный чат"}},
      days:Array.from({length:7},(_,i)=>({date:addDays(d,i),lessons:[
        [lesson("Математический анализ","09:50","11:20","2403","Лекция"),lesson("Проектирование интерфейсов","11:40","13:10","1407","Практика","Дизайн-3"),lesson("Общая физика","15:20","16:50","310","Лабораторная","Физика-1","ул. Ломоносова, 9")],
        [lesson("Алгоритмы и структуры данных","10:00","11:30","201","Практика")],[lesson("Основы проектирования","11:40","13:10","307","Лекция"),lesson("Иностранный язык","13:30","15:00","210","Семинар")],[],[],[lesson("Математический анализ","09:50","11:20","2403","Семинар")],[lesson("Общая физика","13:30","15:00","312","Лекция")]][i]})),tasks,categories:["Учёба","Лабораторные","Дизайн","Проекты","Личное"],mail:[
        {id:1,source:"ИСУ",subject:"Материалы к лабораторной работе",sender:"Кафедра физики",date:"17 ноя.",body:"Доброе утро! К следующему занятию подготовьте отчёт по измерениям и постройте график зависимости силы тока от напряжения. Срок сдачи — завтра в 18:00."},
        {id:2,source:"Email",subject:"Встреча проектных команд",sender:"Проектный офис",date:addDays(d,-1)+" 16:40",body:"В четверг встречаемся с кураторами в 15:00. Возьмите с собой прототип и список вопросов."}]});
  }
  function sampleDraft(text){
    const title=text.trim().split(/[\n.!?]/)[0].trim().slice(0,160)||"Новое задание";
    const time=text.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
    return {title,category:"Учёба",due:(/завтра/i.test(text)?addDays(state.today,1):state.today)+" "+(time?time[1].padStart(2,"0")+":"+time[2]:"23:59"),lead:60};
  }
  function simulate(action,p){
    let task=taskBy(p.task_id??p.id);
    let notice=""; const nextId=rows=>Math.max(0,...rows.map(r=>Number(r.id)||0))+1;
    switch(action){
    case "task_from_text":return {draft:sampleDraft(p.text)};
    case "task_save":
      if(!task){task={id:nextId(state.tasks),done:false,steps:(p.steps||[]).map((title,i)=>({id:i+1,title,done:false}))};state.tasks.push(task)}
      Object.assign(task,{title:p.title,category:p.category,due:p.due,lead:p.lead});
      if(!state.categories.includes(p.category))state.categories.push(p.category);break;
    case "task_done":task.done=p.done;break;
    case "task_delete":state.tasks=state.tasks.filter(t=>!idsame(t.id,p.id));break;
    case "step_add":task.steps.push({id:nextId(task.steps),title:p.title,done:false});break;
    case "step_done":{const step=task.steps.find(x=>idsame(x.id,p.id));if(step)step.done=p.done;break}
    case "step_delete":task.steps=task.steps.filter(x=>!idsame(x.id,p.id));break;
    case "settings":Object.assign(state.settings,p);break;
    case "week_report":notice=buildReport();break;
    case "isu_login":notice="В подключённом боте откроется официальный экран входа в ИСУ в приватном окне на твоём устройстве. В демоверсии используется тестовый ящик.";break;
    case "itmo_login":notice="В демонстрационном режиме используется вымышленный профиль. В подключённом боте откроется окно официального входа в ИТМО ID в приватном окне на твоём устройстве.";break;
    case "refresh":notice="Демонстрационное расписание обновлено.";break;
    case "bars_check":notice="Физика · 42 балла (демопример)";break;
    case "mail_check":notice="Демонстрационный ящик проверен.";break;
    case "check_services":notice="Проверены демонстрационные подключения.";break;
    default:throw Error("Действие пока недоступно.");
    }
    try{localStorage.setItem("para.demo.v2",JSON.stringify(state))}catch{}
    return {...state,notice};
  }
  async function request(path,body){
    const res=await fetch("/api/"+path,{method:"POST",cache:"no-store",headers:{"Content-Type":"application/json","X-Telegram-Init-Data":initData},body:JSON.stringify(body)});
    let result;try{result=await res.json()}catch{throw Error("Сервер вернул неподходящий ответ. Попробуй ещё раз.")}
    if(!res.ok||result.error)throw Error(result.error||"Не удалось выполнить действие.");
    return result;
  }
  function notify(message){clearTimeout(toastTimer);toast.textContent=message;toast.classList.add("on");toastTimer=setTimeout(()=>toast.classList.remove("on"),3600)}
  let pollTimer;
  function watchCheck(){
    clearTimeout(pollTimer);
    if(!state?.check_pending || demo)return;
    pollTimer=setTimeout(async()=>{
      try{
        const update=await request("services",{});
        state.services=update.services;
        state.check_pending=update.check_pending;
        if(tab==="profile"){
          const list=main.querySelector(".service-list");
          if(list){const panel=document.createElement("div");panel.innerHTML=profile();list.replaceChildren(...panel.querySelector(".service-list").children)}
        }
        if(!state.check_pending)notify("Проверка подключений завершена.");
        watchCheck();
      }catch{notify("Не удалось обновить статусы. Нажми «Проверить подключения» ещё раз.")}
    },1800);
  }
  async function privateLogin(source){
    if(demo){notify("Приватный вход доступен в личном чате с ботом.");return}
    try{
      const response=await fetch("/login/open/"+source,{method:"POST",headers:{"X-Telegram-Init-Data":initData}});
      if(!response.ok)throw Error(response.status===429?"Закрой предыдущее окно входа и попробуй ещё раз.":"Открой вход из личного чата с ботом.");
      const result=await response.json();
      location.assign(result.viewer);
    }catch(e){notify(e.message)}
  }
  async function perform(action,p={},options={}){
    if(busy)return null;busy=true;main.setAttribute("aria-busy","true");
    try{
      const result=demo?simulate(action,p):await request("action",{action,...p});
      if(result.draft)return result.draft;
      state=normalize(result);watchCheck();if(options.close&&dialog.open)dialog.close();
      render();
      if(result.notice){
        if(options.long||result.notice.length>160||result.notice.includes("\n"))showReport(options.title||"Результат проверки",result.notice);
        else notify(result.notice);
      }else if(options.message)notify(typeof options.message==="function"?options.message(state):options.message);
      return result;
    }catch(e){const message=e?.message||"Не удалось связаться с сервером.";if(dialog.open){const slot=$(".dialog-error",dialog);if(slot){slot.textContent=message;slot.hidden=false}else notify(message)}else notify(message);return null}
    finally{busy=false;main.removeAttribute("aria-busy")}
  }
  function modal(title,html){$(".dialog-content").innerHTML=`<div class="dialog-title"><h2>${esc(title)}</h2>${iconBtn("close-modal","Закрыть","close")}</div><div role="alert" class="alert dialog-error" hidden></div>${html}`;if(!dialog.open)dialog.showModal();const focusEl=dialog.querySelector("input:not([type=hidden]),textarea,select");if(focusEl)focusEl.focus()}
  function showReport(title,text){modal(title,`<p class="report notice-text">${esc(text)}</p>${btn("close-modal","Закрыть",null,"primary")}`)}
  function empty(title,text,control=""){return `<div class="empty"><strong>${esc(title)}</strong>${esc(text)}${control?"<div>"+control+"</div>":""}</div>`}
  function mast(title,sub,controls=""){return `<div class="mast"><div><h1>${esc(title)}</h1>${sub?`<p>${esc(sub)}</p>`:""}</div><div class="page-actions">${controls}</div></div>`}
  const section=(title,right="",sub="")=>`<div class="section-head"><div><h2>${esc(title)}</h2>${sub?`<div class="meta">${esc(sub)}</div>`:""}</div>${right}</div>`;
  function shell(){
    const theme=Object.hasOwn(themes,state?.settings?.theme)?state.settings.theme:"paper";document.documentElement.dataset.theme=theme;
    const color=getComputedStyle(document.documentElement).getPropertyValue("--bg").trim();
    $('meta[name="theme-color"]').content=color;try{tg?.setHeaderColor(color);tg?.setBackgroundColor(color)}catch{}
    for(const [id,mobile] of [["desktop-nav",false],["mobile-nav",true]]){
      document.getElementById(id).innerHTML=Object.entries(names).map(([k,v])=>`<button type="button" data-tab="${k}" class="${mobile?"":"nav-btn "}${k===tab?"active":""}" ${k===tab?'aria-current="page"':""}>${ico(k)}<span>${esc(v)}</span></button>`).join("");
    }
    const name=state?.profile?.name||"Мой профиль";
    $("#crumb").textContent=names[tab];$("#avatar").textContent=initials(name);
    $("#rail-user").innerHTML=`<span class="avatar-box">${esc(initials(name))}</span><span><b>${esc(name)}</b><small>Профиль ИТМО ID</small></span>${ico("chev")}`;
    $("#mode").innerHTML=demo?'<span class="mode-label"><i></i>Деморежим</span>':"";
  }
  function lessonList(day){
    if(!day)return empty("Расписание пока не загружено","Проверь подключение к my.itmo в профиле.",tabLink("profile","Открыть профиль"));
    const stale = day.stale ? '<p class="cached-day">Сохранённая копия. Свежие данные за этот день пока не получены.</p>' : "";
    if(!day.lessons?.length)return stale + (day.stale
      ? empty("В копии занятий нет","Дождись обновления перед планированием дня.")
      : empty("Пар нет","Этот день свободен по данным расписания."));
    return stale + '<div class="timeline">'+[...day.lessons].sort((a,b)=>a.time_start.localeCompare(b.time_start)).map(x=>`<div class="lesson"><div class="lesson-time">${esc(x.time_start)}<small>${esc(x.time_end)}</small></div><i class="marker"></i><div><h3>${esc(x.subject)}</h3><p>${[x.work_type,x.room&&"ауд. "+x.room,x.building].filter(Boolean).map(esc).join(" · ")}</p>${[x.group,x.teacher_name].some(Boolean)?`<p>${[x.group,x.teacher_name].filter(Boolean).map(esc).join(" · ")}</p>`:""}</div></div>`).join("")+'</div>';
  }
  function checkButton(action,item,parent){
    const checked=!!item.done;const label=checked?"Отменить выполнение":"Отметить выполненным";
    return `<button type="button" class="check ${checked?"done":""}" aria-label="${label} — ${esc(item.title)}" title="${label}" aria-pressed="${checked}" data-action="${action}" data-id="${esc(item.id)}"${parent!==undefined?attr("parent",parent):""}>${checked?ico("check"):""}</button>`;
  }
  function tasksSorted(){return [...state.tasks].sort((a,b)=>String(a.due||"9999").localeCompare(String(b.due||"9999"))||Number(a.id)-Number(b.id))}
  function hero(){
    const time=moscowTime(), current=dayData(state.today);
    const lessons=state.days.flatMap(d=>(d.lessons||[]).map(x=>({...x,date:d.date,stale:d.stale}))).sort((a,b)=>(a.date+a.time_start).localeCompare(b.date+b.time_start));
    const next=lessons.find(x=>x.date>state.today||(x.date===state.today&&x.time_end>time));
    const now=next&&next.date===state.today&&next.time_start<=time;
    const label=(now?"Сейчас идёт":next?"Ближайшая пара":"Расписание")+(next?.stale||(!next&&current?.stale)?" · сохранённая копия":"");
    const date=next&&next.date!==state.today?dateFmt(next.date,{day:"numeric",month:"short"})+" · ":"";
    const title=next?.subject||(current?.stale?"В сохранённой копии пар нет":current?"Свободное время":"Расписание пока не загружено");
    const room=[next?.room&&"ауд. "+next.room,next?.building].filter(Boolean).join(" · ");
    return `<section class="hero" aria-label="Ближайшее занятие"><div class="hero-copy"><div class="hero-kicker"><i class="live-dot"></i>${label}</div><div class="hero-time">${next?esc(date+next.time_start+" — "+next.time_end):""}</div><h2>${esc(title)}</h2><div class="hero-meta">${room?`<span class="place">${ico("pin")} ${esc(room)}</span>`:""}${next?.work_type?`<span>${ico("book")} ${esc(next.work_type)}</span>`:""}${!next?(current?"В загруженном расписании нет предстоящих пар.":"Подключи my.itmo в профиле."):''}</div></div><div class="orbital" aria-hidden="true"><i class="orbit-line"></i><i class="orbit-line two"></i><i class="ring"></i><i class="planet"></i><i class="ring front"></i><i class="spark"></i><i class="spark two"></i></div></section>`;
  }
  function today(){
    const today=dayData(state.today),open=tasksSorted().filter(t=>!t.done);
    const mini=open.slice(0,4).map(t=>`<div class="task-mini">${checkButton("task-done",t)}<button type="button" class="mini-content" data-action="open-task" data-id="${esc(t.id)}"><b class="task-title">${esc(t.title)}</b><small>${esc(dueText(t.due))} &nbsp;·&nbsp; ${esc(t.category||"Без категории")}</small></button></div>`).join("");
    return mast("Сегодня",cap(dateFmt(state.today,{weekday:"long",day:"numeric",month:"long"})),iconBtn("refresh","Обновить расписание","refresh"))+
      (state.warning?`<p class="alert">${esc(state.warning)}</p>`:"")+hero()+(state.wake_preview?.action==="set"?`<div class="wake-summary">Расчёт подъёма · ${esc(state.wake_preview.day)} · <b>${new Date(state.wake_preview.at*1000).toLocaleTimeString("ru-RU",{timeZone:"Europe/Moscow",hour:"2-digit",minute:"2-digit"})} МСК</b></div>`:"")+
      `<div class="dash-grid"><section class="panel">${section("Расписание на день",tabLink("week","На неделю"))}${lessonList(today)}</section><section class="panel">${section("Ближайшие дедлайны",tabLink("tasks","Все"))}${mini||empty("Всё под контролем","Открытых заданий пока нет.",btn("new-task","Добавить задание","plus","minor"))}</section></div>`;
  }
  function loadData(d){
    const day=dayData(d),count=day?.lessons?.length||0;
    const tasks=state.tasks.filter(t=>!t.done&&String(t.due||"").startsWith(d)).length;
    return {known:!!day,count,tasks};
  }
  function buildReport(){return "Нагрузка на ближайшие семь дней\n\n"+Array.from({length:7},(_,i)=>{const d=addDays(state.today,i),x=loadData(d);return cap(dateFmt(d,{weekday:"short",day:"numeric",month:"short"}))+" · "+(x.known?x.count+" "+plural(x.count,"пара","пары","пар"):"расписание уточняется")+" · "+x.tasks+" "+plural(x.tasks,"дедлайн","дедлайна","дедлайнов")}).join("\n")}
  function week(){
    const days=Array.from({length:7},(_,i)=>addDays(state.today,i));if(!days.includes(selectedDay))selectedDay=state.today;
    const strip=days.map(d=>`<button type="button" class="week-day ${selectedDay===d?"active":""}" aria-pressed="${selectedDay===d}" data-action="select-day" data-date="${d}"><span>${cap(dateFmt(d,{weekday:"short"}))}</span><strong>${Number(d.slice(-2))}</strong><i class="tick"></i></button>`).join("");
    const counts=days.map(loadData);const max=Math.max(1,...counts.map(x=>x.count+x.tasks));
    const stats=days.map((d,i)=>`<div class="stats-row"><b>${cap(dateFmt(d,{weekday:"short"}))}</b><div class="bar"><i style="width:${Math.round((counts[i].count+counts[i].tasks)/max*100)}%"></i></div><small>${counts[i].known?counts[i].count:"?"} пар · ${counts[i].tasks} зад.</small></div>`).join("");
    return mast("Расписание","Ближайшие семь дней",iconBtn("refresh","Обновить расписание","refresh"))+(state.warning?`<p class="alert">${esc(state.warning)}</p>`:"")+`<div class="week-strip">${strip}</div><div class="week-grid"><section class="panel">${section(cap(dateFmt(selectedDay,{weekday:"long",day:"numeric",month:"long"})))}${lessonList(dayData(selectedDay))}</section><section class="panel">${section("Нагрузка на неделю")}${'<div class="stats-list">'+stats+'</div>'}<div class="panel-actions">${btn("week-report","Недельная сводка","file","minor")}</div></section></div>`;
  }
  function taskDetails(t){
    const steps=t.steps||[];
    const list=steps.map(st=>`<div class="sub-row">${checkButton("step-done",st,t.id)}<span class="${st.done?"done-text":""}">${esc(st.title)}</span>${iconBtn("delete-step","Удалить подзадачу","close",{id:st.id,parent:t.id})}</div>`).join("");
    return `<div class="details"><p class="meta">Подзадачи · ${steps.filter(x=>x.done).length}/${steps.length}</p>${list}<form class="step-form" data-form="step" data-id="${esc(t.id)}"><input name="step" aria-label="Название подзадачи" placeholder="Новая подзадача" maxlength="160" required><button class="icon-btn" aria-label="Добавить подзадачу">${ico("plus")}</button></form><div class="btn-row">${btn("edit-task","Изменить","edit","minor",{id:t.id})}${btn("task-done",t.done?"Отменить выполнение":"Выполнить",t.done?"undo":"check","minor",{id:t.id})}${iconBtn("delete-task","Удалить задание","trash",{id:t.id})}</div></div>`;
  }
  function tasks(){
    const filters={active:"Открытые",week:"На неделю",overdue:"Просроченные",done:"Готовые",all:"Все"};
    const cats=[...new Set([...state.categories,...state.tasks.map(x=>x.category)].filter(Boolean))].sort((a,b)=>a.localeCompare(b,"ru"));
    const selected=tasksSorted().filter(t=>{
      if(category&&t.category!==category)return false;
      const now=state.today+" "+moscowTime(),end=addDays(state.today,7);
      if(filter==="done")return !!t.done;
      if(filter==="all")return true;
      if(t.done)return false;
      if(filter==="overdue")return !!t.due&&t.due<now;
      if(filter==="week")return !!t.due&&t.due>=state.today&&t.due<end;
      return true;
    });
    const controls=Object.entries(filters).map(([k,v])=>`<button type="button" data-action="task-filter" data-value="${k}" class="${k===filter?"active":""}" aria-pressed="${k===filter}">${v}</button>`).join("");
    const list=selected.map(t=>{const expanded=idsame(t.id,expandedTask);return `<div class="task-group ${expanded?"expanded":""}"><div class="task-row">${checkButton("task-done",t)}<button class="row-main" type="button" aria-expanded="${expanded}" data-action="expand-task" data-id="${esc(t.id)}"><h3 class="${t.done?"done-text":""}">${esc(t.title)}</h3><span class="item-meta"><span class="tag lilac">${esc(t.category||"Без категории")}</span><span>${esc(dueText(t.due))}</span>${t.steps?.length?`<span>☑ ${t.steps.filter(x=>x.done).length}/${t.steps.length}</span>`:""}</span></button>${iconBtn("expand-task",expanded?"Свернуть задание":"Открыть задание",expanded?"down":"chev",{id:t.id})}</div>${expanded?taskDetails(t):""}</div>`}).join("");
    const addControls=btn("from-text","Из сообщения","message","minor")+btn("new-task","Добавить","plus","primary");
    return mast("Задания","Дедлайны, категории и подзадачи",addControls)+`<div class="tool-bar"><div class="segment" aria-label="Фильтр заданий">${controls}</div><select data-control="category" aria-label="Категория"><option value="">Все категории</option>${cats.map(c=>`<option value="${esc(c)}" ${c===category?"selected":""}>${esc(c)}</option>`).join("")}</select></div><div class="panel">${list||empty("Заданий здесь пока нет","Добавь задание или выбери другой фильтр.")}</div>`;
  }
  function mailDate(s){if(!s)return "";const d=new Date(s);return Number.isNaN(+d)?String(s).slice(0,16):new Intl.DateTimeFormat("ru-RU",{day:"numeric",month:"short",timeZone:"Europe/Moscow"}).format(d)}
  function mail(){
    const sources=[["ИСУ",state.services.isu],["IMAP",state.services.mail]];
    const svc={ok:sources.some(([,v])=>v?.ok),detail:sources.map(([k,v])=>k+" · "+(v?.detail||"Ожидает проверки")).join(" / ")};
    const rows=state.mail.map(m=>{const open=idsame(m.id,expandedMail);
      return `<div class="mail-group ${open?"expanded":""}"><button type="button" class="mail-item" data-action="expand-mail" data-id="${esc(m.id)}" aria-expanded="${open}"><span class="mail-icon">${ico("mail")}</span><span class="mail-center"><small>${m.source?`<span class="tag lilac">${esc(m.source)}</span> `:""}${esc(m.sender||"Отправитель не указан")}</small><strong>${esc(m.subject||"Без темы")}</strong></span><time>${esc(m.source==="ИСУ"?m.date:mailDate(m.date))}</time></button>${open?`<div class="details"><div class="mail-body">${esc(m.body||"Текст письма отсутствует.")}</div>${btn("mail-task","Создать задание","plus","minor",{id:m.id})}</div>`:""}</div>`}).join("");
    return mast("Почта","Входящие ИСУ и учебной почты",btn("isu-login","Войти в ИСУ","compass","minor")+iconBtn("mail-check","Проверить почту","refresh"))+`<div class="panel" style="margin-bottom:15px"><div class="settings-list">${switchSetting("mail_on","Пересылать новые письма в Telegram",svc.detail||"Выключенную пересылку можно включить в любой момент.")}</div></div><section class="panel">${section("Входящие",`<span class="meta">${state.mail.length} ${plural(state.mail.length,"письмо","письма","писем")}</span>`)}${rows||empty("Новых писем пока нет",svc.ok?"Здесь появятся письма из подключённого ящика.":"Проверь настройки почтового ящика и соединение в профиле.",tabLink("profile","Перейти в профиль"))}</section>`;
  }
  function switchSetting(key,title,desc=""){
    return `<label class="setting"><span><b>${esc(title)}</b>${desc?`<small>${esc(desc)}</small>`:""}</span><input class="switch" type="checkbox" data-setting="${key}" ${state.settings[key]?"checked":""} aria-label="${esc(title)}"></label>`;
  }
  function campusFields(){
    const buildings=new Set(state.campuses||Object.keys(state.settings.campus_minutes||{}));
    for(const day of state.days){
      if(day.stale)continue;
      for(const lesson of day.lessons||[]){
        const building=String(lesson.building||"").trim();
        if(building&&!/онлайн|дистанц|online|виртуальн|remote/i.test([lesson.format,lesson.work_type,building].join(" ")))buildings.add(building);
      }
    }
    const overrides=state.settings.campus_minutes||{};
    const defaultMinutes=Number(state.settings.travel_minutes)||35;
    return [...buildings].sort((a,b)=>a.localeCompare(b,"ru")).map(building=>{
      const value=Object.hasOwn(overrides,building)?overrides[building]:"";
      return `<label class="setting campus-setting"><span><b>${esc(building)}</b><small>Пустое поле · общее время ${defaultMinutes} мин</small></span><input type="number" min="1" max="240" step="1" data-campus="${esc(building)}" placeholder="${defaultMinutes}" value="${esc(value)}" aria-label="Время в пути в минутах — ${esc(building)}"></label>`;
    }).join("");
  }
  let profilePage="wake";
  function ruleRow(start="",wake="",index=0){
    return `<div class="rule-row"><b>К ${index+1}-й паре</b><label>Начало<input type="time" required name="pair_start" value="${esc(start)}"></label><label>Подъём<input type="time" required name="pair_wake" value="${esc(wake)}"></label>${iconBtn("remove-rule","Удалить правило","close")}</div>`;
  }
  function ruleEditor(){
    const entries=(state.settings.wake_rules??"08:10=06:20, 09:50=08:30").split(",").filter(v=>v.trim());
    modal("Время по парам",`<form class="form" data-form="wake-rules"><div class="rule-list">${entries.map((v,i)=>ruleRow(...v.trim().split("="),i)).join("")}</div>
    ${btn("add-rule","Добавить пару","plus","minor")}<p class="meta">Правило действует для любого формата пары. Для остальных занятий учитываются дорога и сборы или время до онлайн-пары.</p><button class="btn primary">Сохранить</button></form>`);
  }
  function profile(){
    const s=state.settings,person=state.profile||{},services=state.services;
    const status=[["itmo","my.itmo","compass"],["isu","Входящие ИСУ","message"],["mail","Учебная почта","mail"],["telegram","Telegram","send"]].map(([k,label,icon])=>{
      const v=services[k]||{},detail=v.detail||v.details||v.error||(v.ok?"Подключено":"Ожидает подключения");return `<div class="status-line"><span class="service-icon">${ico(icon)}</span><div><b>${label}</b><small>${esc(detail)}</small></div><i class="status-led ${v.ok?"ok":""}" aria-label="${v.ok?"Подключено":"Нет подтверждения"}"></i></div>`;
    }).join("");
    const variants=Object.entries(themes).map(([k,v])=>`<button type="button" class="theme ${(s.theme||"paper")===k?"selected":""}" aria-pressed="${(s.theme||"paper")===k}" data-action="theme" data-value="${k}"><i class="swatch" aria-hidden="true">${v.slice(1).map(c=>`<i style="background:${c}"></i>`).join("")}</i><span>${v[0]}</span></button>`).join("");
    const interval=[0,1,5,15,30].map(n=>`<option value="${n}" ${Number(s.interval)===n?"selected":""}>${n?n+" мин":"Выключено"}</option>`).join("");
    const groups=[
      ["wake","Будильник и дорога",`${switchSetting("wake_on","Связать подъём с расписанием",state.wake_status||"Телефон не привязан")}${[["wake_prep","Сборы перед очной парой",40],["wake_online","Подъём до онлайн-пары",20]].map(([key,label,n])=>`<label class="setting"><span><b>${label}</b><small>В минутах</small></span><input type="number" min="0" max="240" required data-setting="${key}" value="${esc(s[key]??n)}"></label>`).join("")}${btn("wake-rules","Время по парам","clock","minor")}<div class="btn-row">${btn("wake-pair","Привязать будильник телефона к расписанию","clock","minor")}${btn("wake-revoke","Отозвать доступ","close","minor")}</div>${switchSetting("wake_free_off","В свободный день предложить выключить первый будильник")}${switchSetting("travel_on","Пора выходить","Напоминание перед первой очной парой.")}<label class="setting"><span><b>Общее время дороги</b><small>В минутах, для всех корпусов</small></span><input min="1" max="240" step="1" type="number" data-setting="travel_minutes" value="${esc(s.travel_minutes??35)}" required></label>${campusFields()}`],
      ["alerts","Уведомления",`${switchSetting("quiet_on","Тихие часы","Фоновые уведомления придут сводкой в конце интервала по Москве.")}${[["quiet_start","Начало тишины","23:00"],["quiet_end","Конец тишины","07:00"]].map(([key,label,fallback])=>`<label class="setting"><b>${label}</b><input type="time" data-setting="${key}" value="${esc(s[key]||fallback)}" required></label>`).join("")}${switchSetting("quiet_first","Изменения первой пары сразу")}${switchSetting("morning_on","Утреннее расписание")}<label class="setting"><span><b>Время рассылки</b><small>По Москве</small></span><input data-setting="morning_time" type="time" required value="${esc(s.morning_time||"07:30")}"></label>${switchSetting("weekly_on","Недельная сводка")}${switchSetting("mail_on","Пересылка почты")}
        ${[["notify_isu","Входящие ИСУ"],["notify_imap","Входящие IMAP"],["notify_bars","Изменения баллов БаРС"],["notify_schedule","Переносы и отмены занятий"],["notify_due","Дедлайны"]].map(([k,v])=>switchSetting(k,v)).join("")}`],
      ["accounts","Аккаунты и синхронизация",`<div class="service-list">${status}</div><div class="btn-row">${btn("check-services","Проверить связь","refresh","minor")}${btn("itmo-login","Войти в my.itmo","compass","minor")}${btn("isu-login","Войти в ИСУ","mail","minor")}${state.outlook_available?btn("outlook-login","Войти в Microsoft 365","mail","minor"):""}</div><label class="setting"><span><b>Проверять изменения</b><small>На ближайшие семь дней</small></span><select data-setting="interval">${interval}</select></label>`],
      ["themes","Оформление",`<div class="themes">${variants}</div>`]
    ];
    const active=groups.find(([id])=>id===profilePage)||groups[0];
    return mast("Профиль",person.isu?"ИСУ "+person.isu:"Личный кабинет")+
      `<section class="panel person profile-person"><span class="avatar-box">${esc(initials(person.name))}</span><h2>${esc(person.name||"ИТМО ID")}</h2>${btn("bars-check","Баллы БаРС","file","minor")}</section>
      <div class="preferences"><nav aria-label="Разделы профиля">${groups.map(([id,title])=>`<button data-action="profile-page" data-value="${id}" aria-pressed="${active[0]===id}">${title}</button>`).join("")}</nav><section class="panel">${section(active[1])}<div class="settings-list">${active[2]}</div></section></div>`;

  }
  function render(){shell();main.innerHTML=({today,week,tasks,mail,profile})[tab]()}
  function go(next){if(!Object.hasOwn(names,next)||!state)return;tab=next;const dest="#"+next;if(location.hash!==dest)history.replaceState(null,"",dest);render();window.scrollTo({top:0,behavior:"instant"})}
  function editTask(draft={}){
    const existing=draft.id!=null;
    const cats=[...new Set([...state.categories,draft.category||"Учёба"])];
    const due=(draft.due||state.today+" 23:59").replace("T"," ").split(" ");
    const stepsInput=existing?"":`<label>Подзадачи <small class="muted">Каждый шаг с новой строки</small><textarea name="steps" rows="2" maxlength="4000" style="min-height:65px">${(draft.steps||[]).map(step=>esc(typeof step==="string"?step:step.title)).join("\n")}</textarea></label>`;
    const leads=[[-1,"Без напоминания"],[0,"В момент срока"],[15,"За 15 минут"],[60,"За час"],[1440,"За сутки"]];
    modal(existing?"Изменить задание":"Новое задание",`<form class="form" data-form="task"${existing?attr("id",draft.id):""}><label>Что нужно сделать<input name="title" maxlength="160" value="${esc(draft.title||"")}" required></label><label>Категория<input name="category" list="categories" value="${esc(draft.category||"Учёба")}" maxlength="32" required><datalist id="categories">${cats.map(c=>`<option value="${esc(c)}"></option>`).join("")}</datalist></label><div class="pair"><label>Дата сдачи<input name="day" type="date" value="${esc(due[0])}" required></label><label>Время по Москве<input name="time" type="time" value="${esc((due[1]||"23:59").slice(0,5))}" required></label></div><label>Напомнить<select name="lead">${leads.map(([v,n])=>`<option value="${v}" ${Number(draft.lead??60)===v?"selected":""}>${n}</option>`).join("")}</select></label>${stepsInput}<div class="btn-row">${btn("close-modal","Отмена",null)}<button class="btn primary" type="submit">Сохранить</button></div></form>`);
  }
  function textTask(value=""){modal("Задание из сообщения",`<form class="form" data-form="text"><p class="desc">Вставь текст задания. Проверь название и срок в черновике перед сохранением.</p><label>Сообщение<textarea name="text" maxlength="4000" required>${esc(value)}</textarea></label><div class="btn-row">${btn("close-modal","Отмена",null)}<button class="btn primary">Подготовить черновик</button></div></form>`)}
  function confirmDelete(t){modal("Удалить задание?",`<p class="notice-text">${esc(t.title)}. Вместе с заданием будут удалены его подзадачи.</p><div class="btn-row">${btn("close-modal","Оставить",null)}${btn("confirm-delete","Удалить","trash","danger",{id:t.id})}</div>`)}
  function adjustAfterAdd(){filter="active";category="";go("tasks")}
  document.addEventListener("click",async event=>{
    const el=event.target.closest("[data-tab],[data-action]");if(!el)return;
    if(el.dataset.tab){event.preventDefault();go(el.dataset.tab);return}
    const {action,id,parent,value}=el.dataset;
    if(action==="close-modal"){dialog.close();return}
    if(!state||busy)return;const t=taskBy(id);
    switch(action){
    case "refresh":await perform("refresh",{},{message:s=>s.warning||(!s.services.itmo?.ok||s.days.find(d=>d.date===s.today)?.stale?"Свежесть расписания не подтверждена. Проверь подключение в профиле.":"Соединение с my.itmo подтверждено.")});break;
    case "check-services":await perform("check_services",{},{message:s=>"Подтверждённых подключений: "+Object.values(s.services).filter(v=>v?.ok).length+". Подробности в списке подключений."});break;
    case "profile-page":profilePage=value;render();break;
    case "wake-rules":ruleEditor();break;
    case "add-rule":{const list=dialog.querySelector(".rule-list");if(list.children.length<30)list.insertAdjacentHTML("beforeend",ruleRow("","",list.children.length));break}
    case "remove-rule":el.closest(".rule-row").remove();dialog.querySelectorAll(".rule-row>b").forEach((v,i)=>v.textContent="К "+(i+1)+"-й паре");break;
    case "wake-pair":{
      const reply=await perform("wake_pair");
      if(!reply?.pairing)break;
      const {url,origin,code}=reply.pairing;
      modal("Привязка телефона",`<p>Отсканируй QR обычной камерой HONOR. Код действует пять минут.</p><canvas class="pair-qr" aria-label="QR для привязки"></canvas><a class="btn primary" href="${esc(url)}" target="_blank" rel="noreferrer">Открыть на этом телефоне</a><details><summary>Ввести вручную</summary><p>${esc(origin)}</p><code>${esc(code)}</code></details>`);
      showPairQR(dialog.querySelector("canvas"),url);
      break;
    }
    case "wake-revoke":await perform("wake_revoke");break;
    case "bars-check":await perform("bars_check",{},{long:true,title:"Баллы БаРС"});break;
    case "week-report":await perform("week_report",{},{long:true,title:"Недельная сводка"});break;
    case "mail-check":await perform("mail_check",{},{message:s=>s.services.mail?.ok||s.services.isu?.ok?"Доступные входящие показаны в списке.":"Почтовое подключение не подтверждено. Открой профиль."});break;
    case "outlook-login":{const r=await perform("outlook_login");if(r?.notice)modal("Microsoft 365",`<p>${esc(r.notice)}</p><a class="btn primary" href="https://microsoft.com/devicelogin" target="_blank" rel="noreferrer">Открыть Microsoft</a>`);break}
    case "isu-login":await privateLogin("isu");break;
    case "itmo-login":await privateLogin("itmo");break;
    case "select-day":selectedDay=el.dataset.date;render();break;
    case "task-filter":filter=value;render();break;
    case "open-task":filter="all";category="";expandedTask=id;go("tasks");break;
    case "expand-task":expandedTask=idsame(expandedTask,id)?"":id;render();break;
    case "expand-mail":expandedMail=idsame(expandedMail,id)?"":id;render();break;
    case "new-task":editTask();break;
    case "edit-task":if(t)editTask(t);break;
    case "delete-task":if(t)confirmDelete(t);break;
    case "confirm-delete":await perform("task_delete",{id:Number(id)},{close:true,message:"Задание удалено."});break;
    case "task-done":if(t)await perform("task_done",{id:t.id,done:!t.done},{message:t.done?"Задание возвращено в работу.":"Выполнено. Вернуть в работу можно в разделе «Готовые»."});break;
    case "step-done":{const st=taskBy(parent)?.steps?.find(x=>idsame(x.id,id));if(st)await perform("step_done",{task_id:Number(parent),id:st.id,done:!st.done});break}
    case "delete-step":await perform("step_delete",{task_id:Number(parent),id:Number(id)},{message:"Подзадача удалена."});break;
    case "from-text":textTask();break;
    case "mail-task":{const m=state.mail.find(x=>idsame(x.id,id));if(m)textTask([m.subject,m.body].filter(Boolean).join("\n").slice(0,4000));break}
    case "theme":await perform("settings",{theme:value},{message:"Оформление сохранено."});break;
    }
  });
  document.addEventListener("change",async e=>{
    const el=e.target;if(el.dataset.control==="category"){category=el.value;render();return}
    if(el.hasAttribute("data-campus")&&state){
      if(!el.reportValidity())return;
      const overrides=Object.assign(Object.create(null),state.settings.campus_minutes||{});
      if(el.value==="")delete overrides[el.dataset.campus];
      else overrides[el.dataset.campus]=el.valueAsNumber;
      if(!await perform("settings",{campus_minutes:overrides},{message:"Время дороги сохранено."}))render();
      return;
    }
    const key=el.dataset.setting;if(!key||!state)return;
    if(!el.checkValidity()){el.reportValidity();return}
    const value=el.type==="checkbox"?el.checked:["interval","travel_minutes","wake_prep","wake_online"].includes(key)?Number(el.value):el.value;
    const updated=await perform("settings",{[key]:value},{message:"Настройки сохранены."});if(!updated)render();
  });
  document.addEventListener("submit",async e=>{
    const form=e.target;if(!form.dataset.form)return;e.preventDefault();if(busy||!form.reportValidity())return;
    const data=new FormData(form);const str=k=>String(data.get(k)||"").trim();
    switch(form.dataset.form){
    case "wake-rules":{
      const starts=data.getAll("pair_start"),wakes=data.getAll("pair_wake");
      if(new Set(starts).size!==starts.length || wakes.some((v,i)=>v>=starts[i])){notify("Время начала должно быть уникальным, а подъём — раньше пары.");break}
      await perform("settings",{wake_rules:starts.map((v,i)=>v+"="+wakes[i]).join(", ")},{close:true,message:"Правила подъёма сохранены."});break;
    }
    case "step":await perform("step_add",{task_id:Number(form.dataset.id),title:str("step")},{message:"Подзадача добавлена."});break;
    case "task":{
      const p={title:str("title"),category:str("category"),due:str("day")+" "+str("time"),lead:Number(str("lead"))};
      if(form.dataset.id)p.id=Number(form.dataset.id);
      else p.steps=str("steps").split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
      const result=await perform("task_save",p,{close:true,message:"Задание сохранено."});if(result&&!p.id)adjustAfterAdd();break}
    case "text":{const draft=await perform("task_from_text",{text:str("text")});if(draft)editTask(draft);break}
    }
  });
  window.addEventListener("hashchange",()=>{if(state&&Object.hasOwn(names,location.hash.slice(1)))go(location.hash.slice(1))});
  dialog.addEventListener("click",e=>{if(e.target===dialog){const box=dialog.getBoundingClientRect();if(e.clientX<box.left||e.clientX>box.right||e.clientY<box.top||e.clientY>box.bottom)dialog.close()}});
  async function start(){
    if(demo){try{const saved=JSON.parse(localStorage.getItem("para.demo.v2"));if(saved?.today&&Array.isArray(saved.tasks))state=normalize(saved)}catch{}state=state||demoModel();render();return}
    shell();
    try{
      if(!window.Telegram?.WebApp){
        await new Promise((resolve,reject)=>{const script=document.createElement("script");script.src="https://telegram.org/js/telegram-web-app.js";script.onload=resolve;script.onerror=()=>reject(Error("Не удалось загрузить модуль Telegram."));document.head.append(script)});
      }
      tg=window.Telegram?.WebApp;initData=tg?.initData||"";tg?.ready();tg?.expand();
      if(!initData)throw Error("Для доступа к личным данным открой приложение кнопкой в чате со своим ботом.");
      state=normalize(await request("state",{}));render();watchCheck();
      const login=new URLSearchParams(location.search).get("login");
      if(["itmo","isu"].includes(login))await privateLogin(login);
    }catch(e){
      main.innerHTML=mast("Мой кампус","Личное приложение студента ИТМО")+`<section class="panel">${empty("Личный кабинет закрыт",e?.message||"Не удалось открыть приложение.",'<a class="btn minor" href="?demo=1">Посмотреть демоверсию</a>')}</section>`;
    }
  }
  start();
})();
