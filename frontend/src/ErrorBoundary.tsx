import {Component,type ReactNode} from 'react'
export class ErrorBoundary extends Component<{children:ReactNode},{error:Error|null}>{
 state:{error:Error|null}={error:null}
 static getDerivedStateFromError(error:Error){return {error}}
 render(){if(this.state.error)return <main className="loading-screen" role="alert"><h2>화면을 표시하지 못했어요.</h2><p>저장한 콘텐츠와 완성 영상은 내 콘텐츠에서 다시 열 수 있습니다.</p><button className="btn primary" onClick={()=>location.reload()}>홈으로 돌아가기</button><details><summary>오류 정보</summary><pre>{this.state.error.message}</pre></details></main>;return this.props.children}
}
