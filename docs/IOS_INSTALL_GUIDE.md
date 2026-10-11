# iPhone 앱 설치 안내

## 현재 배포 상태

2026-10-11 기준, 이 Mac의 Xcode에 설정된 서명 팀은 무료 개인용 팀(`5YV2YC5247`)입니다. 이 팀으로 Release 아카이브는 만들었지만, App Store 배포 서명이 없어 TestFlight로 내보내거나 업로드할 수 없습니다. Xcode도 App Store Connect 로그인 계정이 없다고 보고했습니다. 생성된 아카이브는 TestFlight 업로드 완료본이 아닙니다.

## 지금 개발 중인 앱을 내 iPhone에 설치

현재 앱은 Xcode의 개인 개발용 서명으로 설치되어 있습니다. 이 방식은 개발자가 연결한 기기에 테스트용 빌드를 설치하는 용도라 다른 사람에게 앱 파일만 보내 설치하게 할 수 없습니다. 새 빌드를 직접 배포하려면 Xcode의 Apple 계정으로 기기를 등록하고 서명해야 합니다.

## 다른 사람에게 배포: TestFlight

1. 활성화된 유료 Apple Developer Program 팀을 사용합니다. 다른 팀 계정이 이미 있다면 Xcode → Settings → Accounts에서 그 Apple Account를 추가하고, 없다면 배포자 명의로 Apple Developer Program에 가입해야 합니다. Apple은 현재 연회비를 미화 99달러(지역 통화 적용 가능)로 안내합니다.
2. Xcode에서 앱의 배포 서명과 버전을 설정하고 **Product → Archive**로 iOS 빌드를 만듭니다.
3. Organizer의 **Distribute App → App Store Connect → Upload**를 선택해 빌드를 업로드합니다.
4. App Store Connect에서 앱의 TestFlight 설명과 테스트할 내용을 등록하고 업로드된 빌드를 선택합니다.
5. 내부 테스터는 App Store Connect 팀 사용자로 초대합니다. 외부 사람은 외부 테스터 그룹에 이메일 또는 공개 초대 링크로 초대합니다. 첫 외부 테스트 빌드는 Apple 검토를 거칠 수 있습니다.
6. 테스터는 App Store에서 **TestFlight** 앱을 설치하고 초대를 수락한 뒤 콘텐츠 스튜디오를 설치합니다.

TestFlight 빌드는 최대 90일 동안 사용할 수 있습니다. 새 버전을 테스트하려면 Xcode에서 새 빌드를 업로드하고 테스터가 업데이트해야 합니다. Apple은 외부 테스터를 앱당 최대 10,000명까지 허용한다고 안내합니다.

## 테스터가 앱을 열 때

사진 추가, 직접 자막 작성, 음악 선택, MP4 제작은 AI를 연결하지 않아도 가능합니다. 사진 기반 AI 자막 제안은 사용자가 각자의 API 키를 앱 설정에 직접 등록해야 합니다. 카드뉴스와 네이버 뉴스 검색은 Mac 앱에서 제공합니다. Mac에 저장된 API 키는 배포된 앱으로 전달되지 않습니다.

## 공식 안내

- [Apple Developer Program 멤버십과 비용](https://developer.apple.com/programs/whats-included/)
- [TestFlight 개요와 배포 순서](https://developer.apple.com/help/app-store-connect/test-a-beta-version/testflight-overview/)
- [외부 테스터 초대](https://developer.apple.com/help/app-store-connect/test-a-beta-version/invite-external-testers/)
