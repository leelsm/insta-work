import {Check,Image as ImageIcon} from 'lucide-react'
import {photoPath} from './api'
import {Project} from './types'
export function ThumbnailPicker({project,onChange}:{project:Project;onChange:(fields:Partial<Project>)=>void}){
 const selected=project.thumbnail_scene??0
 return <section className="thumbnail-picker" aria-label="영상 썸네일 선택"><div className="panel-heading"><h3><ImageIcon size={17}/>영상 썸네일</h3><span className="badge">장면 {selected+1} 선택됨</span></div><p className="muted">대표 이미지로 사용할 장면을 선택하세요. 완성한 썸네일 JPG도 함께 저장할 수 있어요.</p><div className="thumbnail-options">{project.scenes.map((scene,i)=>{
 const asset=project.content_type==='daily'?project.photos[i]?.asset_id:scene.image_asset_id
 return <button type="button" key={i} className={selected===i?'selected':''} aria-label={`장면 ${i+1} 썸네일로 선택`} aria-pressed={selected===i} onClick={()=>onChange({thumbnail_scene:i})}>{asset?<img src={photoPath(asset)} alt=""/>:<span className="thumbnail-text">{scene.title}</span>}<span>장면 {i+1}{selected===i&&<Check size={13}/>}</span></button>
 })}</div></section>
}
