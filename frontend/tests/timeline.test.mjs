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
test('news caption boundaries preserve whole emoji clusters and match renderer code-point limits',()=>{
 for(const cluster of ['👨‍👩‍👧','👍🏽','🇰🇷','😀','#️⃣','❤️']){
  const text='가'.repeat(63)+cluster+'나'
  const parts=captionParts(text)
  assert.equal(parts.join(''),text)
  assert.ok(parts.some(part=>part.includes(cluster)),cluster)
  assert.ok(parts.every(part=>!/[\uD800-\uDBFF]$/.test(part)))
 }
 assert.deepEqual(captionParts('😀'.repeat(65)),['😀'.repeat(64),'😀'])
})
test('crossfade blends neighbouring scenes around each boundary without changing timing',async()=>{
 const {crossfadeAt}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
 const scenes=[{duration:3},{duration:4},{duration:2}]
 assert.deepEqual([crossfadeAt(scenes,0,'fade').neighbor,crossfadeAt(scenes,0,'fade').opacity],[-1,0])
 assert.equal(crossfadeAt(scenes,1.5,'fade').neighbor,-1)
 const before=crossfadeAt(scenes,2.9,'fade')
 assert.equal(before.index,0);assert.equal(before.neighbor,1);assert.ok(Math.abs(before.opacity-.3)<1e-9)
 const at=crossfadeAt(scenes,3,'fade')
 assert.equal(at.index,1);assert.equal(at.neighbor,0);assert.equal(at.opacity,.5)
 const after=crossfadeAt(scenes,3.2,'fade')
 assert.equal(after.neighbor,0);assert.ok(Math.abs(after.opacity-.1)<1e-9)
 assert.equal(crossfadeAt(scenes,8.9,'fade').neighbor,-1)
 assert.equal(crossfadeAt(scenes,9,'fade').opacity,0)
 assert.equal(crossfadeAt(scenes,2.9,'cut').neighbor,-1)
 assert.equal(crossfadeAt(scenes,3.2,'fade').start,3)
})
