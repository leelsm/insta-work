# API 발급 · 계정 준비

직접 자료·자막을 작성하고 영상을 저장하는 데는 API 키가 필요하지 않습니다. 자동 초안, 사진 자막, 뉴스 검색, 음성을 사용할 때만 해당 서비스를 준비하세요. 외부 사이트 주소 버튼은 주소를 복사합니다. 브라우저에 붙여넣어 공식 페이지를 열고 키를 발급하세요.

## 2. 네이버 뉴스 검색 API 발급

2026년 7월 31일부터 검색 API 신규 신청은 NAVER Cloud Platform의 NAVER API HUB에서만 가능하다. 기존 개발자센터 키는 기존 신청자에 한해 2027년 6월 30일까지 지원된다.

1. [네이버 클라우드 콘솔](https://console.ncloud.com/)에 로그인한다. 네이버 개발자센터 로그인과 별도 계정 준비가 필요할 수 있다.
2. `Menu → Application Services → NAVER API HUB`를 연다.
3. 서비스 이용 신청에서 이용약관·개인정보 제공 안내와 현재 요금을 직접 확인하고 동의한다. 결제 수단이 필요하면 사용자가 직접 등록한다.
4. `Application → Application 등록`에서 **뉴스**만 선택하고 다음을 누른다.
5. 앱 이름 `ContentStudio`를 입력하고 완료한다. 새 API 접근 자격 증명이 생성된다.
6. 등록 앱의 `인증 정보`에서 Client ID와 Client Secret을 복사한다.
7. 앱의 `연결 → 뉴스 검색 · AI 음성`에서 발급 서비스를 **NAVER API HUB**로 선택하고 두 키를 저장한다.
8. `연결 테스트` 후 콘텐츠 찾기에서 검색한다. 검색 정렬은 정확도순·날짜순이며 인기순위가 아니다.

기존 개발자센터 발급 키를 사용하는 경우에만 발급 서비스를 **기존 개발자센터**로 선택한다. 두 서비스의 키는 서로 호환되지 않으며 실패 시 다른 서비스로 자동 전송하지 않는다. 키 재발급 후에는 앱에도 변경된 값을 저장한다. 비용과 호출 한도는 클라우드 콘솔의 최신 안내를 확인한다.

근거: [공식 이관 공지](https://developers.naver.com/notice/article/32530), [API HUB 키 발급 가이드](https://api.ncloud-docs.com/docs/naver-api-hub-overview), [뉴스 검색 API](https://api.ncloud-docs.com/docs/naver-api-hub-search-news).

## 3. AI 키와 모델 준비

### OpenAI

1. [OpenAI Platform](https://platform.openai.com/)에 로그인합니다.
2. 사용할 프로젝트를 선택합니다.
3. 프로젝트의 API 키 화면에서 비밀키를 만듭니다. 표시된 키를 안전하게 보관합니다.
4. API 결제·사용 한도와 사용할 모델의 접근 권한을 확인합니다.
5. 앱의 **연결 → AI 연결**에서 OpenAI를 선택하고 모델과 키를 저장합니다.
6. 생성 테스트로 연결을 확인합니다. 테스트에는 소량 비용이 발생할 수 있습니다.

ChatGPT 구독과 API 사용 요금은 별개입니다. 사진 자막에는 이미지 입력을 지원하는 모델을 선택하세요.

### Claude

[Claude Console](https://platform.claude.com/)에서 API 키와 모델 접근 권한을 준비합니다. 앱의 AI 모델 설정에서 Claude를 선택하고 해당 모델 이름과 키를 저장한 뒤 생성 테스트를 합니다. 사진 자막에는 이미지 입력이 지원되어야 합니다.

### OpenAI 호환 API

사용할 업체에서 API 키, 모델 이름과 HTTPS 기본 주소를 확인합니다. 앱에서 OpenAI 호환 API를 선택하고 해당 업체의 값을 입력합니다. Chat Completions와 JSON 객체 응답을 지원해야 합니다. OpenCode는 별도의 OpenCode 연결 카드를 사용하세요.

### FreeLLMAPI

이 앱은 [FreeLLMAPI 공개 프로젝트](https://github.com/tashfeenahmed/freellmapi)의 OpenAI 호환 API를 지원합니다. 서버를 먼저 설치·실행하고 대시보드에서 사용할 제공자 키를 등록하세요. 이후 통합 API 키를 발급받아 앱의 FreeLLMAPI 카드에 저장합니다.

- 기본 주소: `http://127.0.0.1:3001/v1`. 외부 서버라면 HTTPS 주소를 입력합니다.
- 모델: `auto` 또는 ‘모델 목록 불러오기’에서 확인한 모델 ID.
- OpenCode 경유 모델: `freellmapi/auto`, `freellmapi/auto:fast`, `freellmapi/모델ID`.
- 무료 제공량과 가용성은 게이트웨이에 연결한 제공자의 정책·잔여 한도에 따릅니다.

[FreeLLMAPI API 문서](https://github.com/tashfeenahmed/freellmapi/blob/main/docs/en/api/01-rest-api.md)

### OpenCode

[OpenCode 공식 문서](https://opencode.ai/docs/cli/)에 따라 CLI를 설치합니다. 앱은 `opencode run --format json --model provider/model` 방식으로 생성 요청을 전달합니다. 기존 OpenCode 연결을 이용하려면 `opencode auth login`을 완료하고 사용할 모델 ID를 확인하세요.

FreeLLMAPI를 경유할 때는 앱에서 FreeLLMAPI 주소와 통합 키를 저장한 뒤 OpenCode 모델을 `freellmapi/auto`로 지정합니다. 앱은 이 요청에만 게이트웨이 설정을 전달하며, 사용자의 기존 OpenCode 설정 파일을 수정하지 않습니다. 사진 자막에는 실제로 이미지를 지원하는 모델이 필요합니다.

### 로컬 Ollama

[Ollama](https://ollama.com/)를 설치하고 사용할 모델을 다운로드한 뒤 서버를 실행합니다. 앱의 기본 주소는 `http://127.0.0.1:11434/v1`입니다. AI 모델 설정에서 Ollama와 설치한 모델 이름을 선택합니다. API 키는 필요 없습니다. 사진 자막에는 로컬 비전 모델을 사용하세요. 서버·모델의 실제 호환성은 생성 테스트와 사진 제안으로 확인합니다.

## 4. 음성 준비

음성을 사용할 때는 OpenAI 키를 등록하고 **연결 → 뉴스 검색 · AI 음성**에서 음성 모델과 음성을 입력합니다. 샘플 듣기로 발음을 확인합니다. 음성 없이 자막만 만들 수도 있습니다.

## 5. 인스타그램 계정 준비

MP4 파일로 직접 게시하려면 평소 사용하는 Instagram 앱이나 웹에 로그인하면 됩니다. 콘텐츠 스튜디오에 Instagram API 키·토큰을 등록할 필요는 없습니다. 완성한 영상과 문안을 확인하고 Instagram에서 직접 게시하세요.

앱의 **계정 설정 → 인스타그램 계정**에는 개발용 사용자 ID·액세스 토큰을 관리하는 화면이 있습니다. 현재 영상 외부 업로드는 차단되어 있으므로 일반 제작·직접 게시를 위해 이 화면을 채울 필요는 없습니다. Instagram 비밀번호는 앱에 입력하지 마세요.

## 6. 저장과 연결 확인

키를 저장한 뒤 연결 테스트를 실행하세요. ‘등록됨’은 키가 저장되어 있다는 뜻이며 연결 성공과 다릅니다. 모델·키를 바꾸면 다시 테스트합니다. 제공자마다 다른 키를 사용하고, 새 컴퓨터에서는 키를 다시 등록합니다.

키는 OS 보안 저장소에 보관되며 인증 요청 시 해당 업체로 전달됩니다. 백업·진단에는 키가 포함되지 않습니다. 유출됐다면 업체에서 폐기·재발급한 뒤 앱의 값을 교체하세요.

[사용 가이드로 돌아가기](USER_MANUAL.md)
