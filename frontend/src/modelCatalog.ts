import {Settings} from './types'

export type ModelChoice={id:string;name:string;note:string;recommended?:boolean}

export const modelChoices:Partial<Record<Settings['llm_provider'],ModelChoice[]>>={
 freellmapi:[{id:'auto',name:'자동 선택',note:'게이트웨이에 연결된 모델 사용'},{id:'auto:fast',name:'빠른 응답 우선',note:'FreeLLMAPI 자동 라우팅'}],
 opencode:[{id:'freellmapi/auto',name:'FreeLLMAPI 자동 선택',note:'FreeLLMAPI 연결 필요'}],
 openai:[{id:'gpt-5.6-terra',name:'GPT-5.6 Terra',note:'균형형 · 콘텐츠 초안 추천',recommended:true},{id:'gpt-5.6-luna',name:'GPT-5.6 Luna',note:'저비용 · 빠른 응답'},{id:'gpt-5.6-sol',name:'GPT-5.6 Sol',note:'복잡한 추론 · 고품질'},{id:'gpt-6-astra',name:'GPT-6 Astra',note:'최고 성능 · 비용이 높을 수 있음'}],
 anthropic:[{id:'claude-sonnet-5-5',name:'Claude Sonnet 5.5',note:'속도와 품질 균형 · 추천',recommended:true},{id:'claude-haiku-4-5-20251001',name:'Claude Haiku 4.5',note:'빠른 응답 · 비용 절감'},{id:'claude-opus-5-5',name:'Claude Opus 5.5',note:'복잡한 작업 · 높은 성능'},{id:'claude-fable-5-1',name:'Claude Fable 5.1',note:'긴 추론·다단계 작업'}],
 ollama:[{id:'qwen3-vl:4b',name:'Qwen3-VL 4B',note:'비전 지원 · 비교적 가벼움'},{id:'qwen3-vl:8b',name:'Qwen3-VL 8B',note:'비전 지원 · 로컬 추천',recommended:true},{id:'qwen3-vl:30b',name:'Qwen3-VL 30B',note:'비전 지원 · 메모리 여유 필요'}],
 compatible:[{id:'openai/gpt-5.6-terra',name:'OpenAI GPT-5.6 Terra',note:'OpenRouter 모델 ID · 균형형',recommended:true},{id:'anthropic/claude-sonnet-5-5',name:'Claude Sonnet 5.5',note:'OpenRouter 모델 ID · 균형형'},{id:'google/gemini-2.5-flash',name:'Google Gemini 2.5 Flash',note:'OpenRouter 모델 ID · 이미지 지원'}]
}

export const modelField=(provider:Settings['llm_provider'])=>({openai:'model',anthropic:'anthropic_model',ollama:'ollama_model',compatible:'compatible_model',freellmapi:'freellmapi_model',opencode:'opencode_model'} as const)[provider]
