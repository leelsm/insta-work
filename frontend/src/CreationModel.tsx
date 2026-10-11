import {useId,useState} from 'react'
import {Sparkles,Settings2,RefreshCw,ChevronDown} from 'lucide-react'
import {api} from './api'
import {Provider,Settings} from './types'
import {modelChoices,modelField} from './modelCatalog'

export type AIChoice={provider:Provider|'manual';model:string}
export function connectionMissing(settings:Settings,choice:AIChoice){
 if(choice.provider==='manual')return []
 const row=settings.model_status.find(r=>r.provider===choice.provider)
 const missing=(row?.missing_fields||[]).filter(field=>!['모델 이름','provider/model 형식','FreeLLMAPI 주소','FreeLLMAPI 키'].includes(field))
 if(!choice.model.trim())missing.push('모델 이름')
 if(choice.provider==='opencode'){
  if(!/^[^/\s]+\/\S+$/.test(choice.model))missing.push('provider/model 형식')
  if(choice.model.startsWith('freellmapi/')){
   if(!settings.configured.freellmapi_key)missing.push('FreeLLMAPI 키')
   if(!settings.freellmapi_url.trim())missing.push('FreeLLMAPI 주소')
  }
 }
 return missing
}
export const providerLabels:Record<Provider,string>={openai:'ChatGPT · OpenAI API',anthropic:'Claude',opencode:'OpenCode',freellmapi:'FreeLLMAPI',compatible:'OpenAI 호환 API',ollama:'로컬 Ollama'}
export const providerDescriptions:Record<Provider,string>={openai:'OpenAI API 키로 대본과 자막을 만듭니다.',anthropic:'Claude API 키로 대본과 게시 문안을 만듭니다.',opencode:'이 컴퓨터의 OpenCode에 연결된 모델을 사용합니다.',freellmapi:'여러 AI를 연결한 게이트웨이의 통합 키를 사용합니다.',compatible:'OpenRouter 등 호환 서비스에 연결합니다.',ollama:'이 컴퓨터에 설치한 모델을 사용합니다.'}
export function CreationModel({settings,choice,onChange,onSettings,disabled=false,photos=false}:{settings:Settings;choice:AIChoice;onChange:(choice:AIChoice)=>void;onSettings:()=>void;disabled?:boolean;photos?:boolean}){
 const id=useId(),[catalog,setCatalog]=useState<string[]>([]),[loading,setLoading]=useState(false),[error,setError]=useState('')
 const row=settings.model_status.find(r=>r.provider===choice.provider)
 const choices=choice.provider==='manual'?[]:modelChoices[choice.provider]||[]
 const missing=connectionMissing(settings,choice)
 const ready=!!row&&!row.blocked&&!missing.length
 return <details className="creation-assistant"><summary><Sparkles size={18}/><span><strong>{choice.provider==='manual'?'직접 만들기':providerLabels[choice.provider]}</strong><small>{choice.provider==='manual'?'AI 없이 자막과 내용을 직접 작성해요':choice.model}</small></span><span className={'assistant-status '+(!ready&&choice.provider!=='manual'?'needs-setup':'')}>{choice.provider==='manual'?'AI 선택 가능':!ready?'연결 설정 필요':'이번 영상의 AI'}</span><span className="assistant-change">변경<ChevronDown size={15}/></span></summary><section className="creation-model" aria-label="이번 영상의 AI 선택"><div className="creation-model-heading"><div className="assistant-icon"><Sparkles size={20}/></div><div><strong>이번 영상은 누구와 만들까요?</strong><p>AI가 대본·자막을 준비하고, 앱이 사진·카드를 영상으로 완성해요.</p></div><button type="button" className="text-btn" onClick={onSettings}><Settings2 size={16}/>AI 연결 관리</button></div>
 <div className="creation-model-fields"><label>AI 서비스<select disabled={disabled||loading} value={choice.provider} onChange={e=>{const provider=e.target.value as AIChoice['provider'];setCatalog([]);setError('');onChange({provider,model:provider==='manual'?'':settings[modelField(provider)]})}}><option value="manual">직접 만들기 · AI 없이</option>{settings.model_status.map(r=><option value={r.provider} key={r.provider}>{providerLabels[r.provider]}{r.blocked?' · 사용 제한':r.missing_fields.length?' · 연결 필요':r.test_result==='success'?' · 연결 확인됨':' · 연결 테스트 권장'}</option>)}</select></label>
 {choice.provider!=='manual'&&<><label>사용할 모델<input list={id} disabled={disabled||loading} value={choice.model} placeholder={choice.provider==='opencode'?'예: freellmapi/auto':'모델 ID를 선택하거나 입력하세요'} maxLength={100} onChange={e=>onChange({...choice,model:e.target.value})}/><datalist id={id}>{Array.from(new Set([row?.model||'',...choices.map(c=>c.id),...catalog])).filter(Boolean).map(model=><option key={model} value={model}/>)}</datalist></label><button className="btn" disabled={disabled||loading||!ready} onClick={async()=>{if(choice.provider==='manual')return;setLoading(true);setError('');try{const data=await api<{models:string[]}>(`/settings/models/${choice.provider}`,'POST');setCatalog(data.models);if(!data.models.length)setError('사용 가능한 모델 목록이 비어 있습니다. 모델 ID를 직접 입력하세요.')}catch(e){setError((e as Error).message)}finally{setLoading(false)}}}><RefreshCw size={15} className={loading?'spin':''}/>{loading?'불러오는 중':'모델 목록 불러오기'}</button></>}
 </div>{choice.provider==='manual'?<p className="creation-model-note">API 연결 없이 시작합니다. 내용과 자막을 직접 쓰고 영상을 만들 수 있어요.</p>:<p className={'creation-model-note '+(!ready?'needs-setup':'')}>{!ready?<>{row?.blocked?'로컬 전용 설정으로 차단되어 있습니다.':`연결이 필요해요: ${missing.join(' · ')||'서비스 설정'}.`} <button className="text-btn" onClick={onSettings}>연결하기 →</button></>:<>선택한 모델로 생성 자료{photos?'와 사진':''}를 보냅니다. {photos?'사진 자막에는 이미지 입력을 지원하는 모델을 선택하세요. ':''}{row?.test_result==='failed'?'최근 연결 테스트에 실패했습니다. 연결을 다시 확인하세요.':'사용 요금과 한도는 연결한 서비스 기준입니다.'}</>}</p>}{catalog.length>0&&<p className="creation-model-note" role="status">모델 {catalog.length}개를 불러왔습니다. 모델 입력란에서 선택하세요. 목록 조회는 생성·사진 입력 지원을 보장하지 않습니다.</p>}{error&&<p className="error-text" role="alert">{error}</p>}
 </section></details>
}
