export const names = {survival:'生存演习', strong:'强者降临', hosting:'游戏内托管', ranked:'排位战', escort:'押镖（接取）'};

export function chooseOpponent(own, opponents, tolerance, random = Math.random) {
  if (!Number.isFinite(own) || own <= 0 || !opponents.length || opponents.some(x => !Number.isFinite(x.power) || x.power <= 0 || !Number.isInteger(x.slot))) throw Error('无法可靠读取战力和对手，请人工检查');
  const nearest = [...opponents].sort((a,b) => Math.abs(a.power-own)-Math.abs(b.power-own))[0];
  return Math.abs(nearest.power-own)/own <= tolerance/100 ? nearest : opponents[Math.floor(random()*opponents.length)];
}
const number = (x, label) => { if (!Number.isInteger(x) || x < 0) throw Error(`${label}未可靠识别，停止操作`); return x; };
export function rankedOptions(cfg) {
  const server=cfg.rankedServer==='联服'?'连服':(cfg.rankedServer??'连服');
  const limit=cfg.rankedLimit??0;
  if (!['本服','连服'].includes(server)) throw Error('排位战挑战范围应为本服或连服');
  if (!Number.isInteger(limit)||limit<0||limit>20) throw Error('排位战挑战上限应为0至20，0表示用完剩余次数');
  return {server,limit};
}
export function survivalPlan(cfg) {
  const order=['SS','S','A','B','C'];
  const selected=cfg.survivalGrades ?? order;
  if (!Array.isArray(selected) || !selected.length || new Set(selected).size!==selected.length || selected.some(g=>!order.includes(g))) throw Error('生存演习请至少选择一个有效等级：SS、S、A、B、C');
  const limits=cfg.survivalCounts;
  if (limits!=null && (typeof limits!=='object' || Array.isArray(limits) || selected.some(g=>!Number.isInteger(limits[g]) || limits[g]<1 || limits[g]>(g==='SS'?1:30)))) throw Error('生存演习场数无效；SS每天最多1场');
  return {grades:order.filter(g=>selected.includes(g)), limits};
}

