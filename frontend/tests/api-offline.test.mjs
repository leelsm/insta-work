import {test} from 'node:test'
import assert from 'node:assert/strict'
import {readFileSync} from 'node:fs'
import ts from 'typescript'
const source=ts.transpileModule(readFileSync(new URL('../src/api.ts',import.meta.url),'utf8'),{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ESNext}}).outputText
globalThis.sessionStorage={getItem:()=>''}
const {api}=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
test('network failure shows a Korean local-service message',async()=>{
 globalThis.fetch=async()=>{throw new TypeError('Failed to fetch')}
 await assert.rejects(api('/news'),{message:'스튜디오 로컬 서비스에 연결할 수 없습니다. 앱을 다시 실행해주세요.'})
})
test('aborted requests keep their AbortError',async()=>{
 globalThis.fetch=async()=>{throw new DOMException('aborted','AbortError')}
 await assert.rejects(api('/news'),{name:'AbortError'})
})
