'use strict';
(() => {
  const $ = selector => document.querySelector(selector);
  const icons = name => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
  // Labels and defaults are transcribed from resources/tasks.json and the UI contract.
  const tasks = [
    { id:'survival',name:'生存演习',english:'SURVIVAL PRACTICE',icon:'shield',hint:'满分后领取奖励',steps:['读取当前积分与重置次数','按所选等级演示挑战','演示领奖并返回主页'] },
    { id:'strong',name:'强者降临',english:'STRONG ENEMY',icon:'sword',hint:'按所选难度挑战',steps:['读取普通奖励次数','演示所选难度战斗','演示胜利确认与返回'] },
    { id:'hosting',name:'游戏内托管',english:'IN-GAME HOSTING',icon:'home',hint:'结束判断待实机验收',steps:['保留游戏内已有勾选','演示启动托管','演示结束，真实收尾待验收'] },
    { id:'ranked',name:'排位战',english:'RANKED ARENA',icon:'flag',hint:'按范围与次数挑战',steps:['读取剩余次数与双方战力','演示匹配对手并挑战','演示结算确认与返回'] },
    { id:'wanted',name:'通缉任务',english:'WANTED MISSIONS',icon:'target',hint:'自动完成剩余通缉',steps:['演示进入通缉任务','演示自动完成与确认','演示剩余零次后返回'] },
    { id:'escort',name:'押镖（接取）',english:'ESCORT ACCEPTANCE',icon:'box',hint:'仅接取，交付待实施',steps:['查找所选等级的镖车','演示免费刷新与普通押送','演示已接取，交付待实施'] }
  ];
  const defaults = () => ({ selected:['survival','strong','ranked'],order:tasks.map(task=>task.id),rankedServer:'连服',rankedAll:true,rankedCount:1,tolerance:20,battleSeconds:900,difficulty:'阿修罗级',reset:true,survivalInitial:60,survivalGoal:220,grades:['SS','S','A','B','C'],counts:{SS:1,S:2,A:2,B:3,C:5},hostingMinutes:90,escortGrade:'SS',escortRefreshLimit:4 });
  const storageKey='naruto-mission-desk-preview-v1';
  let config=defaults(), focused='ranked', tab='common', phase='idle', timer=null, queue=[], cursor=0, step=0, completed=0, events=[], dirty=false;
  let statuses={};
  const isLocked=()=>phase==='running'||phase==='paused';
  let restored=false;
  try {
    const saved=JSON.parse(localStorage.getItem(storageKey)||'null');
    if(saved && Array.isArray(saved.order) && saved.order.length===tasks.length && new Set(saved.order).size===tasks.length && saved.order.every(id=>tasks.some(task=>task.id===id)) && Array.isArray(saved.selected) && saved.selected.every(id=>saved.order.includes(id))) {
      config={...defaults(),...saved};
      if(!Array.isArray(config.grades)||!config.counts) config=defaults();
      else restored=true;
    }
  } catch { /* A private or unavailable store must not prevent the prototype opening. */ }
  const two=value=>String(value).padStart(2,'0');
  const date=new Date();
  $('#year').textContent=date.getFullYear();$('#month').textContent=two(date.getMonth()+1);$('#day').textContent=two(date.getDate());$('#weekday').textContent=new Intl.DateTimeFormat('zh-CN',{weekday:'long'}).format(date);
  const reduced=()=>matchMedia('(prefers-reduced-motion: reduce)').matches;
  function feedback(message){$('#global-feedback').textContent=message;}
  function markDirty(){dirty=true;$('#save-state').textContent='未保存';$('#save-state').classList.add('dirty');$('#field-feedback').textContent='';}
  function renderQueue(){
    const list=$('#task-list');list.replaceChildren();
    config.order.forEach((id,index)=>{
      const task=tasks.find(item=>item.id===id), selected=config.selected.includes(id);
      const status=statuses[id]||{label:selected?'待执行':'未勾选',type:''};
      const row=document.createElement('div');row.className=`task-row${focused===id?' is-focused':''}`;row.dataset.task=id;
      row.innerHTML=`<label class="task-select-label"><input type="checkbox" aria-label="选择${task.name}" ${selected?'checked':''} ${isLocked()?'disabled':''}></label><button class="task-focus" aria-label="设置${task.name}" aria-pressed="${focused===id}">${icons(task.icon)}<span><strong>${task.name}${focused===id?'<span class="editing-tag">编辑中</span>':''}</strong><small>${task.hint}</small></span></button><div class="row-side"><span class="task-state ${status.type}"></span><button class="parameter-entry" aria-label="编辑${task.name}参数">参数 ↗</button></div>${focused===id?`<div class="row-order"><button id="move-up" class="row-move" aria-label="上移${task.name}">${icons('up')}</button><button id="move-down" class="row-move" aria-label="下移${task.name}">${icons('down')}</button></div>`:''}`;
      row.querySelector('.task-state').textContent=status.label;
      row.querySelector('input').addEventListener('change',event=>{
        if(isLocked())return;
        if(event.target.checked)config.selected.push(id);else config.selected=config.selected.filter(value=>value!==id);
        statuses={};phase='idle';completed=0;markDirty();renderQueue();renderControls();feedback('');
      });
      const focusTask=()=>{
        focused=id;renderQueue();renderFields();
        if(isLocked())setPanelCollapsed('settings-panel',false);
        if(innerWidth<=760) $('.settings-panel').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});
      };
      row.querySelector('.task-focus').addEventListener('click',focusTask);
      row.querySelector('.parameter-entry').addEventListener('click',focusTask);
      row.querySelector('#move-up')?.addEventListener('click',()=>moveTask(-1));
      row.querySelector('#move-down')?.addEventListener('click',()=>moveTask(1));
      list.append(row);
    });
    $('#selection-count').textContent=two(config.selected.length);
    $('#move-up').disabled=isLocked()||config.order.indexOf(focused)===0;
    $('#move-down').disabled=isLocked()||config.order.indexOf(focused)===config.order.length-1;
  }
  const numField=(label,key,min,max,suffix,hint='')=>`<div class="field-group"><label for="field-${key}">${label}</label><div class="number-field"><input id="field-${key}" type="number" min="${min}" max="${max}" step="1" data-key="${key}" value="${config[key]}" aria-describedby="hint-${key}"><span>${suffix}</span></div><p class="field-hint" id="hint-${key}">${hint||`范围 ${min}–${max} ${suffix}`}</p><p class="field-error" id="error-${key}" aria-live="polite"></p></div>`;
  const segment=(label,key,values)=>`<fieldset class="field-group"><legend>${label}</legend><div class="segmented">${values.map(value=>`<label><input type="radio" name="${key}" value="${value}" data-key="${key}" ${config[key]===value?'checked':''}><span>${value}</span></label>`).join('')}</div></fieldset>`;
  const note=text=>`<p class="scope-note">${icons('alert')}<span>${text}</span></p>`;
  function renderFields(){
    const task=tasks.find(item=>item.id===focused);
    $('#task-title').textContent=`${task.name} · 参数`;$('#task-subtitle').textContent=task.english;$('#task-order').textContent='';$('#task-symbol').innerHTML=icons(task.icon);
    document.querySelectorAll('[data-tab]').forEach(button=>{const active=button.dataset.tab===tab;button.setAttribute('aria-selected',active);button.tabIndex=active?0:-1;});
    const form=$('#parameter-form');form.setAttribute('aria-labelledby',`tab-${tab}`);
    let html='';
    if(focused==='ranked'){
      if(tab==='common')html=segment('挑战范围','rankedServer',['本服','连服'])+`<div class="field-group"><label class="checkbox-line"><input type="checkbox" id="all-ranked" data-key="rankedAll" ${config.rankedAll?'checked':''}>用完剩余挑战次数</label><div class="number-field"><input type="number" id="field-rankedCount" aria-label="最多挑战场数" data-key="rankedCount" min="1" max="20" value="${config.rankedCount}" ${config.rankedAll?'disabled':''}><span>场上限</span></div><p class="field-hint">${config.rankedAll?'以游戏剩余次数为准；本网页不读取实际次数。':'最多 1–20 场；游戏次数不足时以实际为准。'}</p><p class="field-error" id="error-rankedCount" aria-live="polite"></p></div>`+numField('匹配战力差','tolerance',0,100,'％','优先匹配阈值内对手；无匹配时随机选择。');
      else html=numField('单场战斗超时','battleSeconds',30,3600,'秒','超过等待时间即停止，不自动重放挑战。')+note('联服切换、战败刷新及结算返回的部分分支仍待实机验收。网页只演示状态，不证明游戏流程通过。');
    }else if(focused==='survival'){
      if(tab==='common')html=`<label class="checkbox-line"><input type="checkbox" data-key="reset" ${config.reset?'checked':''}>剩余免费重置次数为 1 时重置</label><div class="dual-field">${numField('估算起始积分','survivalInitial',0,1000,'分')}${numField('估算满分目标','survivalGoal',1,1000,'分')}</div><p class="task-brief">按 SS → S → A → B → C 挑战。实际积分满分后领奖；这里的积分只用于估算。</p>`;
      else html=`<fieldset class="field-group"><legend>挑战等级与每级最多场数</legend><div class="grade-grid">${['SS','S','A','B','C'].map(grade=>`<label><input type="checkbox" data-grade="${grade}" ${config.grades.includes(grade)?'checked':''}>${grade}</label>`).join('')}</div><div class="grade-counts">${['SS','S','A','B','C'].map(grade=>`<input type="number" aria-label="${grade}级最多场数" data-count="${grade}" min="1" max="${grade==='SS'?1:30}" value="${config.counts[grade]}">`).join('')}</div><p class="field-hint">只挑战勾选等级，计划用尽但未满分时停止。</p></fieldset>`;
    }else if(focused==='strong'){
      html=tab==='common'?segment('挑战难度','difficulty',['天级','夜叉级','阿修罗级'])+`<p class="task-brief">普通奖励次数为 0 时跳过。否则挑战一场，确认胜利后处理结算与分数并返回主页。</p>`:numField('单场战斗超时','battleSeconds',30,3600,'秒');
    }else if(focused==='hosting'){
      html=tab==='common'?`<p class="task-brief">保留游戏内已有托管任务选择，启动已有托管。</p>`+note('可靠的本轮结束判断与完整收尾仍待实施或验收，不能据此认为托管已完成。'):numField('托管超时','hostingMinutes',1,240,'分钟');
    }else if(focused==='wanted'){
      html=`<p class="task-brief">苦无活动 → 日常活动 → 通缉任务 → 参与 → 自动完成。剩余次数连续两帧为 0 后返回主页。</p>`+(tab==='advanced'?`<p class="field-hint">每个页面最多等待 30 秒；全部通缉最多等待 30 分钟，暂停不计时。仅支持本地后台模式。</p>`:'');
    }else if(focused==='escort'){
      html=tab==='common'?segment('接取等级','escortGrade',['SS','S'])+note('当前只接取一次，交付与每日三次循环待实施。不购买次数、不付费刷新、不使用保险押送。'):numField('最多免费刷新次数','escortRefreshLimit',0,20,'次');
    }
    form.innerHTML=html;
    form.querySelectorAll('input,select').forEach(input=>{
      if(isLocked())input.disabled=true;
      const change=()=>{
        const key=input.dataset.key;
        if(key)config[key]=input.type==='checkbox'?input.checked:input.type==='number'?(input.value===''?null:Number(input.value)):input.value;
        if(input.dataset.grade){const grade=input.dataset.grade;config.grades=input.checked?[...config.grades,grade]:config.grades.filter(item=>item!==grade);}
        if(input.dataset.count)config.counts[input.dataset.count]=input.value===''?null:Number(input.value);
        markDirty();
        validateField(input);
        if(key==='rankedAll')renderFields();
      };
      input.addEventListener(input.type==='number'?'input':'change',change);
    });
    $('#save').disabled=isLocked();
  }
  function validateField(input){
    if(input.type!=='number'||input.disabled)return true;
    const valid=input.value!==''&&input.validity.valid;
    input.setAttribute('aria-invalid',String(!valid));
    input.closest('.number-field')?.classList.toggle('invalid',!valid);
    const error=document.getElementById(`error-${input.dataset.key}`);
    if(error)error.textContent=valid?'':`请输入 ${input.min}–${input.max} 之间的整数`;
    return valid;
  }
  function validateConfig(){
    if(config.selected.length===0)return '请至少勾选一项任务。';
    const ranges={battleSeconds:[30,3600]};
    if(config.selected.includes('ranked')){ranges.tolerance=[0,100];if(!config.rankedAll)ranges.rankedCount=[1,20];}
    if(config.selected.includes('hosting'))ranges.hostingMinutes=[1,240];
    if(config.selected.includes('escort'))ranges.escortRefreshLimit=[0,20];
    for(const [key,[min,max]] of Object.entries(ranges))if(!Number.isInteger(config[key])||config[key]<min||config[key]>max)return '存在无效参数，请检查数值范围后再开始。';
    if(config.selected.includes('survival')){
      if(!Number.isInteger(config.survivalInitial)||!Number.isInteger(config.survivalGoal)||config.survivalInitial<0||config.survivalGoal<1||config.survivalGoal>1000||config.survivalInitial>config.survivalGoal)return '生存积分应为整数，起点不高于目标，目标范围 1–1000。';
      if(!config.grades.length||config.grades.some(grade=>!Number.isInteger(config.counts[grade])||config.counts[grade]<1||config.counts[grade]>(grade==='SS'?1:30)))return '生存演习需勾选至少一个等级，并填写有效的场数上限。';
    }
    return '';
  }
  function renderControls(){
    const locked=isLocked();document.body.classList.toggle('locked',locked);
    if(!locked){setPanelCollapsed('queue-panel',false);setPanelCollapsed('settings-panel',false);}
    $('#start').disabled=locked;$('#pause').disabled=!locked;$('#stop').disabled=!locked;$('#simulate-error').disabled=phase!=='running';
    $('#pause span').textContent=phase==='paused'?'继续':'暂停';
    $('#pause use').setAttribute('href',phase==='paused'?'#i-play':'#i-pause');
    $('#select-all').disabled=locked;$('#select-none').disabled=locked;
    $('#save').disabled=locked;
    const total=locked||['done','stopped','failed'].includes(phase)?queue.length:config.selected.length;
    $('#completed-count').textContent=two(completed);$('#run-total').textContent=two(total);
    const progress=total?Math.round(completed/total*100):0;$('#run-progress').style.width=`${progress}%`;$('.progress-track').setAttribute('aria-valuenow',progress);
    const labels={idle:'准备就绪',running:'演示运行中',paused:'演示已暂停',done:'队列演示结束',stopped:'已停止演示',failed:'演示已中止'};
    $('#run-label').textContent=labels[phase];$('#mobile-state').textContent=labels[phase];$('#run-dot').classList.toggle('running-pulse',phase==='running');$('#run-dot').style.background=['failed','running','stopped'].includes(phase)?'var(--accent)':'var(--green)';
    $('#start span').textContent=['done','stopped','failed'].includes(phase)?'重新演示':'开始演示';
    renderQueue();
  }
  function log(title,detail,type='info'){
    const event={time:new Intl.DateTimeFormat('zh-CN',{hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date()),title,detail,type};events.push(event);
    $('#empty-events').hidden=true;$('#empty-events').style.display='none';
    const item=document.createElement('li');item.className=`event-item ${type}`;
    const time=document.createElement('time');time.textContent=event.time;
    const heading=document.createElement('strong');heading.textContent=title;
    const text=document.createElement('p');text.textContent=detail;item.append(time,heading,text);$('#event-list').append(item);
    if($('#follow').checked)$('#event-scroll').scrollTop=$('#event-scroll').scrollHeight;
  }
  function setStep(title,detail){$('#current-step').textContent=title;$('#mobile-step').textContent=title;$('#current-detail').textContent=detail;$('#run-message').textContent=title;}
  function schedule(){clearTimeout(timer);timer=setTimeout(advance,1400);}
  function advance(){
    if(phase!=='running')return;
    const task=tasks.find(item=>item.id===queue[cursor]);
    if(!task)return finish();
    if(step<task.steps.length){
      statuses[task.id]={label:'演示中',type:'running'};
      const title=task.steps[step++];setStep(`${task.name} · ${title}`,'演示数据，不读取游戏画面或实际次数。');log(task.name,title);renderControls();schedule();
    }else{
      const partial=task.id==='escort'||task.id==='hosting';
      statuses[task.id]={label:task.id==='escort'?'接取演示':task.id==='hosting'?'收尾待验收':'已演示',type:partial?'accepted':'done'};completed++;cursor++;step=0;
      log(`${task.name} · 演示结束`,task.id==='escort'?'仅接取；真实交付待实施。':task.id==='hosting'?'托管真实结束判断和收尾未验收。':'仅表示网页演示结束，不代表游戏任务完成。');renderControls();
      if(cursor===queue.length)finish();else schedule();
    }
  }
  function finish(){clearTimeout(timer);phase='done';setStep('所选队列演示结束','以上均为演示事件，未向游戏发送任何操作。');log('队列演示结束','游戏实际任务状态未改变。');renderControls();renderFields();}
  $('#start').addEventListener('click',()=>{
    if(isLocked())return;
    const error=validateConfig();document.querySelectorAll('#parameter-form input').forEach(validateField);
    if(error){feedback(error);return;}
    feedback('');clearTimeout(timer);queue=config.order.filter(id=>config.selected.includes(id));cursor=0;step=0;completed=0;statuses={};phase='running';
    events=[];$('#event-list').replaceChildren();setStep('启动校准 · 演示','实际助手会先校准 1920×1015 游戏区域；此处不操作窗口。');log('启动校准 · 演示',`已选择 ${queue.length} 项，按队列顺序演示。`);renderControls();renderFields();schedule();
    if(innerWidth<=760){setPanelCollapsed('queue-panel',true);setPanelCollapsed('settings-panel',true);$('#activity').scrollIntoView({behavior:reduced()?'instant':'smooth',block:'start'});}
  });
  $('#pause').addEventListener('click',()=>{
    if(phase==='running'){clearTimeout(timer);phase='paused';setStep('已暂停演示','演示计时已暂停，继续后从当前步骤恢复。');log('用户暂停','网页演示已暂停。');}
    else if(phase==='paused'){phase='running';setStep('继续演示','从当前演示步骤恢复，不重放已完成步骤。');log('用户继续','恢复演示计时。');schedule();}
    renderControls();
  });
  $('#stop').addEventListener('click',()=>{
    if(!isLocked())return;clearTimeout(timer);phase='stopped';const id=queue[cursor];if(id)statuses[id]={label:'已停止',type:'failed'};setStep('用户停止演示','未演示的任务保持未执行；不会自动重启。');log('用户停止','停止当前演示，剩余队列未执行。');renderControls();renderFields();
  });
  $('#simulate-error').addEventListener('click',()=>{
    if(phase!=='running')return;clearTimeout(timer);phase='failed';const id=queue[cursor];if(id)statuses[id]={label:'识别不确定',type:'failed'};setStep('识别不确定，停止演示','这是手动模拟的异常，不会继续执行后续任务。');log('模拟识别失败','保留异常状态；不重放挑战，不执行剩余队列。','error');renderControls();renderFields();
  });
  $('#follow').addEventListener('change',()=>{if($('#follow').checked)$('#event-scroll').scrollTop=$('#event-scroll').scrollHeight;});
  $('#select-all').addEventListener('click',()=>{if(isLocked())return;config.selected=[...config.order];statuses={};completed=0;phase='idle';markDirty();renderControls();});
  $('#select-none').addEventListener('click',()=>{if(isLocked())return;config.selected=[];statuses={};completed=0;phase='idle';markDirty();renderControls();});
  function moveTask(offset){if(isLocked())return;const index=config.order.indexOf(focused),target=index+offset;if(target<0||target>=config.order.length)return;[config.order[index],config.order[target]]=[config.order[target],config.order[index]];markDirty();renderQueue();renderFields();}
  function setPanelCollapsed(panel,collapsed){
    $(`.${panel}`).classList.toggle('is-collapsed',collapsed);
    const button=$(`[data-panel="${panel}"]`);button.setAttribute('aria-expanded',String(!collapsed));button.textContent=collapsed?'展开':'收起';
  }
  document.querySelectorAll('[data-panel]').forEach(button=>button.addEventListener('click',()=>setPanelCollapsed(button.dataset.panel,button.getAttribute('aria-expanded')==='true')));
  document.querySelectorAll('[data-tab]').forEach(button=>{
    button.addEventListener('click',()=>{tab=button.dataset.tab;renderFields();});
    button.addEventListener('keydown',event=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(event.key)){event.preventDefault();tab=event.key==='Home'?'common':event.key==='End'?'advanced':tab==='common'?'advanced':'common';renderFields();$(`#tab-${tab}`).focus();}});
  });
  $('#parameter-form').addEventListener('submit',event=>event.preventDefault());
  $('#save').addEventListener('click',()=>{
    if(isLocked())return;
    const error=validateConfig();document.querySelectorAll('#parameter-form input').forEach(validateField);
    if(error){$('#field-feedback').textContent=error;return;}
    try{localStorage.setItem(storageKey,JSON.stringify(config));dirty=false;$('#save-state').textContent='已保存';$('#save-state').classList.remove('dirty');$('#field-feedback').textContent='已保存，仅此浏览器可用';}
    catch{$('#field-feedback').textContent='浏览器保存失败，当前参数仍保留在页面内。';}
  });
  $('#export-log').addEventListener('click',()=>{
    if(!events.length){feedback('暂无演示日志。先开始一次演示后再查看全文。');return;}
    const content='火影忍者online助手 · 网页演示日志（非真实游戏结果）\n'+events.map(event=>`[${event.time}] ${event.title} — ${event.detail}`).join('\n');
    $('#dialog-title').textContent='演示日志全文';
    $('#dialog-content').innerHTML='<p>仅包含本页演示事件，可选中文本后复制保存。</p><textarea id="log-fulltext" class="log-fulltext" aria-label="演示日志全文，可选中复制" readonly></textarea>';
    $('#log-fulltext').value=content;dialog.showModal();$('#log-fulltext').focus();$('#log-fulltext').select();
  });
  const dialog=$('#info-dialog');
  function openInfo(kind){
    const guide=kind==='help';$('#dialog-title').textContent=guide?'把日常，安排明白。':'网页预览与真实助手';
    $('#dialog-content').innerHTML=guide?'<ol><li>勾选要演示的任务，点击任务名称查看参数。</li><li>常规／高级设置可切换，数值越界时会提示。</li><li>点击“开始演示”，查看步骤、日志与任务状态；可暂停、继续或停止。</li><li>“模拟识别失败”展示遇到不确定结果时停止的状态。</li></ol><p>押镖仅接取，交付待实施；托管的可靠结束判断与收尾待实施或验收。所有运行事件都属于演示。</p>':'<p>这是独立的本地网页交互原型，未连接游戏窗口、OCR、Maa 流水线或桌面助手。</p><p>参数仅通过浏览器 localStorage 保存，不会读取或覆盖项目的 config.json、run.json。运行按钮只启动网页计时演示。</p><p>真实助手默认使用本地后台模式，游戏可遮挡但不能最小化。接入真实运行接口需另行设计与验收。</p>';
    dialog.showModal();
  }
  $('#help-open').addEventListener('click',()=>openInfo('help'));$('#connection-open').addEventListener('click',()=>openInfo('connection'));$('#dialog-close').addEventListener('click',()=>dialog.close());$('#dialog-ok').addEventListener('click',()=>dialog.close());
  document.querySelectorAll('nav a').forEach(link=>link.addEventListener('click',()=>{document.querySelectorAll('nav a').forEach(item=>item.classList.toggle('active',item===link));}));
  if(restored)$('#save-state').textContent='已载入本地设置';
  renderQueue();renderFields();renderControls();
})();
