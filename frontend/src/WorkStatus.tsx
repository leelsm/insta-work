import {Clapperboard,Loader2,Sparkles,Upload} from 'lucide-react'
import {Job} from './types'

const titles:Record<string,string>={generate:'AI 초안 생성 중',render:'영상 제작 중',publish:'게시 요청 처리 중'}
const busyTitles:Record<string,string>={'generate-scene':'선택한 사진의 AI 자막을 추천하는 중',generate:'AI 초안 작업을 시작하는 중',render:'영상 제작을 준비하는 중','create-daily':'일상 영상 초안을 만드는 중',upload:'파일을 첨부하는 중','upload-music':'음악을 첨부하는 중','upload-font':'폰트를 첨부하는 중',save:'변경사항 저장 중',sample:'예시 콘텐츠 준비 중'}

export function WorkStatus({job,busy,onCancel}:{job?:Job;busy:string;onCancel?:(job:Job)=>void}){
 const local=!job&&busyTitles[busy]
 if(!job&&!local)return null
 const title=job?(job.kind==='generate'&&job.scene_index!=null?`장면 ${job.scene_index+1} AI 자막 추천 중`:(titles[job.kind]||'작업 진행 중')):String(local)
 const value=Math.max(0,Math.min(100,job?.progress||0))
 const Icon=job?.kind==='render'?Clapperboard:busy.startsWith('upload')?Upload:job?.kind==='generate'?Sparkles:Loader2
 return <div className="work-status" role="status" aria-live="polite" aria-atomic="true">
  <div className="work-status-icon"><Icon size={20} className={job?.kind==='generate'||!job?'spin-slow':''}/></div>
  <div className="work-status-body"><strong>{title}</strong><span>{job?.message||'작업을 준비하고 있습니다. 잠시만 기다려 주세요.'}</span><div className={'work-status-progress '+(!job?'indeterminate':'')} role="progressbar" aria-label={title} aria-valuemin={0} aria-valuemax={100} aria-valuenow={job?value:undefined}><i style={job?{width:`${value}%`}:undefined}/></div></div>
  <div className="work-status-end">{job&&<b>{value}%</b>}{job&&onCancel&&<button className="btn" onClick={()=>onCancel(job)}>작업 중단</button>}</div>
 </div>
}
