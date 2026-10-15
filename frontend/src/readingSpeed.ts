// Fast-subtitle rule shared by the card news and daily editors (mirrored on iPhone):
// readers need about 7 characters per second plus a 1 second margin.
export const READING_CHARS_PER_SECOND=7
export const READING_MARGIN_SECONDS=1
export const SCENE_MIN_SECONDS=2
export const SCENE_MAX_SECONDS=30
export const TOTAL_MAX_SECONDS=180

export function readableLength(text:string){
 const visible=text.replace(/\s+/g,'')
 const Segmenter=(Intl as unknown as {Segmenter?:new(locale?:string,options?:{granularity:'grapheme'})=>{segment(input:string):Iterable<unknown>}}).Segmenter
 return Segmenter?Array.from(new Segmenter('ko',{granularity:'grapheme'}).segment(visible)).length:Array.from(visible).length
}

// Seconds needed to read `text`, rounded up to the editor's 0.5s step. 0 for empty text.
export function recommendedDuration(text:string){
 const length=readableLength(text)
 if(!length)return 0
 return Math.ceil((length/READING_CHARS_PER_SECOND+READING_MARGIN_SECONDS)*2-1e-9)/2
}

// Warning for scene `index` or null when its subtitle can be read comfortably.
// `applicable` is the duration the one-click fix may set: clamped to the scene limits and to
// what the 180 second total still allows; null when it cannot be lengthened at all.
export function subtitleSpeed(scenes:{duration:number}[],index:number,text:string){
 const current=Number(scenes[index]?.duration)||0
 const recommended=recommendedDuration(text)
 if(!recommended||current>=recommended)return null
 const others=scenes.reduce((sum,scene,i)=>i===index?sum:sum+(Number(scene.duration)||0),0)
 const limit=Math.min(SCENE_MAX_SECONDS,Math.floor((TOTAL_MAX_SECONDS-others)*2+1e-9)/2)
 const target=Math.max(SCENE_MIN_SECONDS,Math.min(recommended,limit))
 return {recommended,current,applicable:target>current?target:null}
}
