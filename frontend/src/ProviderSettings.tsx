import {useEffect,useRef,useState} from 'react'
import {createPortal} from 'react-dom'
import {CheckCircle2,Plug,Sparkles,X} from 'lucide-react'
import {api} from './api'
import {Provider,Settings} from './types'
import {modelChoices,modelField} from './modelCatalog'
import {providerLabels,providerDescriptions} from './CreationModel'
export {providerLabels} from './CreationModel'
type Props={settings:Settings;refresh:()=>Promise<unknown>;run:(n:string,f:()=>Promise<unknown>)=>Promise<void>;busy:string;notify:(s:string)=>void}
const keyFields:Partial<Record<Provider,string>>={openai:'openai_key',anthropic:'anthropic_key',compatible:'compatible_key',freellmapi:'freellmapi_key'}
const endpointFields={compatible:'compatible_url',ollama:'ollama_url',freellmapi:'freellmapi_url'} as const
export function ProviderSettings({settings,refresh,run,busy,notify}:Props){
 const [editing,setEditing]=useState<Provider|null>(null),[values,setValues]=useState(settings),[secret,setSecret]=useState(''),[catalog,setCatalog]=useState<string[]>([]),[result,setResult]=useState('')
 async function perform(name:string,action:()=>Promise<unknown>){await run(name,async()=>{try{await action()}catch(e){const message=(e as Error).message;setResult(message);notify(message)}})}
 function edit(provider:Provider){setEditing(provider);setValues(settings);setSecret('');setCatalog([]);setResult('')}
 async function save(){
  if(!editing)return
  const key=keyFields[editing]
  const saved=await api<Settings>('/settings','PUT',{...values,llm_provider:settings.llm_provider,secrets:key&&secret.trim()?{[key]:secret.trim()}: {}})
  setValues(saved);setSecret('');await refresh();return saved
 }
 const p=editing,field=p?modelField(p):'model',key=p?keyFields[p]:undefined
 const endpoint=p&&p in endpointFields?endpointFields[p as keyof typeof endpointFields]:null
 return <><div className="page-heading"><div><div className="eyebrow">CONNECT YOUR AI</div><h1>AI 연결</h1><p>사용할 서비스를 한 번 연결하세요. 영상마다 제작 화면에서 자유롭게 선택할 수 있어요.</p></div></div>
 <div className="connection-intro"><Plug size={22}/><div><strong>연결 정보 입력 → 모델 선택 → 연결 테스트</strong><p>한 가지만 연결해도 시작할 수 있어요. 직접 자막을 작성하면 AI 연결 없이도 영상 제작이 가능합니다.</p></div></div>
 <div className="provider-cards">{(['openai','anthropic','opencode','freellmapi','ollama','compatible'] as Provider[]).map(provider=>{const row=settings.model_status.find(r=>r.provider===provider);if(!row)return null;const ready=!row.missing_fields.length&&!row.blocked;return <section className={'provider-card '+(row.selected?'is-default':'')} key={provider}><div className="provider-card-top"><span className={'provider-logo '+provider}>{provider==='openai'?'G':provider==='anthropic'?'C':provider==='opencode'?'OC':provider==='freellmapi'?'F':provider==='ollama'?'O':'API'}</span><span className={'connection-badge '+(ready&&row.test_result==='success'?'ready':'')}>{row.blocked?'사용 제한':!ready?'설정 필요':row.test_result==='success'?'연결 확인됨':row.test_result==='failed'?'연결 재확인':'테스트 전'}</span></div><h2>{providerLabels[provider]}</h2><p>{providerDescriptions[provider]}</p><div className="provider-saved-model"><small>저장된 모델</small><code>{row.model||'아직 선택하지 않았어요'}</code></div>{!!row.missing_fields.length&&<small className="provider-missing">필요한 항목: {row.missing_fields.join(' · ')}</small>}<div className="provider-card-actions"><button className="btn primary" disabled={!!busy} onClick={()=>edit(provider)}>{ready?'연결 설정':'연결하기'}</button><button className="btn" disabled={!!busy||!ready} onClick={()=>perform('test-'+provider,async()=>{try{notify((await api<{message:string}>('/settings/test/llm/'+provider,'POST')).message)}finally{await refresh()}})}>연결 테스트</button></div><button className="text-btn provider-default" disabled={!!busy||!ready||row.selected} onClick={()=>perform('default-ai',async()=>{await api('/settings','PUT',{...settings,llm_provider:provider});await refresh();notify('새 영상의 기본 AI를 변경했습니다.')})}>{row.selected?<><CheckCircle2 size={14}/>새 영상의 기본 AI</>:'기본 AI로 사용 →'}</button></section>})}</div>
 <p className="connection-footnote">AI는 대본·자막·게시 문안을 만듭니다. 영상 합성은 이 컴퓨터에서 진행합니다. 연결 테스트에는 소량의 사용료가 발생할 수 있습니다.</p>
 {p&&<ProviderModal busy={!!busy} onClose={()=>setEditing(null)}><div className="page-heading"><div><div className="eyebrow">CONNECT · {p.toUpperCase()}</div><h2 id="provider-dialog-title">{providerLabels[p]} 연결</h2><p>{providerDescriptions[p]}</p></div></div><fieldset disabled={!!busy}>
 {p==='opencode'&&<div className="setup-instructions"><strong>OpenCode 준비</strong><ol><li>이 컴퓨터에 OpenCode CLI를 설치합니다.</li><li>FreeLLMAPI를 사용하려면 먼저 FreeLLMAPI 카드에서 통합 키와 주소를 저장하세요.</li><li>모델에 <code>freellmapi/auto</code>를 입력하거나, OpenCode에 연결된 <code>provider/model</code>을 입력하세요.</li></ol><p>기존 연결은 터미널의 <code>opencode auth login</code>으로 준비할 수 있어요. 앱은 생성 요청마다 선택한 모델을 지정합니다.</p></div>}
 {p==='freellmapi'&&<div className="setup-instructions"><strong>FreeLLMAPI 준비</strong><p>FreeLLMAPI 서버를 실행하고 대시보드에서 AI 제공자 키를 등록한 다음, 발급된 통합 API 키를 아래에 입력하세요. 자동 선택은 게이트웨이에 연결된 모델을 사용합니다.</p></div>}
 {key&&<label>1. API 키 {settings.configured[key]&&<small>저장됨 · 변경할 때만 입력하세요</small>}<input type="password" autoComplete="new-password" value={secret} placeholder={settings.configured[key]?'저장된 키 유지':'서비스에서 발급받은 API 키'} onChange={e=>setSecret(e.target.value)}/>{p==='openai'&&<small>이 연결은 OpenAI API 키를 사용합니다. OpenCode의 기존 연결은 OpenCode 카드에서 설정하세요.</small>}</label>}
 {endpoint&&<label>서버 주소 · /v1 포함<input value={values[endpoint]} placeholder={p==='freellmapi'?'http://127.0.0.1:3001/v1':'https://서비스주소/v1'} onChange={e=>setValues({...values,[endpoint]:e.target.value})}/><small>{p==='freellmapi'?'내 컴퓨터 주소 또는 HTTPS 서버 주소를 사용할 수 있습니다. 로컬 주소여도 연결된 외부 AI로 자료가 전송됩니다.':p==='ollama'?'이 컴퓨터에서 실행 중인 Ollama 주소를 입력하세요.':'연결할 서비스에서 제공한 API 기본 주소를 입력하세요.'}</small></label>}
 <label>{key?'2. ':' '}모델 선택<input list="provider-model-options" value={values[field]} maxLength={100} onChange={e=>setValues({...values,[field]:e.target.value})} placeholder={p==='opencode'?'provider/model':'정확한 모델 ID'}/><datalist id="provider-model-options">{Array.from(new Set([...(modelChoices[p]||[]).map(m=>m.id),...catalog])).map(id=><option key={id} value={id}/>)}</datalist><small>사진 자막을 만들려면 이미지 입력을 지원하는 모델을 선택하세요.</small></label>
 <button className="btn" onClick={()=>perform('model-list',async()=>{await save();const data=await api<{models:string[]}>('/settings/models/'+p,'POST');setCatalog(data.models);setResult(`${data.models.length}개 모델을 불러왔습니다. 모델 입력란에서 선택하세요. 목록 조회와 생성 연결 테스트는 별도입니다.`)})}>저장 후 모델 목록 불러오기</button>
 {result&&<p className="connection-result" role="status">{result}</p>}
 <div className="connection-modal-actions"><button className="btn primary" disabled={!values[field].trim()} onClick={()=>perform('provider-test',async()=>{await save();try{const data=await api<{message:string}>('/settings/test/llm/'+p,'POST');setResult(data.message);notify(data.message)}finally{await refresh()}})}><Sparkles size={16}/>저장하고 연결 테스트</button><button className="btn" onClick={()=>perform('provider-save',async()=>{await save();setEditing(null);notify('AI 연결 설정을 저장했습니다.')})}>저장하고 닫기</button></div>
 {key&&settings.configured[key]&&<button className="text-btn" onClick={()=>{if(confirm('저장된 API 키를 삭제할까요?'))perform('key-delete',async()=>{const saved=await api<Settings>('/settings','PUT',{...settings,secrets:{[key]:''}});setValues(saved);setSecret('');await refresh();notify('키를 삭제했습니다.')})}}>저장된 키 삭제</button>}
 </fieldset></ProviderModal>}</>
}
function ProviderModal({children,busy,onClose}:{children:React.ReactNode;busy:boolean;onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null)
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.showModal();const overflow=document.body.style.overflow;document.body.style.overflow='hidden';return()=>{document.body.style.overflow=overflow;previous?.focus()}},[])
 return createPortal(<dialog className="connection-dialog" ref={dialog} aria-labelledby="provider-dialog-title" onCancel={e=>{e.preventDefault();if(!busy)onClose()}}><button type="button" className="icon-btn connection-close" aria-label="연결 설정 닫기" disabled={busy} onClick={onClose}><X size={22}/></button>{children}</dialog>,document.body)
}

