const sleep=ms=>new Promise(r=>setTimeout(r,ms));
export async function createMidsceneAdapter({cfg,checkpoint,emit}) {
  for(const k of ['MIDSCENE_MODEL_API_KEY','MIDSCENE_MODEL_NAME','MIDSCENE_MODEL_BASE_URL','MIDSCENE_MODEL_FAMILY']) if(!process.env[k]) throw Error('请先配置模型连接：'+k);
  await sleep(2000);
  const {agentForComputer}=await import('@midscene/computer');
  const agent=await agentForComputer({ ...(cfg.displayId?{displayId:cfg.displayId}:{}), aiContexts:{aiAct:'只操作360游戏大厅中的火影忍者online当前账号。不切换账号，不充值、不购买次数、不花元宝，不改变阵容。依据最新截图操作；无法识别就报错。所有关闭动作仅限游戏内面板，不关闭程序。'} });
  const io={
    log:message=>emit('log',message),
    act:async prompt=>{await checkpoint();emit('log',prompt);await agent.aiAct(prompt);},
    query:async prompt=>{await checkpoint();return agent.aiQuery(prompt);},
    verify:async prompt=>{await checkpoint();await agent.aiAssert(prompt);},
    wait:async ms=>{for(let i=0;i<ms;i+=250){await checkpoint();await sleep(Math.min(250,ms-i));}},
    until:async (condition,seconds)=>{
      let remaining=seconds*1000;
      while(remaining>0) {
        await checkpoint(); const start=Date.now();
        const answer=await agent.aiQuery('{ready:boolean}，根据当前游戏画面判断以下条件是否已满足。无法确认就返回false：'+condition);
        if(answer?.ready === true) return;
        await io.wait(3000); remaining-=Date.now()-start;
      }
      throw Error('等待超时：'+condition);
    }
  };
  return io;
}
