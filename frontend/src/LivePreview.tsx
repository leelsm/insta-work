import {useEffect,useRef,useState} from 'react'
import {Pause,Play,RotateCcw} from 'lucide-react'
import {customMusicPath,photoPath} from './api'
import {SubtitleDrag} from './SubtitleEditor'
import {captionParts,fadeOpacity,motionTransform,sceneAt} from './timeline'
import type {Project} from './types'

export function LivePreview({project,selected,onChange,disabled=false}:{project:Project;selected:number;onChange:(fields:Partial<Project>)=>void;disabled?:boolean}){
 const [time,setTime]=useState(0),[playing,setPlaying]=useState(false)
 const total=project.scenes.reduce((n,s)=>n+Math.max(.08,Number(s.duration)||2),0)
 const imageKey=(project.content_type==='daily'?project.photos.map(p=>p.asset_id):project.scenes.map(s=>s.image_asset_id)).filter(Boolean).join(',')
 useEffect(()=>{for(const id of imageKey.split(',').filter(Boolean)){const image=new Image();image.src=photoPath(id)}},[imageKey])
 const clock=useRef(0),audio=useRef<HTMLAudioElement>(null)
 const totalRef=useRef(total);totalRef.current=total
 useEffect(()=>{const next=project.scenes.slice(0,selected).reduce((n,s)=>n+s.duration,0);clock.current=next;setTime(next);setPlaying(false)},[selected,project.id])
 useEffect(()=>{clock.current=Math.min(clock.current,total);setTime(clock.current)},[total])
 useEffect(()=>{
  if(!playing)return
  let previous=performance.now(),frame=0
  function tick(now:number){clock.current=Math.min(totalRef.current,clock.current+Math.max(0,(now-previous)/1000));previous=now;setTime(clock.current);if(clock.current>=totalRef.current){setPlaying(false);return}frame=requestAnimationFrame(tick)}
  frame=requestAnimationFrame(tick);return()=>cancelAnimationFrame(frame)
 },[playing])
 const position=sceneAt(project.scenes,time),scene=project.scenes[position.index]
 const photo=project.content_type==='daily'?project.photos[position.index]:null
 const asset=photo?.asset_id||scene?.image_asset_id
 const parts=captionParts(scene?.narration||scene?.body||scene?.title||'')
 const text=project.content_type==='daily'?(scene?.narration||''):parts[Math.min(parts.length-1,Math.floor(position.elapsed/position.duration*parts.length))]
 const music=project.music_asset_id?customMusicPath(project.music_asset_id):(project.music_id?'/api/music/'+project.music_id:'')
 useEffect(()=>{const a=audio.current;if(!a)return;a.volume=project.music_volume??.35;if(playing)a.play().catch(()=>{});else a.pause()},[playing,music,project.music_volume])
 function seek(value:number){clock.current=value;setTime(value);const a=audio.current;if(a&&Number.isFinite(a.duration)&&a.duration>0)a.currentTime=((project.music_offset||0)+value)%a.duration}
 useEffect(()=>{seek(clock.current)},[music,project.music_offset,selected])
 if(!scene)return null
 return <><div className="preview-label">실시간 미리보기 <span>9:16</span></div>
 <div className={'live-preview '+project.template}>
  <div className="live-preview-frame" style={{opacity:playing?fadeOpacity(project.transition,position.elapsed,position.duration):1}}>
   {asset&&<img className="live-preview-photo" src={photoPath(asset)} alt={`장면 ${position.index+1} 미리보기`} style={{objectFit:photo?.fit==='contain'?'contain':'cover',objectPosition:`${(photo?.position_x??.5)*100}% ${(photo?.position_y??.5)*100}%`,transform:motionTransform(project.motion,position.elapsed/position.duration)}}/>}
   <SubtitleDrag project={project} text={text} onChange={onChange} variant={project.content_type} disabled={disabled||playing}/>
   {scene.image_author&&<div className="live-preview-credit">{scene.image_author} · {scene.image_license}</div>}
  </div>
 </div>
 <div className="live-preview-controls"><button type="button" className="btn" aria-label={playing?'미리보기 일시정지':'미리보기 재생'} onClick={()=>{if(!playing&&clock.current>=total)seek(0);setPlaying(!playing)}} disabled={disabled}>{playing?<Pause size={16}/>:<Play size={16}/>}</button><button type="button" className="icon-btn" aria-label="미리보기 처음부터" onClick={()=>seek(0)}><RotateCcw size={16}/></button><span>장면 {position.index+1}/{project.scenes.length} · {time.toFixed(1)} / {total.toFixed(1)}초</span></div>
 <input className="live-preview-seek" aria-label="미리보기 재생 위치" type="range" min={0} max={total} step={.01} value={time} onChange={e=>seek(Number(e.target.value))}/>
 <p className="preview-note">순서·자막·크기·움직임·전환이 바로 반영됩니다. 자막은 일시정지 후 끌어 옮기세요.{project.voice?' 음성 사용 시 최종 장면 길이는 음성 길이에 맞춰집니다.':''}</p>
 {music&&<audio ref={audio} src={music} loop preload="metadata" onLoadedMetadata={()=>seek(clock.current)}/>}</>
}
