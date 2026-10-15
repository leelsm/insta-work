import {Gauge} from 'lucide-react'
import {subtitleSpeed} from './readingSpeed'

const seconds=(value:number)=>`${Number(value.toFixed(1))}초`

export function SubtitleSpeedWarning({scenes,index,text,onApply,disabled=false}:{scenes:{duration:number}[];index:number;text:string;onApply:(duration:number)=>void;disabled?:boolean}){
 const speed=subtitleSpeed(scenes,index,text)
 if(!speed)return null
 const limited=speed.applicable!==null&&speed.applicable<speed.recommended
 return <div className="subtitle-speed-warning" role="status"><Gauge size={16}/><div><strong>자막이 빠릅니다</strong><span>읽기 편한 길이는 {seconds(speed.recommended)}예요. (현재 {seconds(speed.current)})</span>{speed.applicable===null?<small>장면당 30초·총 180초 한도로 더 늘릴 수 없어요. 자막을 줄이거나 다른 장면을 짧게 해 주세요.</small>:limited&&<small>장면당 30초·총 180초 한도로 {seconds(speed.applicable)}까지 늘릴 수 있어요.</small>}</div>{speed.applicable!==null&&<button type="button" className="btn" disabled={disabled} onClick={()=>onApply(speed.applicable!)}>{seconds(speed.applicable)}로 늘리기</button>}</div>
}
