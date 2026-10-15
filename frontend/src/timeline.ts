import type {Project,Scene} from './types'
export function sceneAt(scenes:Scene[],time:number){
 let start=0
 for(let index=0;index<scenes.length;index++){
  const duration=Math.max(.08,Number(scenes[index].duration)||2)
  if(time<start+duration||index===scenes.length-1)return {index,start,duration,elapsed:Math.max(0,Math.min(duration,time-start))}
  start+=duration
 }
 return {index:0,start:0,duration:1,elapsed:0}
}
export function motionTransform(motion:Project['motion'],progress:number){
 const p=Math.max(0,Math.min(1,progress))
 if(motion==='zoom')return `scale(${1+.045*p})`
 if(motion==='zoom-out')return `scale(${1+.045*(1-p)})`
 if(motion==='pan-left')return `translateX(${2.25-4.5*p}%) scale(1.045)`
 if(motion==='pan-right')return `translateX(${4.5*p-2.25}%) scale(1.045)`
 return 'none'
}
// Crossfade centred on each scene boundary: the neighbouring scene is drawn on top with
// `opacity`, reaching 50% exactly at the cut, so scene durations and subtitle timing stay
// unchanged. The very first and last frames are never faded.
export function crossfadeAt(scenes:Scene[],time:number,transition:Project['transition'],half=.25){
 const position=sceneAt(scenes,time)
 if(transition!=='fade')return {...position,neighbor:-1,opacity:0}
 const window=Math.min(half,position.duration/2)
 if(window>0&&position.index>0&&position.elapsed<window)return {...position,neighbor:position.index-1,opacity:.5-position.elapsed/window/2}
 const remaining=position.duration-position.elapsed
 if(window>0&&position.index<scenes.length-1&&remaining<window)return {...position,neighbor:position.index+1,opacity:.5-remaining/window/2}
 return {...position,neighbor:-1,opacity:0}
}
export function captionParts(text:string){
 const result:string[]=[]
 for(let part of text.trim().split(/(?<=[.!?。])\s+|\n+/)){
  // Match the renderer's 64-code-point chunks, keeping each emoji cluster whole.
  // JS string offsets are UTF-16 and would split even a single smiley in half.
  let chars=Array.from(part)
  while(chars.length>64){
   const space=chars.slice(0,64).lastIndexOf(' ')
   let cut=space>=15?space:64
   if(space<15){
    const Segmenter=(Intl as unknown as {Segmenter?:new(locale?:string,options?:{granularity:'grapheme'})=>{segment(input:string):Iterable<{segment:string}>}}).Segmenter
    const units=Segmenter?Array.from(new Segmenter('ko',{granularity:'grapheme'}).segment(part),s=>s.segment):chars
    let start=0
    for(const unit of units){const end=start+Array.from(unit).length;if(start<cut&&cut<end){cut=start||end;break}start=end}
   }
   result.push(chars.slice(0,cut).join('').trim());part=chars.slice(cut).join('').trim();chars=Array.from(part)
  }
  if(part)result.push(part)
 }
 return result.length?result:['']
}
