# 인스타그램 API 게시용 임시 저장소 준비

현재 구현은 AWS S3 비공개 버킷에 승인한 MP4를 올리고, 3시간 유효한 다운로드 URL을 Meta에 전달한다. 로컬 PC를 외부에 공개할 필요가 없다. 임시 자격 증명 만료나 버킷 정책에 따라 링크 유효시간은 더 짧을 수 있다. MP4를 직접 내려받아 게시하면 이 설정은 필요 없다.

## 준비 순서

1. AWS 콘솔에서 S3 버킷을 준비하고 이름·리전을 확인한다. 예: 서울 리전 `ap-northeast-2`.
2. 퍼블릭 액세스 차단을 유지한다. 공개 버킷 정책이나 공개 ACL을 추가하지 않는다.
3. 앱이 사용하는 `instagram-studio/` 접두사에 필요한 권한만 허용한 자격 증명을 준비한다. 루트 계정 키를 사용하지 않는다. 임시 자격 증명이 있으면 Access Key·Secret Key·Session Token을 함께 사용한다.
4. 장기 액세스 키를 사용하는 경우 IAM 사용자에서 이 프로그램 전용 키를 생성하고 Secret Key는 생성 시 보관한다.
5. 프로그램 설정에 버킷 이름, 리전, Access Key ID, Secret Access Key와 필요한 Session Token을 입력하고 저장한다.
6. 연결 테스트로 버킷 접근을 확인한다. 실제 영상 업로드에는 객체 쓰기·읽기 권한도 필요하다.
7. 버킷 수명주기 규칙을 `instagram-studio/` 접두사에만 적용해 업로드 자료를 정리한다. 예: 생성 1일 이후 만료. 버전 관리 사용 시 이전 버전과 미완료 멀티파트 업로드 정리도 구성한다.

수명주기 삭제는 지정 시각에 즉시 실행되는 보장이 없다. 다른 용도로 쓰는 파일에 규칙이 적용되지 않도록 접두사를 제한한다. 현재 앱은 업로드 자료를 즉시 삭제하지 않으며 버킷 수명주기에 맡긴다. 저장 및 전송 비용은 AWS 계정에 발생한다.

근거: [S3 임시 서명 URL](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html), [IAM 액세스 키 관리](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_access-keys.html), [IAM 최소 권한](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html), [S3 객체 만료](https://docs.aws.amazon.com/AmazonS3/latest/userguide/lifecycle-expire-general-considerations.html).

## 권한 정책 예시

`YOUR_BUCKET_NAME`을 실제 버킷 이름으로 바꾼다. 이미 적용된 명시적 Deny·암호화·조직 정책에 따라 추가 구성이 필요할 수 있다. SSE-KMS를 사용한다면 해당 키의 권한도 필요하다.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:ListBucket"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME"
    },
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:AbortMultipartUpload"],
      "Resource": "arn:aws:s3:::YOUR_BUCKET_NAME/instagram-studio/*"
    }
  ]
}
```

## 확인할 문제

- 연결 테스트 실패: 버킷 이름·리전·자격 증명 만료·ListBucket 권한 확인.
- 업로드 실패: PutObject 권한, 버킷 암호화·정책, 자격 증명 만료 확인.
- Meta 영상 처리 실패: 서명 URL을 차단하는 네트워크/IP 정책, GetObject 권한, 인증 만료, 파일 규격 확인.
- 영상이 남아 있음: 해당 접두사에 만료 규칙이 활성화됐는지 확인. 버전 관리 버킷에서는 이전 버전도 별도 확인.
