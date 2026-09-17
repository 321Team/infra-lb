# 수동 작업 기록과 이후 근거

[노션 원본](NOTION_LB_ORIGINAL.md)은 사용자 첨부 파일을 수정 없이 보존한 당시 작업 기록이다. 원본 문서의 작성·최종 수정 시각은 첨부 파일만으로 확정하지 않는다. [카카오톡 발췌](CHAT_LB_EXCERPTS_20260916.md)는 원본 텍스트 위치와 해시를 함께 보존한다.

| 원본의 당시 표기 | 이후 확인된 근거 | 이관 시 적용 |
|---|---|---|
| IF-11A 승인 대기 | [D35 승인](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/releases/v3.1.15/D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0.md), export의 9/2 22:06 승인 문구 | 설계 승인 완료 이력으로 연결. 새 Runtime 승인 아님 |
| Node 6대 접근·Stage A 인계 대기 | [D36](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/releases/v3.1.16/D36_Team_Availability_and_Status_Update_Record_v1.0.md), Stage A 원본·조건부 인수 회신 | 기존 Stage A PASS 유지. 과거 미완료 체크를 현재 미실행으로 사용하지 않음 |
| backend 3DOWN 예상 | Bootstrap 이전 기록; 9/17 PR15는 CP1 UP·CP2/3 DOWN | 과거/현재 스냅샷을 분리 |
| LB 및 CP firewall 관리 | 현행 LB 범위는 [기준선 이슈9](https://github.com/321Team/fds-project-baseline/issues/9), Node firewall은 Kubernetes/ICR 소관 | 과거 Scope로 CP 설정을 이 저장소에 재편입하지 않음 |
| 백업 경로·SHA | 노션에 기재된 두 백업 파일 자체는 이번 자료에 없음 | 복구 가능성 검증 완료로 표시하지 않음 |

과거 Stage A 중복 재승인 요구는 [승인 범위 정정](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/registry/STAGE_A_APPROVAL_SCOPE_CORRECTION.md)을 따른다. Permanent 조건은 [9/16 인수 판단](https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5697474151) 범위에서 해소됐고, 현재 DAD 원본은 PR14에서 별도 리뷰한다.

현재 사용할 기준·출처는 [운영 기준](../OPERATIONS_BASELINE.md), [인계 상태](../STAGE_A_HANDOFF.md), [증적 목록](../EVIDENCE_INDEX.md)에서 확인한다. 원본 자체를 최신 판단에 맞춰 덮어쓰지 않는다.
