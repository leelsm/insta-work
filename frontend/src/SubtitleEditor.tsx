import {useEffect,useRef,useState} from 'react'
import {Type,Upload,Move} from 'lucide-react'
import {api,fontPath,uploadFont} from './api'
import {Project} from './types'

type Runner=(name:string,fn:()=>Promise<unknown>)=>Promise<void>

export function useSubtitleFont(id?:string){
 const [family,setFamily]=useState('')
 useEffect(()=>{
  if(!id){setFamily('');return}
  let active=true
  const name='StudioSubtitle'+id
  const face=new FontFace(name,`url(${fontPath(id)})`)
  face.load().then(loaded=>{if(active){document.fonts.add(loaded);setFamily(name)}}).catch(()=>{if(active)setFamily('')})
  return()=>{active=false}
 },[id])
 return family
}

export function SubtitleControls({project,onChange,run,busy}:{project:Project;onChange:(fields:Partial<Project>)=>void;run:Runner;busy:string}){
 const [fonts,setFonts]=useState<{asset_id:string;name:string;note:string;noonnu_url:string}[]>([])
 const [error,setError]=useState('')
 const family=useSubtitleFont(project.subtitle_font_id)
 useEffect(()=>{let active=true;api<{fonts:typeof fonts}>('/fonts/library').then(data=>{if(active)setFonts(data.fonts)}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[])
 const preset=fonts.find(font=>font.asset_id===project.subtitle_font_id)
 return <div className="subtitle-controls"><div className="subtitle-controls-title"><Type size={17}/><strong>자막 폰트와 위치</strong></div>
  <label>자막 폰트<select aria-label="자막 폰트 선택" disabled={!!busy} value={project.subtitle_font_id?(preset?.asset_id||'__custom__'):''} onChange={e=>{if(e.target.value==='__custom__')return;const font=fonts.find(font=>font.asset_id===e.target.value);onChange({subtitle_font_id:font?.asset_id||'',subtitle_font_name:font?.name||''})}}><option value="">기본 한글 폰트</option>{fonts.map(font=><option value={font.asset_id} key={font.asset_id}>{font.name} · {font.note}</option>)}{project.subtitle_font_id&&!preset&&<option value="__custom__">내 폰트 · {project.subtitle_font_name}</option>}</select></label>
  <label>폰트 크기 · {project.subtitle_size??50}px<input aria-label="자막 폰트 크기" type="range" min={24} max={96} step={2} value={project.subtitle_size??50} disabled={!!busy} onChange={e=>onChange({subtitle_size:Number(e.target.value)})}/></label>
  <div className="form-row"><label>사진 움직임<select aria-label="사진 움직임" value={project.motion??'zoom'} onChange={e=>onChange({motion:e.target.value as Project['motion']})}><option value="still">정지</option><option value="zoom">서서히 확대</option><option value="zoom-out">서서히 축소</option><option value="pan-left">왼쪽으로 이동</option><option value="pan-right">오른쪽으로 이동</option></select></label><label>장면 전환<select aria-label="장면 전환" value={project.transition??'fade'} onChange={e=>onChange({transition:e.target.value as Project['transition']})}><option value="cut">바로 전환</option><option value="fade">자연스럽게 겹치기 (크로스페이드)</option></select></label></div>
  <div className="subtitle-font-sample" style={{fontFamily:family||undefined}}>오늘의 이야기를 영상으로 담아보세요.</div>
  {preset&&<small>{preset.note} · 무료 · 영상 사용 가능</small>}
  {error&&<p className="error-text">{error}</p>}
  <p>다운로드한 TTF·OTF 폰트를 첨부하거나 기본 폰트를 사용하세요. 미리보기의 자막을 마우스로 끌어 원하는 곳에 놓을 수 있어요.</p>
  <div className="subtitle-controls-actions"><label className={'btn file-picker '+(busy?'disabled':'')}><Upload size={15}/>{project.subtitle_font_id?'다른 폰트 선택':'폰트 파일 선택'}<input type="file" accept=".ttf,.otf,font/ttf,font/otf" disabled={!!busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void run('upload-font',async()=>{const saved=await uploadFont(file);onChange({subtitle_font_id:saved.asset_id,subtitle_font_name:saved.filename})})}}/></label>{project.subtitle_font_id&&<button type="button" className="text-btn" onClick={()=>onChange({subtitle_font_id:'',subtitle_font_name:''})}>기본 폰트로</button>}</div>
  <small>{project.subtitle_font_id?`사용 중: ${project.subtitle_font_name||'첨부 폰트'}`:'사용 중: 기본 한글 폰트'} · 20MB 이하 · 영상 게시에 사용할 수 있는 폰트를 선택하세요.</small>
 </div>
}

export function SubtitleDrag({project,text,onChange,variant='daily',disabled=false}:{project:Project;text:string;onChange:(fields:Partial<Project>)=>void;variant?:'daily'|'news';disabled?:boolean}){
 const stage=useRef<HTMLDivElement>(null)
 const grab=useRef({x:0,y:0})
 const family=useSubtitleFont(project.subtitle_font_id)
 const y=project.subtitle_y??(variant==='daily'?(project.subtitle_position==='center'?.5:.76):.79)
 function update(clientX:number,clientY:number,element:HTMLElement){
  const bounds=stage.current?.getBoundingClientRect();if(!bounds)return
  const halfX=element.offsetWidth/2,halfY=element.offsetHeight/2
  const x=Math.max(halfX+5,Math.min(bounds.width-halfX-5,clientX-grab.current.x-bounds.left))
  const nextY=Math.max(halfY+5,Math.min(bounds.height-halfY-5,clientY-grab.current.y-bounds.top))
  onChange({subtitle_x:x/bounds.width,subtitle_y:nextY/bounds.height})
 }
 return <div className={'subtitle-drag-stage '+variant} ref={stage}>
  {!!text.trim()&&<div className={'subtitle-drag-text '+project.subtitle_style} style={{left:`${(project.subtitle_x??.5)*100}%`,top:`${y*100}%`,fontFamily:family||undefined,fontSize:`${(project.subtitle_size??50)/10.8}cqw`}} role="button" tabIndex={disabled?-1:0} aria-label="자막 위치 이동" title="드래그해서 자막 위치 변경" onPointerDown={e=>{if(disabled)return;e.preventDefault();const bounds=stage.current?.getBoundingClientRect();if(!bounds)return;grab.current={x:e.clientX-(bounds.left+(project.subtitle_x??.5)*bounds.width),y:e.clientY-(bounds.top+y*bounds.height)};e.currentTarget.setPointerCapture(e.pointerId)}} onPointerMove={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))update(e.clientX,e.clientY,e.currentTarget)}} onPointerUp={e=>{if(e.currentTarget.hasPointerCapture(e.pointerId))e.currentTarget.releasePointerCapture(e.pointerId)}} onKeyDown={e=>{if(disabled)return;const step=e.shiftKey?.03:.01;if(e.key==='ArrowLeft')onChange({subtitle_x:Math.max(0,(project.subtitle_x??.5)-step)});else if(e.key==='ArrowRight')onChange({subtitle_x:Math.min(1,(project.subtitle_x??.5)+step)});else if(e.key==='ArrowUp')onChange({subtitle_y:Math.max(0,y-step)});else if(e.key==='ArrowDown')onChange({subtitle_y:Math.min(1,y+step)});else return;e.preventDefault()}}><span className="subtitle-drag-handle"><Move size={12}/></span>{text}</div>}
 </div>
}
