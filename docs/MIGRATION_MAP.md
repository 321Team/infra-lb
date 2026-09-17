# LB 소스 편입과 기존 PR 대응

2026-09-17. 기존 PR 객체·번호·대화·리뷰·승인 이력은 원래 저장소에 남긴다. infra-lb에서는 고정 커밋의 소스를 새 편입 PR로 검토하고 원본에 연결한다. 과거 승인 또는 미병합 PR의 기술 확인이 새 PR의 승인을 대신하지 않는다.

| 기존 위치 | infra-lb에서 관리할 내용 | 원래 위치에 남는 내용 |
|---|---|---|
| evidence [PR #1](https://github.com/321Team/fds-project-evidence/pull/1), [#5](https://github.com/321Team/fds-project-evidence/pull/5) | `configs/haproxy.cfg`의 Stage A 고정 설정 및 상태 참조 | 병합 이력, 원본 결과, 조건부 인수 기록 |
| evidence [PR #6](https://github.com/321Team/fds-project-evidence/pull/6) | Permanent 조건의 확인 범위 링크 | 원본 출력과 당시 검토/승인 |
| evidence [PR #14](https://github.com/321Team/fds-project-evidence/pull/14) | `tools/dad/collect_dad.py`, 기존 테스트, DAD runbook | 원본 PR 객체·기존 대화 이력. 후속 증적 검토는 [이관 현황](PR_MIGRATIONS.md)을 따름 |
| evidence [PR #15](https://github.com/321Team/fds-project-evidence/pull/15) | `tools/stage-b/collect_preflight.py`, 기존 테스트/fixture, 후속 절차 | 원본 PR 객체·기존 대화 이력. 후속 사전점검 검토는 [이관 현황](PR_MIGRATIONS.md)을 따름 |
| evidence [PR #7](https://github.com/321Team/fds-project-evidence/pull/7) | LB 관련 연결만 참조 | FUP-04~09 공통 매핑. LB 단독 PR로 취급하지 않음 |
| infra-ansible [Stage A playbook](https://github.com/321Team/infra-ansible/blob/57e7cc740e7a406387848c52f4aa56b98c516168/playbooks/p1-lb-01-stage-a-nodes.yml) | 고정 출처 참조 | 공통 inventory와 Node→LB 연결검사 소스는 원래 저장소에서 유지 |
| baseline [이슈9](https://github.com/321Team/fds-project-baseline/issues/9) | 소스 저장소 및 편입 PR 연결 | 요구사항·잔여 조건·전체 상태 |

수집기 2개와 cfg는 원본 Git blob을 가져와 SHA-256과 Git blob SHA를 대조한다. 테스트·fixture·API/복구 절차·입력 양식은 이미 전달한 키트에서 가져온다. 실행 경로와 현재 상태를 새 문서에 반영하되 수집기 로직을 바꾸지 않는다.

## 편입 시점 고정 근거

- Stage A evidence main: `90093f88167055f81e8789d2a848f44ead0ee9ce`.
- DAD PR14 HEAD: `f74bda7eac39658c297a4dd5d1c590bd0717bcce`; 제출 archive SHA-256 `9a8c149d3f0e48a43b6d052c3389b7f01ae9857bf30b03cfd592c16927d850a0`.
- preflight PR15 HEAD: `c6ed08bdd7d54901dffc709fc9fa0d75e961f68b`; 제출 archive SHA-256 `a1a7bb272a770ba44f5ae6542f0f6aee2a948cbbcf773a6f31242b83abf23281`.
- 공통 Ansible main: `57e7cc740e7a406387848c52f4aa56b98c516168`. 새 LB PR 때문에 공통 소스를 변경하지 않는다.
- infra-lb 초기 README 부모 commit: `af56e2dde761fdf39d90170c4c710a8d87b46a53`.

정확한 경로·해시는 [SOURCE_LOCK.json](SOURCE_LOCK.json)을 참조한다. 이 문서는 소스 편입 목록이며 증적 PR14/15의 종결·승인·병합을 뜻하지 않는다.

## 후속 LB 자료 편입 — 2026-09-17

초기 PR의 미병합 HEAD를 부모로 자료 이관을 추가했다. 새 검토 HEAD는 PR 본문에서 확인한다.

| 출처 | 편입/참조 |
|---|---|
| 기존 Stage A 구축 가이드 v1.5 | archive/stage-a-guide-v1.5 원본 보존 |
| 완료 팩 v1.3 | archive/stage-a-completion-v1.3에 LB 소스·문서 12개 보존. 공통 playbook 1개는 infra-ansible 참조 |
| 기존 Stage A export/보완 수집기 | archive/stage-a-support 원본 2개 보존 |
| 수동 노션 기록 | docs/history 원본 보존; 이후 상태와 대조 |
| 카카오톡 export | LB 관련 4개 구간 발췌와 원본 SHA·위치 |
| Stage A/Permanent/DAD/preflight 증적 | docs/EVIDENCE_INDEX.md 및 MATERIALS_MANIFEST.json에 고정 Git 경로·blob SHA |

운영 기준·인계 요약을 추가했으며 기존 cfg·DAD/preflight 코드와 테스트는 변경하지 않았다. 당시 증적 PR14/15는 evidence에서 검토하도록 두었다. 이후 사용자 지시로 후속 검토를 infra-lb로 옮기며 최신 위치는 [PR 이관 현황](PR_MIGRATIONS.md)을 따른다. 이번 추가 편입의 바이트/구문/링크 검증은 MATERIALS_VALIDATION.json을 따른다.
