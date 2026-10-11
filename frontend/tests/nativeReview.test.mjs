import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
// Evaluate the small delivery queue with a fake transport, without browser globals.
const source=readFileSync(new URL('../src/nativeReview.ts',import.meta.url),'utf8')
 .replace("import {api} from './api'",'').replace('let pending:Promise<unknown>','let pending')
 .replace('export function syncNativeReview(reviewing:boolean):Promise<unknown>','function syncNativeReview(reviewing)')
const make=api=>new Function('api',source+';return syncNativeReview')(api)
test('review entry and exit are delivered in order',async()=>{
 const seen=[];const send=make(async(path,method,body)=>{await new Promise(r=>setTimeout(r,5));seen.push([path,method,body.reviewing])})
 await Promise.all([send(true),send(false),send(true)])
 assert.deepEqual(seen.map(x=>x[2]),[true,false,true])
 assert.ok(seen.every(x=>x[0]==='/video-review'&&x[1]==='POST'))
})
test('failed delivery cannot crash preview or block the next update',async()=>{
 const seen=[];const send=make(async(_,__,body)=>{seen.push(body.reviewing);if(body.reviewing)throw Error('offline')})
 await send(true);await send(false);assert.deepEqual(seen,[true,false])
})
