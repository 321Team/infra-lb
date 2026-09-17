# FUP-09 현재 시점 DAD Supplement 수신 검토

**판정: 현재 시점 DAD Runtime·수신 무결성 PASS / 독립 편입 검토·이하영 인수 조건 해소 확인 대기.**

사용자가 v1.1로 실행한 원본 tar.gz와 sidecar를 대조했다. 검토자가 LB에 접속하거나 검사를 재실행한 결과가 아니다. 수집 시각은 **2026-09-16 15:07:50~53 UTC / 2026-09-17 00:07:50~53 KST**이며 파일명의 날짜는 UTC다.

## 검증 결과

| 항목 | 확인한 사실 |
|---|---|
| 대상 | k8s-api-lb01 / ens160 / 10.1.93.109/24 / MAC 00:0c:29:f7:65:94 |
| 원본 패키지 | 10,044 bytes / SHA-256 `9a8c149d3f0e48a43b6d052c3389b7f01ae9857bf30b03cfd592c16927d850a0` / 외부 sidecar 일치 |
| 내부 원본 | 29/29 SHA-256 일치, 원래 Manifest 포함 30개 원본 텍스트 바이트 보존 |
| 실행 수집기 | 제공 v1.1 SHA-256 `723f2a58f66cbb91ad5d83f13d4005ebe3e70ea5997811d8933122f898ea021a`와 동일 |
| 명령 기록 | 12/12 예상 명령 일치·rc=0·빈 stderr, timeout/실행 오류 없음, 시각 순서·UTC/KST 일치 |
| L2 사전 확인 | .254로 ens160 직접 경로, ARP 송신 1·응답 1·rc=0, 응답 MAC 94:f3:92:6b:a8:40 |
| DAD | .109에 sender 0.0.0.0으로 송신 3·응답 0·rc=0, 단회 실행 |
| 사전/사후 | 주소·링크·HAProxy·Listener stdout 4개 각각 byte 동일. MAC/IP·링크 UP·HAProxy active·.109:6443 LISTEN 유지 |
| 결과 | PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED, final_acceptance=PENDING_REVIEW |

- [원본 DAD 출력](raw/05_dad.stdout.txt) · [명령/RC/시각](raw/COMMANDS.json) · [사전 통신](raw/04_l2_peer.stdout.txt)
- [원본 결과](raw/RESULT.json) · [원본 내부 Manifest](raw/SHA256SUMS) · [직접 대조 상세](VERIFICATION.json) · [출처/보관](SOURCE_PACKAGE.json)

## v1.0 STOP 및 도구 해시 한계

[이전 STOP 기록](https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5699648290)은 DAD 전 도구 해시 읽기 실패이며 이력으로 보존한다. 이번 TOOLS.json에서 sudo는 root 소유 mode **0o4111**, 일반 계정 실행 접근 가능, 읽기 PermissionError/Hash 미확인으로 기록됐다. sudo 바이너리 Hash는 확보하지 않았으며 해당 누락을 숨기지 않는다. 실제 sudo를 경유한 arping 버전 조회·L2·DAD 3건은 모두 rc=0이다. 다른 도구 Hash 6개와 필수 증적 29개 Hash는 확보됐다. 권한·SELinux·sudoers 변경을 수행한 소스는 없다.

v1.1은 자체 정적/모의 회귀 25건 검증 후 제공됐으며 독립 코드 승인이나 CI 실행 기록은 아니다. 이번 원본 수집은 기존 모의 시험과 별개의 대상 LB Runtime 결과다. 실행 도구 자체의 완전한 진위 보증이나 원격 실시간 관찰을 했다고 주장하지 않는다.

## 승인과 남은 판단

- [재검사 제안](https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5698968629) 및 [이하영 승인](https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5699238203)에 따른 현재 시점 보완 증적이다.
- 인수자에게 이 원본·Manifest·검증 범위·sudo 보조 Hash 누락을 확인하고 **LB-A-01 잔여 조건을 해소하는지** 회신을 요청한다. 실제 검토자·검토일시/시간대·확인 Commit·수용 범위/남은 조건을 기록한다.
- 독립 편입 검토와 최종 인수는 아직 대기다. 기존 재검사 승인을 이번 결과의 사전 인수나 PR APPROVED로 대체하지 않는다.
- 관측 시점·해당 L2에서 응답 가능한 장비의 중복 응답 미검출에 한정한다. 과거 8/31 원본은 여전히 미확보이며 이 결과로 복구하지 않는다. 꺼진 장비·분리된 링크·미래 충돌 부재를 보장하지 않는다.
- 기존 Stage A Technical/Evidence PASS·조건부 인수와 Permanent 조건 해소는 유지한다. Stage B 3 backend UP·인증 API·failover/recovery, Bootstrap, 전체 P1-LB 종결은 이 증적 범위 밖이다.

## 보존·편입

원본 tar.gz와 sidecar는 별도 제출 보관본에 그대로 남긴다. 저장소 정책에 따라 Git에는 압축 내부 원본 30개·sidecar·새 수신 검토 3개를 기록한다. 다른 리뷰어의 별도 tar.gz 보관본 열람 가능 여부는 미확인이지만, 이 PR에서 모든 내부 원본을 직접 볼 수 있다. 기존 원본에는 승인 문구를 삽입하지 않는다.

새 수신 경로의 34개 파일을 루트 REGISTRY_SHA256SUMS에 추가한다. 기존 루트 Manifest의 관리 범위 전체가 저장소 모든 파일과 같다고 주장하지 않는다. 최신 인수 판단·Commit·PR은 [후속 이슈 #4](https://github.com/321Team/fds-project-evidence/issues/4)와 [P1-LB-01 #9](https://github.com/321Team/fds-project-baseline/issues/9)에서 추적한다.
