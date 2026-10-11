import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'

const source = ts.transpileModule(readFileSync(new URL('../src/api.ts', import.meta.url), 'utf8'), {
 compilerOptions: {target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ESNext},
}).outputText

async function setup({bitmap=true, portrait=false, bitmapFails=false}={}) {
 const calls=[]
 let closed=false
 const width=portrait?6000:8000, height=portrait?8000:6000
 class Photo {
  naturalWidth=width;naturalHeight=height
  set src(value){queueMicrotask(()=>this.onload())}
 }
 globalThis.sessionStorage={getItem:()=>''}
 globalThis.HTMLImageElement=Photo
 globalThis.Image=Photo
 globalThis.createImageBitmap=bitmap?async()=>{
  if(bitmapFails)throw new Error('decoder unavailable')
  return {width,height,close(){closed=true}}
 }:undefined
 globalThis.document={createElement:()=>{
  const canvas={width:0,height:0,getContext:()=>({drawImage(...args){calls.push(args.slice(1))}}),
   toBlob(callback,mime,quality){calls.push({mime,quality,width:canvas.width,height:canvas.height});callback(new Blob(['compressed'],{type:mime}))}}
  return canvas
 }}
 const create=URL.createObjectURL, revoke=URL.revokeObjectURL
 URL.createObjectURL=()=> 'blob:original';URL.revokeObjectURL=value=>calls.push({revoked:value})
 globalThis.fetch=async(url,options)=>{
  calls.push({url,body:options.body})
  return {ok:true,json:async()=>({asset_id:'saved'})}
 }
 const {uploadPhoto}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
 return {uploadPhoto,calls,closed:()=>closed,cleanup(){URL.createObjectURL=create;URL.revokeObjectURL=revoke}}
}

for(const options of [{bitmap:true},{bitmap:false,portrait:true},{bitmap:true,bitmapFails:true}]) {
 test(`48 MP photo is resized before upload ${JSON.stringify(options)}`,async()=>{
  const env=await setup(options)
  try{
   // Originals over 20 MB must be compressed rather than rejected.
   const original={name:'48MP.jpg',size:30_000_000}
   const result=await env.uploadPhoto(original)
   assert.equal(result.asset_id,'saved')
   const encoded=env.calls.find(item=>item.mime)
   assert.equal(Math.max(encoded.width,encoded.height),1920)
   assert.equal(Math.min(encoded.width,encoded.height),1440)
   assert.equal(encoded.mime,'image/jpeg')
   const request=env.calls.find(item=>item.url)
   assert.notEqual(request.body,original)
   assert.equal(request.body.type,'image/jpeg')
   assert.equal(request.body.size,10)
   if(options.bitmap&&!options.bitmapFails)assert.equal(env.closed(),true)
   else assert.ok(env.calls.some(item=>item.revoked==='blob:original'))
  }finally{env.cleanup()}
 })
}

test('old news exports are not presented as the updated full-screen preview', async()=>{
 globalThis.sessionStorage={getItem:()=>''}
 const {isCurrentRender}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
 assert.equal(isCurrentRender({content_type:'news',render:{folder:'old'}}),false)
 assert.equal(isCurrentRender({content_type:'news',render:{layout_version:2}}),true)
 assert.equal(isCurrentRender({content_type:'daily',render:{folder:'photo-video'}}),true)
 assert.equal(isCurrentRender({content_type:'news',render:null}),false)
})
