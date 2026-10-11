import {useEffect,useState} from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {BookOpen,Copy,Loader2} from 'lucide-react'
import {api} from './api'

type Manual={id:string;title:string;description:string}
type Document={id:string;title:string;markdown:string}
export function GuideReader({selected,onSelect}:{selected:string;onSelect:(id:string)=>void}){
 const [manuals,setManuals]=useState<Manual[]>([]),[doc,setDoc]=useState<Document|null>(null),[error,setError]=useState(''),[notice,setNotice]=useState(''),[loading,setLoading]=useState(true),[retry,setRetry]=useState(0)
 useEffect(()=>{let current=true;setLoading(true);setError('');setDoc(null);setNotice('');Promise.all([api<Manual[]>('/manuals'),api<Document>('/manuals/'+encodeURIComponent(selected))]).then(([list,content])=>{if(current){setManuals(list);setDoc(content)}}).catch(e=>{if(current)setError(e.message)}).finally(()=>{if(current)setLoading(false)});return()=>{current=false}},[selected,retry])
 const link=(href:string|undefined,children:React.ReactNode)=>{
  if(!href)return <span>{children}</span>
  const filename=href.split('#')[0].split('/').pop()||''
  if(manuals.some(m=>m.id===filename))return <button className="manual-link" onClick={()=>onSelect(filename)}>{children}</button>
  if(href.startsWith('#'))return <span>{children}</span>
  if(!/^https?:\/\//i.test(href))return <span>{children}</span>
  return <button className="manual-link external-reference" title={href} onClick={()=>navigator.clipboard.writeText(href).then(()=>setNotice('웹 주소를 복사했습니다. 브라우저 주소창에 붙여넣으세요.')).catch(()=>setNotice(href))}>{children}<Copy size={12}/><span className="sr-only"> 웹 주소 복사</span></button>
 }
 return <><div className="page-heading"><div><div className="eyebrow">STUDIO HELP</div><h1>사용 가이드</h1><p>문서를 앱 안에서 읽으세요. API 준비부터 영상 제작까지 안내합니다.</p></div></div><div className="manual-layout"><nav className="panel manual-index" aria-label="가이드 문서">{manuals.filter(m=>['USER_MANUAL.md','API_SETUP_GUIDE.md'].includes(m.id)).map(m=><button className={m.id===selected?'active':''} key={m.id} onClick={()=>onSelect(m.id)}><BookOpen size={16}/><span><strong>{m.title}</strong><small>{m.description}</small></span></button>)}</nav><section className="panel manual-document" aria-live="polite">{loading?<p className="manual-loading"><Loader2 className="spin" size={18}/>가이드를 불러오고 있어요.</p>:error?<div><p className="error-text">{error}</p><button className="btn" onClick={()=>setRetry(retry+1)}>다시 불러오기</button></div>:doc&&<><div className="panel-heading"><h2>{doc.title}</h2><span className="model-tag">앱 내 문서</span></div><p className="model-description">가이드는 앱에 포함된 로컬 파일입니다. 외부 사이트 주소는 클릭하면 복사됩니다.</p>{notice&&<p className="notice" role="status">{notice}</p>}<article className="markdown-content"><Markdown remarkPlugins={[remarkGfm]} skipHtml components={{a:({href,children})=>link(href,children),img:({alt})=><span>{alt||'이미지'}</span>}}>{doc.markdown}</Markdown></article></>}</section></div></>
}
