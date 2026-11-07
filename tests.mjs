import test from 'node:test';
import assert from 'node:assert/strict';
import {runFlow,chooseOpponent,survivalPlan} from './flows.mjs';
const cfg={reset:true,difficulty:'阿修罗级',tolerance:20,battleSeconds:30,hostingMinutes:1};
function mock(answers) {
 const actions=[];
 return {actions,log:()=>{},act:async p=>actions.push(p),verify:async()=>{},until:async()=>{},wait:async()=>{},query:async()=>{if(!answers.length)throw Error('测试回答已耗尽');return answers.shift();}};
}

test('生存演习仅挑战选中的S，即使SS仍可挑战',async()=>{
 const attempts={SS:1,S:2};
 const io=mock([{points:160,goal:220,reset:0,claimed:false,attempts},{points:160,goal:220,attempts},{points:220,remaining:1},{points:220,goal:220}]);
 await runFlow('survival',io,{...cfg,survivalGrades:['S'],survivalCounts:{S:2}});
 assert.ok(io.actions.some(x=>x.includes('点击生存演习S难度')));
 assert.ok(!io.actions.some(x=>x.includes('点击生存演习SS难度')));
});

test('计划一场S后仍未满分，停止而不打未选等级',async()=>{
 const attempts={SS:1,S:2,A:2};
 const io=mock([{points:60,goal:220,reset:0,claimed:false,attempts},{points:60,goal:220,attempts},{points:120,remaining:1},{points:120,goal:220,attempts:{...attempts,S:1}}]);
 await assert.rejects(runFlow('survival',io,{...cfg,survivalGrades:['S'],survivalCounts:{S:1}}),/所选等级.*积分未满/);
 assert.equal(io.actions.filter(x=>x.includes('点击生存演习S难度')).length,1);
 assert.ok(!io.actions.some(x=>x.includes('点击一键领取')||x.includes('点击生存演习SS难度')||x.includes('点击生存演习A难度')));
});

test('空等级和超额SS计划在进入游戏前拒绝',async()=>{
 for(const bad of [{survivalGrades:[]},{survivalGrades:['SS'],survivalCounts:{SS:2}}]) {
   const io=mock([]);await assert.rejects(runFlow('survival',io,{...cfg,...bad}));assert.equal(io.actions.length,0);
 }
 assert.deepEqual(survivalPlan({}).grades,['SS','S','A','B','C']);
});
test('匹配战力优先最近；全部超阈值时随机',()=>{
 assert.equal(chooseOpponent(100,[{slot:1,power:130},{slot:2,power:90}],20).slot,2);
 assert.equal(chooseOpponent(100,[{slot:1,power:300},{slot:2,power:400}],20,()=>0.9).slot,2);
 assert.throws(()=>chooseOpponent(-1,[{slot:1,power:300}],20));
});
test('排位战次数归零才完成，胜负都确认',async()=>{
 const io=mock([{remaining:2,own:100,opponents:[{slot:1,power:110}]},{result:'victory'},{remaining:1,own:100,opponents:[{slot:1,power:110}]},{result:'defeat'},{remaining:0}]);
 await runFlow('ranked',io,cfg);
 assert.equal(io.actions.filter(x=>x.includes('星形结束战斗')).length,2);
 assert.equal(io.actions.filter(x=>x.includes('无论胜利还是失败')).length,2);
});
test('排位次数不变立即报错',async()=>{
 const s={remaining:2,own:100,opponents:[{slot:1,power:110}]};const io=mock([s,{result:'victory'},s]);
 await assert.rejects(runFlow('ranked',io,cfg),/次数未减少/);
 assert.equal(io.actions.filter(x=>x.includes('星形结束战斗')).length,1);
});

test('排位战自选场数包含失败，达到上限不刷新',async()=>{
 const s={remaining:5,own:100,opponents:[{slot:1,power:110}]};
 const io=mock([s,{result:'defeat'},{...s,remaining:4}]);
 await runFlow('ranked',io,{...cfg,rankedServer:'本服',rankedLimit:1});
 assert.equal(io.actions.filter(x=>x.includes('星形结束战斗')).length,1);
 assert.ok(io.actions.some(x=>x.includes('本服图标')));
 assert.ok(!io.actions.some(x=>x.startsWith('点击一次右下角刷新')));
});

