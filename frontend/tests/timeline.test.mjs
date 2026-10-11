import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
const source=readFileSync(new URL('../src/timeline.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {sceneAt,captionParts}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
test('playback follows edited scene order and duration',()=>{
 const scenes=[{title:'one',duration:2},{title:'two',duration:4},{title:'three',duration:3}]
 assert.equal(sceneAt(scenes,2).index,1)
 assert.equal(sceneAt(scenes,5).elapsed,3)
 const edited=[scenes[2],scenes[0],scenes[1]]
 assert.equal(edited[sceneAt(edited,0).index].title,'three')
 assert.equal(edited[sceneAt(edited,3).index].title,'one')
 assert.equal(sceneAt(edited,99).elapsed,4)
 edited[0].duration=10
 assert.equal(sceneAt(edited,5).index,0)
})
test('news captions advance in readable chunks',()=>{
 assert.deepEqual(captionParts('첫 번째 이야기. 두 번째 이야기!'),['첫 번째 이야기.','두 번째 이야기!'])
 const text='가'.repeat(130)
 assert.deepEqual(captionParts(text).map(x=>x.length),[64,64,2])
})
