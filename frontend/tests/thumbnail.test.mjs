import {readFileSync} from 'node:fs'
import {test} from 'node:test'
import assert from 'node:assert/strict'
import ts from 'typescript'
const source=readFileSync(new URL('../src/thumbnail.ts',import.meta.url),'utf8')
const js=ts.transpileModule(source,{compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.ES2022}}).outputText
const {remapThumbnail}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
test('thumbnail follows its scene through reordering, editing, and deletion',()=>{
 const a={},b={},c={},before=[a,b,c]
 assert.equal(remapThumbnail(before,[c,a,b],1),2)
 assert.equal(remapThumbnail(before,[b,c],1),0)
 assert.equal(remapThumbnail(before,[a,{...b},c],1),1)
 assert.equal(remapThumbnail(before,[a,c],1),1)
 assert.equal(remapThumbnail(before,[a,b],2),1)
 assert.equal(remapThumbnail(before,[a,b,c]),0)
})