test('排位战失败后冷却直接继续，可用则刷新后重新选人',async()=>{
 for(const state of ['ready','cooldown']) {
   const s={remaining:2,own:100,opponents:[{slot:1,power:110}]};
   const next={...s,remaining:1};
   const answers=[s,{result:'defeat'},next,{state}];
   if(state==='ready')answers.push({...next,opponents:[{slot:2,power:100}]});
   answers.push({result:'victory'},{remaining:0});
   const io=mock(answers);await runFlow('ranked',io,cfg);
   assert.equal(io.actions.filter(x=>x.startsWith('点击一次右下角刷新')).length,state==='ready'?1:0);
   assert.equal(io.actions.filter(x=>x.includes('星形结束战斗')).length,2);
   if(state==='ready')assert.ok(io.actions.some(x=>x.includes('第2个对手')));
 }
});

test('排位战未知胜负和无效参数在后续点击前停止',async()=>{
 const s={remaining:2,own:100,opponents:[{slot:1,power:110}]};
 const io=mock([s,{result:'unknown'}]);
 await assert.rejects(runFlow('ranked',io,cfg),/胜负无法/);
 assert.ok(!io.actions.some(x=>x.includes('无论胜利还是失败')));
 for(const bad of [{rankedServer:'全部'},{rankedLimit:-1},{rankedLimit:21},{rankedLimit:true}]) {
   const io=mock([]);await assert.rejects(runFlow('ranked',io,{...cfg,...bad}));assert.equal(io.actions.length,0);
 }
});
test('生存演习满分领奖，未到上限不结束',async()=>{
 const attempts={SS:1,S:0,A:0,B:0,C:0};
 const io=mock([{points:130,goal:210,reset:0,claimed:false,attempts},{points:130,goal:210,attempts},{points:210,remaining:0},{points:210,goal:210,attempts:{...attempts,SS:0}}]);
 await runFlow('survival',io,cfg);
 assert.equal(io.actions.filter(x=>x.includes('点击生存演习SS难度')).length,1);
 assert.equal(io.actions.filter(x=>x.includes('点击一键领取')).length,1);
});
test('SS/S已耗尽时使用A',async()=>{
 const attempts={SS:0,S:0,A:1,B:1,C:1};
 const io=mock([{points:190,goal:210,reset:0,claimed:false,attempts},{points:190,goal:210,attempts},{points:210,remaining:0},{points:210,goal:210,attempts:{...attempts,A:0}}]);
 await runFlow('survival',io,cfg);assert.ok(io.actions.some(x=>x.includes('点击生存演习A难度')));
});
test('积分识别失败不挑战',async()=>{
 const io=mock([{points:-1,goal:210}]);await assert.rejects(runFlow('survival',io,cfg),/积分/);
 assert.ok(!io.actions.some(x=>x.includes('开战')));
});
test('强者降临零奖励次数跳过',async()=>{
 const io=mock([{remaining:0}]);await runFlow('strong',io,cfg);assert.ok(!io.actions.some(x=>x.includes('再点击进入战斗')));
});
test('强者降临三种难度分别传入操作',async()=>{
 for(const difficulty of ['天级','夜叉级','阿修罗级']){const io=mock([{remaining:1},{victory:true}]);await runFlow('strong',io,{...cfg,difficulty});assert.ok(io.actions.some(x=>x.includes(difficulty)));}
});
test('生存演习有重置机会先重置，即使旧奖励已领',async()=>{
 const io=mock([{points:210,goal:210,reset:1,claimed:true},{points:210,goal:210}]);await runFlow('survival',io,cfg);assert.ok(io.actions.some(x=>x.includes('点击生存演习重置')));
});
test('强者降临失败不报告任务成功',async()=>{
 const io=mock([{remaining:1},{victory:false}]);await assert.rejects(runFlow('strong',io,cfg),/未确认胜利/);
});
test('托管完成依赖日志，随后退出温泉和家园',async()=>{
 const io=mock([]);let waited=false;io.until=async c=>{assert.ok(c.includes('托管日志'));waited=true;};const original=io.act;io.act=async p=>{if(p.includes('如果停留温泉'))assert.ok(waited);await original(p);};await runFlow('hosting',io,cfg);
 assert.ok(io.actions.some(x=>x.includes('离开家园')));
});