export async function runFlow(id, io, cfg) {
  const {act, query, verify, log, wait} = io;
  const home = async () => { await act('关闭当前任务的游戏内面板，回到木叶村主界面。只用游戏内红色叉号；如位于家园，点击右下角离开并确认。不要关闭360游戏程序。'); await verify('火影忍者online木叶村主界面可见，顶部有生存演习、强者降临、排位战入口。'); };
  const auto = async () => act('检查游戏内战斗按钮：绿色“自动”表示未开启，要点击到红色“取消”才开启。已是红色取消则保持。如速度为×1点一次变×2，已为×2保持。不点击撤退。');
  if (id === 'survival') {
    const {grades,limits}=survivalPlan(cfg); const used={};
    log('生存演习挑战计划：'+grades.join(' → '));
    await home(); await act('点击顶部生存演习入口。');
    let s = await query('{points:number, goal:number, reset:number, claimed:boolean, attempts:{SS:number,S:number,A:number,B:number,C:number}}，读取生存演习当前积分、积分上限、剩余重置次数、奖励是否全部已领，以及各难度剩余挑战次数。数字无法读清返回-1，不能猜测。');
    number(s.points,'积分'); number(s.goal,'目标积分'); if (!s.goal) throw Error('积分上限无效');
    if (cfg.reset && number(s.reset,'重置次数') === 1) {
      await act('点击生存演习重置按钮。如有免费的重置确认则确认，遇到需要花费货币则停止。');
      await verify('生存演习剩余重置次数为0。');
    } else if (s.claimed) { log('今日奖励已领取，跳过'); await home(); return; }
    for (let i=0;i<30;i++) {
      s = await query('{points:number, goal:number, attempts:{SS:number,S:number,A:number,B:number,C:number}}，准确读取生存演习积分和各难度剩余次数，无法读清返回-1。');
      number(s.points,'积分'); number(s.goal,'积分上限'); if (!s.goal) throw Error('积分上限无效');
      log(`积分 ${s.points}/${s.goal}`);
      if (s.points >= s.goal) {
        await act('点击一键领取。如果弹出领取后无法更改难度的确认，点击是；奖励弹窗点击确定。');
        await verify('生存演习积分达到上限，奖励显示已领取或全部奖励已经领取。'); await home(); return;
      }
      const tier = grades.find(t=>(limits==null || (used[t]??0)<limits[t]) && number(s.attempts?.[t],t+'次数')>0);
      if (!tier) throw Error('所选等级的游戏次数或计划场数已耗尽，积分未满；请调整生存演习高级设置');
      log(`挑战 ${tier}`); await act(`点击生存演习${tier}难度，进入准备界面后点击黄色开战按钮。`); await auto();
      await io.until('战斗结束，出现胜利或失败结算和确定按钮',cfg.battleSeconds);
      await act('点击战斗结算的确定，返回生存演习界面。');
      await verify('生存演习积分和剩余挑战次数可见。');
      const next = await query('{points:number, remaining:number}，读取生存演习积分和'+tier+'难度剩余次数，无法读清返回-1。');
      number(next.points,'积分'); number(next.remaining,'剩余次数');
      if (next.points === s.points && next.remaining >= s.attempts[tier]) throw Error('战斗后积分和次数没有变化，停止防止重复点击');
      used[tier]=(used[tier]??0)+1;
    }
    throw Error('生存演习达到操作上限');
  }
  if (id === 'strong') {
    await home(); await act('点击顶部强者降临入口。');
    const s = await query('{remaining:number}，读取本周可用普通奖励次数，无法读清返回-1。');
    if (number(s.remaining,'奖励次数') === 0) { log('本周普通奖励次数为0，跳过'); await home(); return; }
    if (!['天级','夜叉级','阿修罗级'].includes(cfg.difficulty)) throw Error('难度配置无效');
    await act(`选择强者降临${cfg.difficulty}，再点击进入战斗。`); await auto();
    await io.until('强者降临整场战斗结束，出现胜利或失败结算确认按钮',cfg.battleSeconds);
    const result=await query('{victory:boolean}，当前强者降临结算是否明确为胜利？无法确认返回false。');
    await act('点击结算确认。如果出现查看分数，则点击查看分数，再点击确认关闭分数和结算界面。'); await home();
    if(result?.victory!==true) throw Error('强者降临未确认胜利，已退出结算，请检查');
    return;
  }
  if (id === 'hosting') {
    await home(); await act('点击中忍勋章下方橙色小电脑，打开托管系统；保留已有任务勾选和设置，点击开始托管。如果出现当天首次进入托管、消耗1张托管卡的确认弹窗，点击确定一次；当天再次开启直接托管则不再点击确认。遇到购买、额外货币消耗或托管卡不足提示则停止。');
    await verify('游戏显示托管中。');
    await act('展开游戏内托管日志，保留托管运行状态，不点击退出托管。');
    log('等待游戏内所有托管任务完成');
    await io.until('托管日志最新一次运行明确显示托管结束，所有托管任务已完成。仅温泉页面或托管中图标不能证明完成；必要时展开托管日志查看。',cfg.hostingMinutes*60);
    await act('如果停留温泉界面，点击温泉右上角红色叉号；离开温泉提示点击确定。随后在家园点击右下角离开，离开家园提示点击确定。'); await home(); return;
  }
  if (id === 'ranked') {
    const {server,limit}=rankedOptions(cfg);
    await home(); await act('点击顶部排位战入口。');
    await act(`检查排位战当前范围，若不是${server}，点击右上角${server==='连服'?'联服':'本服'}图标切换。`);
    await verify(`排位战标题明确显示${server==='连服'?'联服':'本服'}排行。`);
    let last = null, completed=0, result=null;
    for (let i=0;i<30;i++) {
      const readPanel=()=>query('{remaining:number, own:number, opponents:[{slot:number,power:number}]}，读取排位战右上角剩余挑战次数、左上角我方战力、下方可挑战对手。slot按下方对手从左到右1开始编号，不包括上方前三名榜单。无法读清的数字返回-1。');
      let s = await readPanel();
      number(s.remaining,'剩余挑战次数'); log(`剩余挑战次数 ${s.remaining}`);
      if (last !== null && s.remaining >= last) throw Error('挑战次数未减少，停止防止重复挑战');
      if (s.remaining===0 || limit>0 && completed>=limit) {log(`本轮已挑战${completed}场，剩余${s.remaining}次`);await home();return;}
      if (result==='defeat') {
        const refresh=await query('{state:"ready"|"cooldown"|"unknown"}，检查右下角刷新对手按钮是否可免费使用，还是正在冷却。付费或无法判断返回unknown。');
        if (refresh.state==='ready') {
          const before=s.remaining;
          await act('点击一次右下角刷新对手。若提示冷却，确认提示后继续；不得购买刷新或消耗元宝、点券。');
          await verify('排位挑战面板已显示更新后的对手，或已明确提示刷新冷却并关闭提示。');
          s=await readPanel();number(s.remaining,'剩余挑战次数');
          if (s.remaining!==before)throw Error('刷新后挑战次数变化异常，停止');
        } else if (refresh.state==='cooldown') log('刷新对手正在冷却，继续按原规则挑战');
        else throw Error('无法确认免费刷新或冷却状态，停止');
      }
      const opponent=chooseOpponent(s.own,s.opponents,cfg.tolerance);
      log(`我方 ${s.own}，选择第${opponent.slot}个对手，战力 ${opponent.power}`);
      await act(`点击下方从左到右第${opponent.slot}个对手（战力${opponent.power}）的挑战按钮。`);
      await io.until('排位战战斗画面已加载，右下角结束战斗按钮可见',120);
      await act('点击右下角星形结束战斗按钮。不要点击旁边的撤退。');
      await io.until('出现胜利或失败结算，确定按钮可见',cfg.battleSeconds);
      const settlement=await query('{result:"victory"|"defeat"|"unknown"}，根据明确的胜利/失败结算读取胜负。不能因为没识别到胜利就认定失败，无法判断返回unknown。');
      result=settlement.result;
      if (!['victory','defeat'].includes(result))throw Error('排位战胜负无法可靠识别，保留结算');
      await act('无论胜利还是失败，点击结算确定按钮，返回排位战界面。');
      await verify('排位战界面显示剩余挑战次数。'); last=s.remaining;completed++;
    }
    throw Error('排位战达到操作上限');
  }
  if (id === 'escort') {
    const grade = cfg.escortGrade ?? 'SS';
    if (!['SS','S'].includes(grade)) throw Error('押镖接取等级应为SS或S');
    const refreshLimit = number(cfg.escortRefreshLimit ?? 4,'刷新上限');
    if (refreshLimit > 20) throw Error('押镖刷新上限不能超过20');
    await home();
    await act('点击主界面左侧“组队副本 进行中”横条，找到“押镖劫掠”活动，点击该活动的参加按钮。不要选择劫掠。');
    await io.until('押镖任务列表已出现，可以看到任务等级、每行押送按钮、今日剩余完成次数及右下角刷新按钮。',120);
    let refreshed = 0;
    let previousFree = null;
    while (true) {
      const s = await query(`{remaining:number, freeRefreshes:number, matchingSlots:number[]}，读取押镖界面今日剩余完成次数、右下角免费刷新次数和等级明确为${grade}的行号（自上而下从1开始）。严格区分双S的SS和单S的S，仅返回所选${grade}等级，不使用其他等级。没有匹配等级返回空数组；数字无法读清返回-1，等级无法识别时matchingSlots返回null。`);
      number(s.remaining,'押镖剩余完成次数');
      if (s.remaining > 3) throw Error('押镖剩余次数超过每日3次上限，请检查识别结果');
      if (s.remaining === 0) { log('今日押镖完成次数为0，跳过'); await home(); return; }
      if (!Array.isArray(s.matchingSlots) || s.matchingSlots.some(slot=>!Number.isInteger(slot)||slot<1||slot>3)) throw Error('押镖任务等级未可靠识别，停止操作');
      log(`押镖今日剩余次数 ${s.remaining}/3，${grade}任务 ${s.matchingSlots.length} 个`);
      if (s.matchingSlots.length) {
        const slot = s.matchingSlots[0];
        await act(`点击押镖任务列表自上而下第${slot}行${grade}任务的普通“押送”按钮，不点击“保险押送”。若要求付费刷新、购买许可证或花费点券元宝，不确认并停止。`);
        await verify(`${grade}押镖任务已经成功接取，出现押送中状态或对应任务目标；没有停留在付费提示或未确认的接取弹窗。`);
        log(`${grade}押镖已接取；每日最多3次，当前仅实现接取，后续完成押送及再次接取步骤待补充`);
        return;
      }
      const free = number(s.freeRefreshes,'免费刷新次数');
      if (previousFree !== null && free >= previousFree) throw Error('押镖免费刷新次数未减少，停止防止重复点击');
      if (free === 0) throw Error(`没有${grade}且免费刷新次数已用完，等待人工处理`);
      if (refreshed >= refreshLimit) throw Error(`没有${grade}且已达到押镖刷新上限`);
      await io.until('押镖界面右下角免费刷新按钮可点击，刷新冷却已结束。',600);
      await act('点击押镖界面右下角“免费刷新”一次。只使用免费次数，若出现付费或购买提示，不确认并停止。');
      await verify('押镖任务列表刷新完成，今日剩余完成次数和各行任务等级可以重新读取。');
      previousFree = free;
      refreshed++;
    }
  }
  throw Error('未知任务 '+id);
}
