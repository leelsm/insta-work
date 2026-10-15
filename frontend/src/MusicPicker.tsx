import {useEffect,useRef,useState} from 'react'
import {Check,Music2,Play,Volume2,Copy} from 'lucide-react'
import {Project} from './types'
import {musicCredit,musicMoods,musicTracks,postingCaption,recommendedMusic} from './music'

export function MusicPicker({project,onChange}:{project:Project;onChange:(fields:Partial<Project>)=>void}) {
 const [audio,setAudio]=useState(''),[expanded,setExpanded]=useState(false)
 const player=useRef<HTMLAudioElement>(null)
 useEffect(()=>{setAudio('');setExpanded(false)},[project.id,project.mood,project.music_id,project.music_asset_id])
 useEffect(()=>{if(player.current)player.current.volume=project.music_volume??.35},[audio,project.music_volume])
 const recommended=recommendedMusic(project.mood||'일상')
 const selected=musicTracks.find(t=>t.id===project.music_id)
 const tracks=expanded?musicTracks:[...recommended,...(selected&&!recommended.some(t=>t.id===selected.id)&&!project.music_asset_id?[selected]:[])]
 return <div className="bgm-picker">
  <label>배경음악 분위기<select value={project.mood||'일상'} onChange={e=>onChange({mood:e.target.value})}>{musicMoods.map(m=><option key={m}>{m}</option>)}</select></label>
  <p className="muted">{project.mood||'일상'}에 어울리는 BGM {recommended.length}곡 · 선택한 한 곡이 영상에 들어갑니다.</p>
  <div className="music-options">
   <button type="button" className={'music-option '+(!project.music_id&&!project.music_asset_id?'selected':'')} onClick={()=>onChange({music_id:'',music_asset_id:'',music_filename:''})}><Volume2 size={22}/><b>음악 없이</b><small>사진과 문장에 집중</small></button>
   {tracks.map(t=><div className={'music-option '+(project.music_id===t.id&&!project.music_asset_id?'selected':'')} key={t.id}>
    <button type="button" className="music-select" onClick={()=>onChange({music_id:t.id,music_asset_id:'',music_filename:'',music_offset:0})}><span className="track-art"><Music2 size={22}/></span><b>{t.title}</b><small>{t.mood} · {t.bpm} BPM</small><span className="track-license">{recommended.some(r=>r.id===t.id)?'추천 · ':''}{t.license}</span>{project.music_id===t.id&&!project.music_asset_id&&<Check size={16} className="track-check"/>}</button>
    <button type="button" className="text-btn" onClick={()=>setAudio(audio===t.id?'':t.id)}><Play size={13}/>{audio===t.id?'미리듣기 닫기':'미리듣기'}</button>
    {t.reference_url&&<a href={t.reference_url} target="_blank" rel="noreferrer">채널에서 듣기 ↗</a>}
   </div>)}
  </div>
  <button type="button" className="text-btn" onClick={()=>setExpanded(!expanded)}>{expanded?'추천곡만 보기':`전체 ${musicTracks.length}곡 보기 · 오리지널 포함`}</button>
  {audio&&<audio key={audio} ref={player} controls autoPlay src={'/api/music/'+audio} onLoadedMetadata={()=>{const a=player.current;if(a){a.volume=project.music_volume??.35;if(a.duration>0)a.currentTime=(project.music_offset||0)%a.duration}}}/>}
  <p className="bgm-source">참고: <a href={catalogChannel} target="_blank" rel="noreferrer">YouTube Audio Library 채널</a> · 음원은 제작자의 공식 배포본을 제공합니다. CC BY 곡은 게시 문안에 출처를 함께 넣어주세요.</p>
 </div>
}
const catalogChannel='https://www.youtube.com/channel/UCBjfXxHdjTdSOZ3fGqt_i-w'

export function MusicCredit({project}:{project:Project}) {
 const [message,setMessage]=useState('')
 const credit=musicCredit(project),caption=postingCaption(project)
 return <div className="bgm-credit">
  {credit&&<><strong>선택한 BGM 출처 · 게시 문안에 포함</strong><pre>{credit}</pre></>}
  <button type="button" className="text-btn" onClick={()=>navigator.clipboard.writeText(caption).then(()=>setMessage('게시 문안과 음악 출처를 복사했어요.')).catch(()=>setMessage('아래 문안을 직접 선택해 복사해주세요.'))}><Copy size={14}/>{credit?'문안 + 음악 출처 복사':'게시 문안 복사'}</button>
  <small role="status">{message}</small>
  {caption.length>2200&&<p className="privacy-note">출처 포함 {caption.length}자입니다. 인스타그램에 게시하려면 본문을 줄여 2200자 이하로 맞춰주세요.</p>}
  {message==='아래 문안을 직접 선택해 복사해주세요.'&&<textarea readOnly rows={6} value={caption} aria-label="출처 포함 게시 문안"/>}
 </div>
}
