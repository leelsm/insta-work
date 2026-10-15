import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
const source=readFileSync(new URL('../src/readingSpeed.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {readableLength,recommendedDuration,subtitleSpeed}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
test('reading length ignores spaces and counts emoji clusters once',()=>{
 assert.equal(readableLength('안녕 하세요\n반가워요'),9)
 assert.equal(readableLength('👨‍👩‍👧 🇰🇷 👍🏽'),3)
 assert.equal(readableLength('   '),0)
})
test('recommended duration is 7 characters per second plus 1 second, rounded up to 0.5s',()=>{
 assert.equal(recommendedDuration(''),0)
 assert.equal(recommendedDuration('가'.repeat(7)),2)
 assert.equal(recommendedDuration('가'.repeat(14)),3)
 assert.equal(recommendedDuration('가'.repeat(15)),3.5)
 assert.equal(recommendedDuration('가'.repeat(70)),11)
})
test('warning only when the scene is shorter than the recommendation',()=>{
 const text='가'.repeat(35) // 5s + 1s = 6s
 assert.equal(subtitleSpeed([{duration:6}],0,text),null)
 assert.equal(subtitleSpeed([{duration:8}],0,text),null)
 assert.equal(subtitleSpeed([{duration:6}],0,''),null)
 assert.deepEqual(subtitleSpeed([{duration:4}],0,text),{recommended:6,current:4,applicable:6})
})
test('one-click duration is clamped to 30s per scene and the 180s total',()=>{
 const long='가'.repeat(400)
 assert.equal(subtitleSpeed([{duration:5}],0,long).applicable,30)
 const scenes=[{duration:30},{duration:30},{duration:30},{duration:30},{duration:30},{duration:26},{duration:4}]
 assert.equal(subtitleSpeed(scenes,6,'가'.repeat(70)).applicable,null)
 scenes[5].duration=21.5
 const limited=subtitleSpeed(scenes,6,'가'.repeat(70))
 assert.equal(limited.applicable,8.5)
 assert.equal(limited.recommended,11)
 const sum=scenes.reduce((n,s,i)=>n+(i===6?limited.applicable:s.duration),0)
 assert.ok(sum<=180)
})
