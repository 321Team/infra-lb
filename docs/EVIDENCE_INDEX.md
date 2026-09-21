# LB 자료·증적 통합 목록

소스·문서와 이관된 LB 전용 실행 증적은 infra-lb에서 관리한다. 원본 PR·이전 승인 이력은 evidence/baseline의 고정 링크로 보존한다. 현재 검토 위치와 이관 범위는 [PR 이관 현황](PR_MIGRATIONS.md)을 따른다. 파일 개수에는 README·수신 검토·manifest가 포함되므로 실제 시험 횟수가 아니다.

## 이관한 원본 자료

- [Stage A 보존 자료 안내](../archive/README.md): 구축 가이드 v1.5, 완료 팩 v1.3의 LB 소스·문서, 9/7 export/보완 소스
- [노션 작업 원본 및 이후 대조](history/README.md)
- [LB 관련 카카오톡 발췌](history/CHAT_LB_EXCERPTS_20260916.md): 4개 구간, 원본 위치와 해시
- [운영 기준](OPERATIONS_BASELINE.md), [Stage A 인계 근거](STAGE_A_HANDOFF.md)
- 기존 [SOURCE_LOCK.json](SOURCE_LOCK.json)은 최초 cfg·DAD/preflight 편입 기록이며 변경하지 않았다.

## Git 원본 고정 참조

| 자료 묶음 | 원본 경로 | 파일 수 | 고정 commit |
|---|---|---:|---|
| Stage A 수신 원본·검토 | [evidence/P1-LB-01/stage-a/received-20260907/](https://github.com/321Team/fds-project-evidence/tree/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/received-20260907) | 28 | `90093f88167055f81e8789d2a848f44ead0ee9ce` |
| Permanent 보완 | [evidence/P1-LB-01/stage-a/supplement-20260909T072022Z/](https://github.com/321Team/fds-project-evidence/tree/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/supplement-20260909T072022Z) | 11 | `90093f88167055f81e8789d2a848f44ead0ee9ce` |
| 현재 DAD | [evidence/P1-LB-01/stage-a/dad-supplement-20260916T150750Z/](https://github.com/321Team/fds-project-evidence/tree/f74bda7eac39658c297a4dd5d1c590bd0717bcce/evidence/P1-LB-01/stage-a/dad-supplement-20260916T150750Z) | 34 | `f74bda7eac39658c297a4dd5d1c590bd0717bcce` |
| Stage B 사전점검 | [evidence/P1-LB-01/stage-b/preflight-20260917T031743Z/](https://github.com/321Team/fds-project-evidence/tree/c6ed08bdd7d54901dffc709fc9fa0d75e961f68b/evidence/P1-LB-01/stage-b/preflight-20260917T031743Z) | 52 | `c6ed08bdd7d54901dffc709fc9fa0d75e961f68b` |

위 네 묶음 125개와 관련 인수/정정·DNS 소비자 파일 9개의 정확한 Git blob SHA·경로는 [MATERIALS_MANIFEST.json](MATERIALS_MANIFEST.json)에 기록했다. 모든 링크 대상은 해당 commit의 tree에서 존재를 확인했다. 이번에는 기존 서버 출력의 Runtime 판정을 다시 수행하지 않았다.

## 해석과 관리 경계

- [D35](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/releases/v3.1.15/D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0.md)·[D36](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/releases/v3.1.16/D36_Team_Availability_and_Status_Update_Record_v1.0.md)·[정본 본문](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/baseline/FDS_Project_Implementation_Baseline_v3.1.18.md)은 baseline에서 관리한다. 새 저장소에 정본 사본을 만들어 이중 관리하지 않는다.
- 기존 evidence handoff·수신 README의 HOLD/Pending은 작성 당시 표기다. [인계 근거](STAGE_A_HANDOFF.md)에서 이후 정정과 실제 인수 회신을 함께 확인한다.
- DNS 디렉터리의 `k8s_api_lb01_failover_evidence.txt`는 **LB 호스트의 DNS 장애전환**이다. API backend 장애복구·Stage B 완료 증적으로 세지 않는다.
- 전체 카카오톡 ZIP·이미지와 실행 tar.gz 원본은 기존 보관본에 남긴다. 이 저장소에는 LB 관련 발췌, 출처, 해시와 Git 증적 링크를 정리했다. 다른 팀원의 원본 보관본 접근까지 확인한 것은 아니다.
- 노션에 적힌 이전 백업 두 파일 실물, 8/31 DAD 서버 원본, Stage B 인증 API/장애복구 결과는 이번 이관으로 새로 확보하지 않았다.
- 자료 이관 검증은 [MATERIALS_VALIDATION.json](MATERIALS_VALIDATION.json), 전체 파일 해시는 루트 SHA256SUMS를 따른다.

## 현재 분기에 편입한 실행 원본

- [DAD 원본·수신 검토](../evidence/P1-LB-01/stage-a/dad-supplement-20260916T150750Z/README.md): 원본 PR14의 34개 파일을 byte 그대로 보존.
- Stage B preflight 52개는 별도 후속 이관 분기에서 검토한다.
