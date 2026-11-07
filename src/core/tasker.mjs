export class Tasker {
  constructor({resource,handlers,io,checkpoint,emit,beforeTask}) {Object.assign(this,{resource,handlers,io,checkpoint,emit,beforeTask});}
  async postTask(id,cfg) {
    const task=this.resource.task(id);
    await this.checkpoint();if(this.beforeTask) await this.beforeTask(id);
    this.emit('task',task.label+'：运行中',{id,status:'running'});
    let nodeName=task.entry;const visited=new Set();
    try {
      while(nodeName) {
        await this.checkpoint();
        if(visited.has(nodeName)) throw Error('任务资源存在无限循环：'+nodeName);
        visited.add(nodeName);const node=this.resource.nodes[nodeName];
        this.emit('node',nodeName+'：开始',{id,node:nodeName,status:'running'});
        if(node.action.type==='Custom') {
          const handler=this.handlers[node.action.handler];
          if(!handler) throw Error('自定义处理器未注册：'+node.action.handler);
          await handler(this.io,cfg);
        }
        this.emit('node',nodeName+'：完成',{id,node:nodeName,status:'done'});nodeName=node.next[0];
      }
      this.emit('task',task.label+'：完成',{id,status:'done'});
    } catch(error) {this.emit('task',task.label+'：失败',{id,status:'failed'});throw error;}
  }
  async run(ids,cfg) {
    for(const id of ids)this.resource.task(id);
    for(const id of ids)await this.postTask(id,cfg);
  }
}
