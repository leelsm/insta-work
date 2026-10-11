# 프로젝트 구조와 플랫폼별 기능

현재 저장소에는 별도로 구현된 두 앱이 있습니다. iPhone은 SwiftUI 네이티브 앱이고, 데스크톱은 React 화면을 Python 앱 창에 띄우는 구조입니다. Mac 기능을 수정해도 iPhone에 자동 반영되지 않습니다.

| 경로 | 역할 | 사용 플랫폼 |
| --- | --- | --- |
| `ios/ContentStudio/` | SwiftUI 화면, 로컬 프로젝트 저장, Keychain, AI·뉴스 통신, AVFoundation 영상 제작 | iPhone |
| `ios/ContentStudio.xcodeproj/` | iOS 빌드, 앱 식별자, 개발 팀·서명 설정 | Xcode |
| `ios/ContentStudio/Assets.xcassets/` | iPhone 앱 아이콘 | iPhone |
| `ios/Tests/` | Swift 뉴스 파서·카드 초안 검사 | 개발 검증 |
| `frontend/src/` | React·TypeScript 화면, 카드 편집, 설정, 사용 가이드 | Mac·Windows / 로컬 웹 |
| `studio/` | FastAPI API, SQLite 저장, 뉴스 수집, AI 연결, FFmpeg 영상 제작 | Mac·Windows |
| `run.py`, `studio/launcher.py` | Python 서버와 데스크톱 창 실행 | Mac·Windows |
| `scripts/build.py` | PyInstaller로 데스크톱 앱 패키징 | Mac·Windows |
| `resources/` | 기존 아이콘, 음악, 폰트·라이선스 | 일부 공용 |
| `studio/transfer.py`, `ios/ContentStudio/StudioStore.swift` | `.studio` 파일을 통한 프로젝트 교환 | 양쪽에 각각 구현 |
| `tests/` | Python API·뉴스·영상·전송 테스트 | 데스크톱 코드 검증 |
| `docs/` | 사용 설명, API 설정, 설계·검증 상태 | 공용 문서 |
| `dist/`, `frontend/dist/` | 빌드 결과물. 원본 소스가 아님 | 배포 / 데스크톱 번들 |

## 실행 흐름

- 데스크톱: React 화면 → 로컬 FastAPI → SQLite·OS Keychain·외부 API·FFmpeg.
- iPhone: SwiftUI 화면 → iPhone 로컬 파일·Keychain·외부 API·AVFoundation. Mac 서버 없이 실행됩니다.
- 기기 사이 프로젝트 이동: `.studio` 내보내기 → AirDrop/파일 공유 → 가져오기. 자동 동기화는 아닙니다.
- Mac에 저장한 API 키는 iPhone에 자동 복사하지 않습니다. 각 기기 설정에 따로 등록합니다.

## 플랫폼별 기능

- **Mac**: 카드뉴스와 일상 영상 제작을 모두 제공합니다. 뉴스 검색·요약·이미지 추천·AI 음성은 Mac에서 사용합니다.
- **iPhone**: 일상 영상에 집중합니다. 홈은 새 일상 영상과 내 영상, 제작은 사진 선택 → 분위기·자막 → 편집 → MP4 저장 순서입니다.
- 일상 편집 설정은 양쪽에서 사진 맞춤·위치·장면 길이·순서·자막·폰트·크기·위치·스타일·사진 움직임·전환·음악·시작 구간을 제공합니다. iPhone도 사진을 실제 AI 이미지 입력으로 전달할 수 있으며, 사용자가 요청해야 전송합니다.
- `.studio` 일상 프로젝트 교환에서 편집 설정과 분위기·설명·말투를 보존합니다. iPhone은 카드 프로젝트 가져오기를 받지 않으며 이전에 저장한 카드는 Mac으로 내보내기만 제공합니다.

SwiftUI 화면과 AVFoundation 렌더러는 Mac과 별도 구현입니다. 코드가 자동으로 공유되지는 않습니다. 메뉴를 줄이면서 일상 편집의 설정과 결과를 맞춘 구조입니다.

## 개발 시 주의

공용인 것은 음악·아이콘 원본 등의 자료와 프로젝트 교환 형식입니다. 화면, 뉴스 처리, AI 요청, 렌더링 코드는 플랫폼별로 별도이므로 변경 시 양쪽 동작을 확인해야 합니다. 아이콘 원본은 `resources/ContentStudio.png`, iOS 패키징용 불투명 1024px 파일은 `ios/ContentStudio/Assets.xcassets/AppIcon.appiconset/AppIcon.png`입니다.
