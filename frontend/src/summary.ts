import type {Scene} from './types'

const CARD_LIMIT=500,MAX_CARDS=5,MIN_CARD=120

// Split long sentences only at spaces; a run with no space at all is the only case cut at the limit.
function sentenceChunks(text:string){
 const chunks:string[]=[]
 for(let part of text.split(/(?<=[.!?。！？])\s+/)){
  part=part.trim()
  while(part.length>CARD_LIMIT){
   let cut=part.lastIndexOf(' ',CARD_LIMIT)
   if(cut<1)cut=CARD_LIMIT
   chunks.push(part.slice(0,cut).trim());part=part.slice(cut).trim()
  }
  if(part)chunks.push(part)
 }
 return chunks
}

export function summaryScenes(text:string):Scene[]{
 const chunks=sentenceChunks(text.replace(/\s+/g,' ').trim())
 const total=chunks.reduce((n,c)=>n+c.length,0)
 // Short texts stay on one card; longer ones spread evenly across at most five cards.
 const target=Math.max(MIN_CARD,Math.ceil(total/Math.min(MAX_CARDS,Math.max(1,chunks.length))))
 const parts:string[]=[]
 let current=''
 for(const chunk of chunks){
  const joined=current?current+' '+chunk:chunk
  const last=parts.length===MAX_CARDS-1
  if(current&&(joined.length>CARD_LIMIT||(!last&&current.length+chunk.length/2>target))){
   // The last card keeps filling up to the limit; only text past five full cards is dropped.
   if(last)break
   parts.push(current)
   current=chunk
  }else current=joined
 }
 if(current)parts.push(current)
 if(!parts.length)parts.push('')
 return parts.map((body,i)=>{
  const phrase=body.split(/(?<=[.!?。！？])\s+/)[0]||body
  const title=phrase.length>32?phrase.slice(0,31).replace(/\s+\S*$/,'')+'…':phrase
  const duration=Math.min(10,Math.max(4,Math.round(body.length/9)))
  return {title:title||`핵심 요약 ${i+1}`,body,narration:body,duration,source_ids:[0],image_search_query:''}
 })
}