export function ConnectionManager({onClose,...props}:Props&{onClose:()=>void}){
 const dialog=useRef<HTMLDialogElement>(null)
 useEffect(()=>{const previous=document.activeElement as HTMLElement|null;dialog.current?.showModal();return()=>{previous?.focus()}},[])
 return createPortal(<dialog ref={dialog} className="connection-dialog connection-manager" aria-label="AI 연결 관리" onCancel={e=>{e.preventDefault();if(!props.busy)onClose()}}><button className="btn connection-manager-back" disabled={!!props.busy} onClick={onClose}>완료 · 제작 화면으로 돌아가기</button><ProviderSettings {...props}/></dialog>,document.body)
}
export function PrivacySettings({settings,refresh,run,busy,notify}:Props){
 const [mode,setMode]=useState(settings.privacy_mode)
 return <><div className="page-heading"><div><div className="eyebrow">PRIVACY & STORAGE</div><h1>보안 · 로컬 저장</h1><p>외부 전송 여부를 직접 선택하세요.</p></div></div><section className="panel privacy-panel"><label>자료 전송 정책<select value={mode} onChange={e=>setMode(e.target.value as Settings['privacy_mode'])}><option value="cloud_ai">클라우드 AI 허용 · 영상은 로컬 보관</option><option value="local_only">로컬 전용 · 외부 API 차단</option></select></label><p>API 키: macOS Keychain / Windows Credential Manager에 저장합니다. 화면·프로젝트·백업에는 키를 포함하지 않습니다.</p><p>사진·영상·프로젝트: 내 컴퓨터에 저장합니다. 웹 서버는 127.0.0.1에만 연결하고 세션 인증을 요구합니다. 사진의 EXIF 위치 정보는 제거합니다.</p><p>클라우드 AI 허용: 생성할 자료와 축소 사진은 선택한 AI 업체에, 음성 텍스트는 OpenAI에 전송됩니다. 뉴스 검색어는 네이버에 전송됩니다. 인터넷에 공개 게시되지는 않지만 업체의 처리·보관 정책이 적용됩니다.</p><p>로컬 전용: 외부 AI·뉴스·음성·인스타그램 연결을 차단합니다. Ollama 또는 직접 편집으로 영상 제작이 가능합니다.</p><p className="info-note">영상 외부 업로드는 차단됩니다. 완성한 MP4를 내려받아 인스타그램에서 직접 게시하세요.</p><button className="btn primary" disabled={!!busy} onClick={()=>run('privacy',async()=>{await api('/settings','PUT',{...settings,privacy_mode:mode,allow_video_upload:false});await refresh();notify('보안 정책을 저장했습니다.')})}>보안 정책 저장</button></section></>
}