test('押镖找到SS后选择对应行，不刷新',async()=>{
 const io=mock([{remaining:3,freeRefreshes:4,matchingSlots:[2]}]);
 await runFlow('escort',io,cfg);
 assert.ok(io.actions.some(p=>p.includes('第2行SS任务的普通')));
 assert.ok(!io.actions.some(p=>p.includes('免费刷新”一次')));
});

test('押镖没有SS先免费刷新，再接取SS',async()=>{
 const io=mock([{remaining:3,freeRefreshes:4,matchingSlots:[]},{remaining:3,freeRefreshes:3,matchingSlots:[1]}]);
 await runFlow('escort',io,cfg);
 assert.equal(io.actions.filter(p=>p.includes('免费刷新”一次')).length,1);
 assert.ok(io.actions.some(p=>p.includes('第1行SS任务的普通')));
});

test('押镖次数为0跳过，免费刷新耗尽或上限为0时不刷新',async()=>{
 const skip=mock([{remaining:0}]);await runFlow('escort',skip,cfg);
 for(const [free,limit,reason] of [[0,4,/免费刷新次数已用完/],[4,0,/刷新上限/]]) {
  const io=mock([{remaining:3,freeRefreshes:free,matchingSlots:[]}]);
  await assert.rejects(runFlow('escort',io,{...cfg,escortRefreshLimit:limit}),reason);
  assert.ok(!io.actions.some(p=>p.includes('免费刷新”一次')||p.includes('行SS任务的普通')));
 }
});

test('押镖等级识别失败或刷新无进展时停止',async()=>{
 const unknown=mock([{remaining:3,matchingSlots:null}]);
 await assert.rejects(runFlow('escort',unknown,cfg),/等级未可靠识别/);
 const state={remaining:3,freeRefreshes:4,matchingSlots:[]};const stuck=mock([state,state]);
 await assert.rejects(runFlow('escort',stuck,cfg),/免费刷新次数未减少/);
 assert.equal(stuck.actions.filter(p=>p.includes('免费刷新”一次')).length,1);
});

test('SS接取未确认成功时不能报告完成',async()=>{
 const io=mock([{remaining:3,matchingSlots:[3]}]);
 io.verify=async p=>{if(p.includes('SS押镖任务'))throw Error('接取未成功');};
 await assert.rejects(runFlow('escort',io,cfg),/接取未成功/);
});

test('押镖选择S会按单S查询并接取，不默认使用SS',async()=>{
 const io=mock([{remaining:2,matchingSlots:[3]}]);
 const query=io.query;let prompt='';io.query=async p=>{prompt=p;return query(p);};
 await runFlow('escort',io,{...cfg,escortGrade:'S'});
 assert.ok(prompt.includes('等级明确为S的行号'));
 assert.ok(io.actions.some(p=>p.includes('第3行S任务的普通')));
 assert.ok(!io.actions.some(p=>p.includes('行SS任务的普通')));
});

test('押镖拒绝无效等级和超过每日上限的次数',async()=>{
 const invalid=mock([]);await assert.rejects(runFlow('escort',invalid,{...cfg,escortGrade:'A'}),/等级应为SS或S/);
 assert.equal(invalid.actions.length,0);
 const excess=mock([{remaining:4,matchingSlots:[1]}]);await assert.rejects(runFlow('escort',excess,cfg),/每日3次上限/);
 assert.ok(!excess.actions.some(p=>p.includes('行SS任务的普通')));
});
