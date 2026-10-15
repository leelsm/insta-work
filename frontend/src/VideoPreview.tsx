import {syncNativeReview} from './nativeReview'
import {useEffect,useId,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import {Maximize2,X} from 'lucide-react'
import './video.css'

export function VideoPreview({src,poster}:{src:string;poster?:string}){
 const [expanded,setExpanded]=useState(false)
 const inline=useRef<HTMLVideoElement>(null)
 useEffect(()=>{
  const sync=()=>{void syncNativeReview(true)}
  sync()
  window.addEventListener('pywebviewready',sync)
  return()=>{
   window.removeEventListener('pywebviewready',sync)
   void syncNativeReview(false)
  }
 },[])
 useEffect(()=>{
  function closeVideo(){
   inline.current?.pause()
   if(expanded)setExpanded(false)
   else window.dispatchEvent(new Event('studio-close-review'))
  }
  window.addEventListener('studio-close-video',closeVideo)
  return()=>window.removeEventListener('studio-close-video',closeVideo)
 },[expanded])
 return <><video ref={inline} controls controlsList="nofullscreen" disablePictureInPicture playsInline src={src} poster={poster} preload="none"/>
 <button type="button" className="btn video-expand" onClick={()=>{inline.current?.pause();setExpanded(true)}}><Maximize2 size={16}/>영상 크게 보기</button>
 {expanded&&<VideoDialog key={src} src={src} poster={poster} onClose={()=>setExpanded(false)}/>}</>
}

function VideoDialog({src,poster,onClose}:{src:string;poster?:string;onClose:()=>void}){
 const titleId=useId()
 const dialog=useRef<HTMLDivElement>(null)
 const close=useRef<HTMLButtonElement>(null)
 const video=useRef<HTMLVideoElement>(null)
 useEffect(()=>{
  const previous=document.activeElement as HTMLElement|null
  const overflow=document.body.style.overflow
  document.body.style.overflow='hidden'
  close.current?.focus()
  return()=>{document.body.style.overflow=overflow;previous?.focus()}
 },[])
 function dismiss(){video.current?.pause();onClose()}
 return createPortal(<div className="video-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)dismiss()}}>
  <div className="video-modal" ref={dialog} role="dialog" aria-modal="true" aria-labelledby={titleId} onKeyDown={e=>{
   if(e.key==='Escape'){e.preventDefault();e.stopPropagation();dismiss()}
   if(e.key==='Tab'){
    const elements=Array.from(dialog.current?.querySelectorAll<HTMLElement>('button,video')||[])
    const first=elements[0],last=elements.at(-1)
    if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}
    else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}
   }
  }}>
   <div className="video-modal-heading"><h2 id={titleId}>완성 영상 확인</h2><button type="button" ref={close} className="icon-btn" aria-label="영상 닫기" title="영상 닫기" onClick={dismiss}><X size={22}/></button></div>
   <video ref={video} tabIndex={0} controls controlsList="nofullscreen" disablePictureInPicture playsInline src={src} poster={poster} preload="none"/>
   <p>오른쪽 X 또는 Esc를 누르면 편집 화면으로 돌아갑니다.</p>
  </div>
 </div>,document.body)
}
