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
export function fadeOpacity(transition:Project['transition'],elapsed:number,duration:number){
 return transition==='fade'?Math.max(0,Math.min(1,elapsed/.25,(duration-elapsed)/.25)):1
}
export function captionParts(text:string){
 const result:string[]=[]
 for(let part of text.trim().split(/(?<=[.!?。])\s+|\n+/)){
  while(part.length>64){const space=part.lastIndexOf(' ',63),cut=space>=15?space:64;result.push(part.slice(0,cut).trim());part=part.slice(cut).trim()}
  if(part)result.push(part)
 }
 return result.length?result:['']
}
