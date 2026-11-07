import http from 'node:http';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const root=path.dirname(fileURLToPath(import.meta.url));
const files={'/':['index.html','text/html'],'/index.html':['index.html','text/html'],'/styles.css':['styles.css','text/css'],'/app.js':['app.js','text/javascript'],'/mark.svg':['mark.svg','image/svg+xml']};
const server=http.createServer(async(req,res)=>{
  const file=files[new URL(req.url,'http://127.0.0.1').pathname];
  if(!file){res.writeHead(404);res.end('Not found');return;}
  try{const data=await readFile(path.join(root,file[0]));res.writeHead(200,{'Content-Type':`${file[1]}; charset=utf-8`,'Cache-Control':'no-store'});res.end(data);}
  catch{res.writeHead(500);res.end('Preview file unavailable');}
});
server.listen(4175,'127.0.0.1',()=>console.log('Local: http://127.0.0.1:4175'));
