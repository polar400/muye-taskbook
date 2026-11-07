import test from 'node:test';
import assert from 'node:assert/strict';
import {Resource} from './resource.mjs';
import {Tasker} from './tasker.mjs';
const data=()=>({format:'naruto-task-resource-v1',tasks:[{id:'a',label:'A',entry:'A'},{id:'b',label:'B',entry:'B'}],nodes:{A:{action:{type:'Custom',handler:'a'},next:['Done']},B:{action:{type:'Custom',handler:'b'},next:['Done']},Done:{action:{type:'DoNothing'},next:[]}}});
test('资源拒绝无效后继和重复ID',()=>{
 const d=data();d.nodes.A.next=['Missing'];assert.throws(()=>new Resource(d),/后继/);
 const e=data();e.tasks[1].id='a';assert.throws(()=>new Resource(e),/重复/);
});
test('队列在处理器失败时停止，发出失败事件',async()=>{
 const events=[];let ranB=false;
 const t=new Tasker({resource:new Resource(data()),handlers:{a:async()=>{throw Error('识别失败');},b:async()=>{ranB=true;}},io:{},checkpoint:async()=>{},emit:(...e)=>events.push(e)});
 await assert.rejects(t.run(['a','b'],{}),/识别失败/);assert.equal(ranB,false);
 assert.ok(events.some(e=>e[2]?.status==='failed'));
 assert.ok(!events.some(e=>e[0]==='task'&&e[2]?.status==='done'));
});
test('未知队列任务在首个操作前拒绝',async()=>{
 let ran=false;const t=new Tasker({resource:new Resource(data()),handlers:{a:async()=>{ran=true;}},io:{},checkpoint:async()=>{},emit:()=>{}});
 await assert.rejects(t.run(['a','unknown'],{}),/未知任务/);assert.equal(ran,false);
});
test('循环节点资源不会无限运行',async()=>{
 const d=data();d.nodes.A.next=['A'];const t=new Tasker({resource:new Resource(d),handlers:{a:async()=>{}},io:{},checkpoint:async()=>{},emit:()=>{}});
 await assert.rejects(t.run(['a'],{}),/无限循环/);
});
test('每项任务操作前先完成历史复盘',async()=>{
 const order=[];
 const t=new Tasker({resource:new Resource(data()),handlers:{a:async()=>order.push('run-a'),b:async()=>order.push('run-b')},io:{},checkpoint:async()=>{},emit:()=>{},beforeTask:async id=>order.push('review-'+id)});
 await t.run(['a','b'],{});
 assert.deepEqual(order,['review-a','run-a','review-b','run-b']);
});
