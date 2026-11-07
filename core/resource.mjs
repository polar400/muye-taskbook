import fs from 'node:fs';
// Application resource format; not a Maa Pipeline parser.
export class Resource {
  constructor(data) {
    if(data.format!=='naruto-task-resource-v1' || !Array.isArray(data.tasks) || !data.nodes) throw Error('任务资源格式无效');
    this.tasks=data.tasks; this.nodes=data.nodes;
    const ids=new Set();
    for(const task of this.tasks) {
      if(!task.id || !task.label || !this.nodes[task.entry] || ids.has(task.id)) throw Error('任务入口不存在或ID重复');
      ids.add(task.id);
    }
    for(const [name,node] of Object.entries(this.nodes)) {
      if(!['Custom','DoNothing'].includes(node.action?.type)) throw Error('不支持的动作：'+name);
      if(node.action.type==='Custom' && !node.action.handler) throw Error('缺少自定义处理器：'+name);
      if(!Array.isArray(node.next) || node.next.length>1) throw Error('当前只支持单个后继节点：'+name);
      for(const next of node.next) if(!this.nodes[next]) throw Error('后继节点不存在：'+next);
    }
  }
  static load(file) {return new Resource(JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,'')));}
  task(id) {const task=this.tasks.find(t=>t.id===id);if(!task)throw Error('未知任务 '+id);return task;}
}
