import {Music2,Upload,Check} from 'lucide-react'
import {customMusicPath,uploadMusic} from './api'
import {Project} from './types'

type Runner=(name:string,fn:()=>Promise<unknown>)=>Promise<void>
export function MusicUpload({project,onChange,run,busy}:{project:Project;onChange:(fields:Partial<Project>)=>void;run:Runner;busy:string}){
 const selected=!!project.music_asset_id
 return <div className={'custom-music '+(selected?'selected':'')}>
  <div className="custom-music-head"><span className="custom-music-icon"><Music2 size={19}/></span><div><strong>내 음악 파일 첨부</strong><small>앱 제공 무료 음악 외에 직접 보유한 곡을 사용할 수 있어요.</small></div>{selected&&<Check size={17}/>}</div>
  <div className="custom-music-actions"><label className={'btn file-picker '+(busy?'disabled':'')}><Upload size={15}/>{selected?'다른 음악으로 바꾸기':'음악 파일 선택'}<input type="file" accept=".mp3,.m4a,.wav,audio/mpeg,audio/mp4,audio/wav" disabled={!!busy} onChange={e=>{const file=e.target.files?.[0];e.target.value='';if(file)void run('upload-music',async()=>{const saved=await uploadMusic(file);onChange({music_id:'',music_asset_id:saved.asset_id,music_filename:saved.filename,music_offset:0})})}}/></label>{selected&&<button type="button" className="text-btn" onClick={()=>onChange({music_id:'',music_asset_id:'',music_filename:''})}>첨부 해제</button>}</div>
  {selected&&<div className="custom-music-preview"><b title={project.music_filename}>{project.music_filename||'첨부 음악'}</b><audio controls src={customMusicPath(project.music_asset_id)} /></div>}
  <div className="custom-music-guide"><strong>어디서 첨부하나요?</strong><ol><li>영상 편집 화면에서 <b>배경음악</b> 영역을 찾습니다.</li><li><b>음악 파일 선택</b>을 눌러 MP3·M4A·WAV 파일을 고릅니다.</li><li>여기서 미리 듣고 음량을 조절한 뒤 <b>영상 만들기</b>를 누릅니다.</li></ol><p>25MB 이하 파일을 사용할 수 있습니다. 직접 제작했거나 영상 게시에 사용할 권한이 있는 음악을 선택하세요. 파일은 이 컴퓨터의 앱 데이터에 저장됩니다.</p></div>
 </div>
}
