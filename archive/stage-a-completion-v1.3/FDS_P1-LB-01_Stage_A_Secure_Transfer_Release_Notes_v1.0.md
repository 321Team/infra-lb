# P1-LB-01 Stage A Secure Transfer Release Notes v1.0

> Release Date: `2026-09-03`  
> Parent Ticket: `P1-LB-01`  
> Baseline: `FDS_Project_Implementation_Baseline_v3.1.15`  
> Status: `RELEASED / RUNTIME EVIDENCE PENDING`

## 변경 사유

Evidence 16·18을 `ansible01`에서 LB로 SCP하던 중 `Too many authentication failures`가 발생했다. 초기 우회안인 Password 강제는 P1-ANS-01에서 승인된 Key·Host Key·Identity 제한 통제와 정합성이 없고 LB Password 예외 승인도 없으므로 폐기했다.

## 적용 내용

- Source별 Passphrase 보호 ED25519 일회성 키 분리
- LB Console ED25519 Fingerprint와 Source별 전용 `known_hosts` 고정
- `IdentityAgent=none`, `IdentitiesOnly=yes`, Publickey-only, Strict Host Key Checking
- LB `authorized_keys`에 Source IP 제한, `restrict`, Evidence 전용 Forced Command 적용
- 승인 파일명·1 MiB 제한·전송 전후 SHA-256 검증
- mode `0700` Inbox, mode `0600` 수신본, mode `0640` 최종 Evidence
- 전송 완료 후 LB Public Key와 Source Private Key 즉시 폐기
- Evidence `18a`, `18b`, `18c` 및 Handoff 검토 항목 추가
- HAProxy 정상 구문 검증 시 출력이 없어 Evidence 06이 0 byte가 되던 수집 결함 수정
- Evidence 전체 mode `0640`, Symlink 금지, SHA-256 재검증을 Finalize Gate에 추가

## 영향성

| 대상 | 영향 |
|---|---|
| P1-ANS-01 | 재개 없음; 기존 Node 관리키 범위 확장 없음 |
| P1-LB-01 | Stage A Runtime Evidence Gate 강화 |
| P1-K8S-01 | Stage A Handoff 승인 전 Bootstrap HOLD 유지 |
| Network/Firewall | 변경 없음 |
| `sshd_config` | 변경 없음 |
| SELinux Mode | Enforcing 유지 |

## 대체 관계

- `P1-LB-01_Stage_A_Completion_Pack_v1.3`이 v1.2를 대체한다.
- `FDS_P1-LB-01_Stage_A_Build_Guide_v1.5`가 v1.4를 대체한다.
- v1.1/v1.2 실행 이력과 기존 Evidence 01~18은 삭제하지 않고 감사 이력으로 보존한다.

## Runtime 경계

본 릴리즈는 통제 설계와 실행 도구를 발행한 것이다. Evidence 18a~18c, Reviewer 승인, `99_SHA256SUMS.txt`, Repository Commit ID가 확보되기 전에는 다음 상태를 유지한다.

```text
Stage A Result: Listener Configured / Handoff Blocked
P1-K8S-01 Bootstrap: HOLD
```
