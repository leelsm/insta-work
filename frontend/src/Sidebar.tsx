import {LayoutDashboard,Layers3,Activity,Plus,Newspaper,Images,Settings2,Instagram,ShieldCheck,Download,BookOpen,ChevronDown,Clapperboard,LogOut} from 'lucide-react'
import {NavGroup,Settings} from './types'
export const menuGroups=[
 {id:'workspace' as NavGroup,label:'워크스페이스',icon:LayoutDashboard,items:[['home','시작하기',LayoutDashboard],['projects','내 콘텐츠',Layers3],['jobs','작업 이력',Activity]]},
 {id:'content' as NavGroup,label:'콘텐츠 만들기',icon:Plus,items:[['discover','뉴스 카드뉴스',Newspaper],['daily','일상 영상',Images]]},
 {id:'api' as NavGroup,label:'연결',icon:Settings2,items:[['settings-ai','AI 연결',Settings2],['settings-services','뉴스 검색 · AI 음성',Newspaper]]},
 {id:'accounts' as NavGroup,label:'계정 설정',icon:Instagram,items:[['settings-accounts','인스타그램 계정',Instagram]]},
 {id:'preferences' as NavGroup,label:'앱 설정',icon:ShieldCheck,items:[['settings-security','보안 · 로컬 저장',ShieldCheck],['settings-backup','백업 · 진단',Download]]},
 {id:'help' as NavGroup,label:'도움말',icon:BookOpen,items:[['guide','사용 가이드',BookOpen]]},
]
export const menuLabel=(nav:string)=>menuGroups.flatMap(g=>g.items).find(i=>i[0]===nav)?.[1] as string|undefined
export function Sidebar({settings,nav,projectCount,onNavigate,onShutdown}:{settings:Settings;nav:string;projectCount:number;onNavigate:(id:string)=>void;onAppearance:(changes:{nav_collapsed?:boolean;nav_groups?:Partial<Record<NavGroup,boolean>>})=>void;onShutdown:()=>void;busy:boolean}){
 const connected=settings.model_status.filter(r=>!r.blocked&&!r.missing_fields.length&&r.test_result==='success').length
 const item=(id:string,label:string,Icon:typeof LayoutDashboard)=> <button key={id} title={label} aria-current={nav===id||(nav==='editor'&&id==='projects')?'page':undefined} className={'nav-item '+(nav===id||(nav==='editor'&&id==='projects')?'active':'')} onClick={()=>onNavigate(id)}><Icon size={19}/><span>{label}</span>{id==='projects'&&<small className="nav-count">{projectCount}</small>}</button>
 return <aside className="sidebar studio-sidebar"><div className="sidebar-brand-row"><div className="brand"><div className="brand-mark"><Clapperboard size={22}/></div><div className="brand-name">콘텐츠 스튜디오<small>CONTENT STUDIO</small></div></div></div>
 <button className="sidebar-create" title="새 영상 만들기" onClick={()=>onNavigate('create')}><Plus size={20}/><span>새 영상 만들기</span></button>
 <nav className="studio-nav" aria-label="주 메뉴"><div className="nav-section-label">스튜디오</div>{item('home','홈',LayoutDashboard)}{item('projects','내 콘텐츠',Layers3)}{item('jobs','작업 이력',Activity)}
 <div className="nav-section-label">만들기</div>{item('daily','사진으로 영상',Images)}{item('discover','글·뉴스로 영상',Newspaper)}
 <div className="nav-section-label">연결 및 설정</div>{item('settings-ai','AI 연결',Settings2)}{item('settings-services','뉴스 검색 · AI 음성',Newspaper)}
 <details className="sidebar-more"><summary title="앱 설정"><ShieldCheck size={19}/><span>앱 설정</span><ChevronDown size={14}/></summary>{item('settings-security','보안 · 로컬 저장',ShieldCheck)}{item('settings-backup','백업 · 진단',Download)}{item('settings-accounts','인스타그램 계정',Instagram)}</details>
 {item('guide','사용 가이드',BookOpen)}</nav>
 <div className="side-bottom"><button className="sidebar-connection" title="AI 연결 관리" onClick={()=>onNavigate('settings-ai')}><span className={'connection-light '+(connected?'connected':'')}/><span><strong>{connected?`AI ${connected}개 연결됨`:'AI 연결을 시작하세요'}</strong><small>내 컴퓨터에 안전하게 저장</small></span></button><button className="nav-item shutdown-item" title="스튜디오 종료" aria-label="스튜디오 종료" onClick={onShutdown}><LogOut size={17}/><span>스튜디오 종료</span></button><div className="version"><span>CONTENT STUDIO · 새 작업 공간</span></div></div></aside>
}
