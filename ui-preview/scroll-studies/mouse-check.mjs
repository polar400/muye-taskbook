// Coordinates are measured from this task's page; connects only to its owned QA browser.
const url = process.argv[2];
if (!url?.startsWith('ws://127.0.0.1:')) throw new Error('Expected local QA browser URL');
const socket = new WebSocket(url);
await new Promise((resolve, reject) => { socket.onopen = resolve; socket.onerror = reject; });
let id = 0;
const pending = new Map();
socket.onmessage = event => {
  const message = JSON.parse(event.data);
  if (!message.id) return;
  const handlers = pending.get(message.id);
  if (!handlers) return;
  pending.delete(message.id);
  if (message.error) handlers.reject(new Error(message.error.message));
  else handlers.resolve(message.result);
};
function call(method, params = {}, sessionId) {
  return new Promise((resolve, reject) => {
    const requestId = ++id;
    pending.set(requestId, { resolve, reject });
    socket.send(JSON.stringify({ id: requestId, method, params, ...(sessionId ? { sessionId } : {}) }));
  });
}
const timeout = setTimeout(() => { socket.close(); process.exitCode = 1; console.error('Mouse check timed out'); }, 15000);
try {
  const { targetInfos } = await call('Target.getTargets');
  const target = targetInfos.find(info => info.type === 'page' && info.url.startsWith('http://127.0.0.1:4173'));
  if (!target) throw new Error('Owned preview tab not found');
  const { sessionId } = await call('Target.attachToTarget', { targetId: target.targetId, flatten: true });
  const evaluate = async expression => {
    const result = await call('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true }, sessionId);
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  };
  const point = await evaluate(`(() => {
    const area = document.querySelector('.snap-window');
    area.scrollTo({top:0,behavior:'instant'});
    const r = area.getBoundingClientRect();
    return {x:r.left+r.width/2,y:Math.min(innerHeight-80,r.top+r.height/2),page:scrollY,height:area.clientHeight};
  })()`);
  await call('Input.dispatchMouseEvent', { type: 'mouseMoved', x: point.x, y: point.y }, sessionId);
  await call('Input.dispatchMouseEvent', { type: 'mouseWheel', x: point.x, y: point.y, deltaX: 0, deltaY: Math.round(point.height * .7) }, sessionId);
  await new Promise(resolve => setTimeout(resolve, 900));
  const after = await evaluate(`({page:scrollY,offset:document.querySelector('.snap-window').scrollTop,count:document.querySelector('#snap-count').textContent})`);
  if (Math.abs(after.offset - point.height) > 1 || after.page !== point.page || after.count !== '02 / 03') throw new Error(`Wheel did not snap: ${JSON.stringify({point,after})}`);
  console.log(JSON.stringify({ passed: true, before: point, after }));
  await evaluate(`document.querySelector('.snap-window').scrollTo({top:1080,behavior:'instant'})`);
  await call('Input.dispatchMouseEvent', { type: 'mouseWheel', x: point.x, y: point.y, deltaX: 0, deltaY: 600 }, sessionId);
  await new Promise(resolve => setTimeout(resolve, 500));
  const exit = await evaluate('scrollY');
  if (exit <= point.page) throw new Error('End of snap area did not release page scrolling');
  console.log(JSON.stringify({ passed: true, snapBoundaryReleasesPage: true, pageBefore: point.page, pageAfter: exit }));
} finally { clearTimeout(timeout); socket.close(); }
