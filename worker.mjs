import fs from 'node:fs';
import readline from 'node:readline';
import {runFlow} from './flows.mjs';
import {Resource} from './core/resource.mjs';
import {Tasker} from './core/tasker.mjs';
import {createMidsceneAdapter} from './adapters/midscene.mjs';

let currentTask='worker', currentNode='未知';
const emit = (kind, message, extra={}) => {
  if(kind==='task'&&extra.status==='running') {currentTask=extra.id;currentNode='任务开始';}
  if(kind==='node') currentNode=extra.node;
  console.log('APP_EVENT '+JSON.stringify({kind,message,...extra}));
};
let paused=false, stopped=false;
readline.createInterface({input:process.stdin}).on('line',line=>{
  if(line==='pause') {paused=true;emit('log','将在当前识别／操作结束后暂停');}
  if(line==='resume') {paused=false;emit('log','继续运行');}
  if(line==='stop') stopped=true;
});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
async function checkpoint() { if(stopped) throw Error('已停止'); if(paused) emit('paused','已暂停'); while(paused&&!stopped) await sleep(250); if(stopped) throw Error('已停止'); }

async function main() {
  const cfg=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^\uFEFF/,''));
  const resource=Resource.load(new URL('./resources/tasks.json',import.meta.url));
  const names=Object.fromEntries(resource.tasks.map(t=>[t.id,t.label]));
  for(const id of cfg.tasks) resource.task(id);
  if(cfg.preview) {
    for(const id of cfg.tasks) {await checkpoint();emit('task',names[id]+'：流程预览',{id,status:'running'}); emit('log',JSON.stringify(cfg,null,2)); await sleep(300);emit('task',names[id]+'：预览完成，未操作游戏',{id,status:'preview'});}
    emit('done','流程预览完成，未操作游戏'); return;
  }
  const io=await createMidsceneAdapter({cfg,checkpoint,emit});
  await io.verify('当前可见的是360游戏大厅中的火影忍者online，游戏画面可识别。');
  await io.act('仅将鼠标移到火影忍者online主场景空白位置，不点击。');
  const handlers=Object.fromEntries(resource.tasks.map(t=>[t.id,(io,cfg)=>runFlow(t.id,io,cfg)]));
  const tasker=new Tasker({resource,handlers,io,checkpoint,emit});
  await tasker.run(cfg.tasks,cfg);
  emit('done','所选任务全部完成');
}
main().catch(e=>{
  const stack=String(e.stack||'');
  const frame=stack.match(/(?:at .*?\()?((?:file:\/\/\/|[A-Za-z]:[\\/])[^\n]+?):(\d+):(\d+)\)?/);
  const source=frame?{file:decodeURIComponent(frame[1]),line:Number(frame[2]),column:Number(frame[3])}:null;
  emit('error',String(e.message),{manual:stopped,failure:{taskId:currentTask,step:currentNode,exceptionType:e.name,traceback:stack,source,evidenceNote:'Midscene后端未提供本次失败截图，截图未知'}});
  process.exitCode=1;
}).finally(()=>process.exit(process.exitCode||0));
