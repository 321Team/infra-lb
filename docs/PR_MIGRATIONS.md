# LB 전용 PR 이관 — 2026-09-17

사용자의 PR 이관 지시에 따라 미병합 LB 전용 변경 두 건을 infra-lb로 옮긴다. 이전 소스 편입 PR1은 main에 병합되었다. 아래 원본 PR의 객체·번호·대화·기존 승인 이력은 evidence에 보존하며, 새 변경의 검토는 각 이관 PR에서 진행한다.

| 원본 PR / 고정 HEAD | 새 검토 분기 | 이 분기의 편입 범위 |
|---|---|---|
| [evidence #14](https://github.com/321Team/fds-project-evidence/pull/14), `f74bda7eac39658c297a4dd5d1c590bd0717bcce` | [DAD 이관](https://github.com/321Team/infra-lb/tree/chore/migrate-evidence-pr14-dad) | 원본 34개 편입, 독립 검토 대기 |
| [evidence #15](https://github.com/321Team/fds-project-evidence/pull/15), `c6ed08bdd7d54901dffc709fc9fa0d75e961f68b` | [Stage B 이관](https://github.com/321Team/infra-lb/tree/chore/migrate-evidence-pr15-preflight) | 별도 후속 분기에서 이관; 이 변경에는 포함되지 않음 |

각 원본 PR 상단에도 실제 새 PR URL을 기록한다. 원본 종료는 **이관**을 뜻하며 승인·병합·인수 완료가 아니다. 캡처 당시 두 원본 PR의 review submission은 0건이다. 새 HEAD에 대해 독립 리뷰가 필요하다.

## 파일 보존과 검증

- 원본에서 추가한 LB 디렉터리 파일을 경로와 byte 그대로 가져왔다. 출처 SHA, 파일별 Git blob SHA·SHA-256, 원본 PR 본문·작성자/시각을 포함한 댓글 사본은 `docs/pr-migrations/evidence-14.json`에 기록한다. 댓글 사본은 원래 작성자의 새 회신으로 게시하지 않는다.
- 원본 PR의 root README와 REGISTRY_SHA256SUMS는 evidence 저장소 전체를 관리하므로 복사하지 않는다. 해당 LB 인덱스와 manifest 기능을 이 저장소의 문서 및 루트 SHA256SUMS로 반영했다.
- 원본 내부 SHA256SUMS 및 제출 sidecar를 보존한다. 별도 이관 검증 기록은 `docs/pr-migrations/*-validation.json`, 이 분기 전체 파일 해시는 루트 `SHA256SUMS`다. 기존 SOURCE_LOCK·MATERIALS_MANIFEST는 당시 고정 참조 기록으로 보존한다.
- tar.gz 원본은 기존 첨부 보관본을 유지한다. 서버 설정·수집기 로직 변경이나 실서버 재실행은 없다.

## 검토와 병합 순서

DAD 분기는 main을 대상으로, Stage B 분기는 DAD 분기를 대상으로 한다. DAD 이관을 먼저 병합한 뒤 Stage B PR의 base를 main으로 바꾸고 최종 diff·HEAD·승인을 확인한다. Stage B 분기를 DAD 분기로 먼저 병합하지 않는다. 공통 정책·인덱스·루트 manifest 충돌을 방지하기 위한 순서다.

- DAD: 현재 시점 기술 PASS, LB-A-01 잔여 조건 해소 여부는 이하영의 명시적 인수 판단 대기.
- Stage B: PRECHECK_NOT_READY, CP1 UP·CP2/3 DOWN/Connection refused. 인증 API·장애복구 미수행, 전체 P1-LB-01 In Progress 유지.
- 원본 PR7(공통 FUP)·PR13(Ansible), 이미 병합된 PR1/5/6 및 기준선 이슈는 이동하지 않는다.
