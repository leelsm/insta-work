import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
const source=readFileSync(new URL('../src/summary.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {summaryScenes}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))

test('short manual text stays one card without filler',()=>{
 const scenes=summaryScenes('안녕하세요')
 assert.equal(scenes.length,1)
 assert.equal(scenes[0].body,'안녕하세요')
 assert.equal(scenes[0].title,'안녕하세요')
 assert.equal(scenes[0].duration,4)
 assert.ok(!scenes.some(s=>s.body.includes('기사 요약')))
})
test('few sentences make few cards and never split mid-sentence',()=>{
 const sentences=['첫 번째 문장입니다.','두 번째 문장이에요!','세 번째는 질문일까요?']
 const scenes=summaryScenes(sentences.join(' '))
 assert.ok(scenes.length>=1&&scenes.length<=3)
 const bodies=scenes.map(s=>s.body).join(' ')
 assert.equal(bodies,sentences.join(' '))
 for(const s of scenes)for(const piece of s.body.split(/(?<=[.!?])\s+/))assert.ok(sentences.includes(piece),piece)
})
test('long text is capped at five cards of at most 500 characters on sentence boundaries',()=>{
 const sentence='오늘 발표된 내용은 지역 경제와 교통 계획에 관한 것입니다.'
 const text=Array.from({length:120},()=>sentence).join(' ')
 const scenes=summaryScenes(text)
 assert.equal(scenes.length,5)
 for(const s of scenes){assert.ok(s.body.length<=500);assert.ok(s.body.endsWith('.'));assert.ok(s.duration>=4&&s.duration<=10)}
 assert.equal(scenes[0].duration,10)
})
test('an overlong sentence is split at spaces, not characters',()=>{
 const words=Array.from({length:200},(_,i)=>'단어'+i)
 const scenes=summaryScenes(words.join(' '))
 assert.ok(scenes.length>=2)
 const all=scenes.flatMap(s=>s.body.split(' '))
 assert.deepEqual(all,words)
 for(const s of scenes)assert.ok(s.body.length<=500)
})
test('duration follows text length',()=>{
 assert.equal(summaryScenes('가'.repeat(54))[0].duration,6)
})
test('text that fits in five cards is never dropped',()=>{
 const sentences=Array.from({length:6},(_,i)=>String(i).repeat(399)+'.')
 const text=sentences.join(' ')
 const scenes=summaryScenes(text)
 assert.ok(scenes.length<=5)
 for(const s of scenes)assert.ok(s.body.length<=500)
 const kept=scenes.map(s=>s.body).join(' ')
 assert.ok(kept.length>=2000,String(kept.length))
 assert.ok(text.startsWith(kept))
})
test('a few short sentences stay on one card',()=>{
 const text='오늘은 날씨가 좋다. 공원에 갔다. 다시 오고 싶다.'
 const scenes=summaryScenes(text)
 assert.equal(scenes.length,1)
 assert.equal(scenes[0].body,text)
})
