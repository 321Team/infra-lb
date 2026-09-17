# P1-LB-01 Stage A 완료 실행 팩 v1.3 — Release Notes

## Release

- Version: `v1.3`
- Date: `2026-09-03`
- Canonical Baseline: `FDS_Project_Implementation_Baseline_v3.1.15`
- Parent Guide: `FDS_P1-LB-01_Stage_A_Build_Guide_v1.5`
- Approval Record: `D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0`
- Scope: Stage A 잔여 검증 및 Evidence/Handoff 보조

## Included

- `/etc/haproxy/haproxy.cfg`의 `stats socket` 자동 탐지 및 실제 Unix Socket 검증
- 현재 환경의 `/var/lib/haproxy/stats` 지원과 `HAPROXY_STATS_SOCKET` 명시적 Override
- LB의 IF-11/IF-11A/IF-06A Rich Rule 적용 가드 및 기존 Rule 백업
- LB→CP Pre-bootstrap 결과 자동 분류
- K8s Node 6대의 원격 TCP Positive Test용 Ansible Playbook
- Runner Positive 및 미승인 Source Negative Test 스크립트
- Evidence `01`~`19`, `99_SHA256SUMS.txt` 완결성 검사
- Stage A Handoff Review Template
- Source별 일회성 ED25519 Key와 LB Host Key Pinning 기반의 정책 통제 전송
- `from`, `restrict`, Forced Command 기반 Evidence 전용 Receiver
- 보호 Inbox와 Evidence 18a/18b/18c
- Evidence mode `0640`, Symlink 금지 및 Finalize Hash 재검증

## Runtime result reflected

- `10.1.93.102:6443`: Connection refused — Route PASS / API not started
- `10.1.93.103:6443`: Connection refused — Route PASS / API not started
- `10.1.93.104:6443`: Connection refused — Route PASS / API not started

이 결과만으로 Stage A 전체 PASS를 선언하지 않는다. D35로 IF-11A 설계 승인은 완료됐으나 Node/Runner Positive, ansible01 `.10` Negative, Handoff 및 Git Commit Evidence가 모두 필요하다.

## Validation

- v1.3 Shell Script 5종: `bash -n` PASS
- Ansible Playbook: YAML parse PASS
- Receiver 격리시험: 승인 Source/파일 허용, 비승인 Source exit `21`, 비승인 파일 exit `23`, Inbox `0700`, 수신 파일 `0600` PASS
- Client Key 시험: Passphrase 보호 Key mode `0600` PASS, 빈 Passphrase exit `3` 및 Key 제거 PASS
- LB Authorization 시험: `from`, `restrict`, Forced Command, `authorized_keys` `0600` PASS
- 제한: 배포 환경에 Ansible 실행 파일과 실제 Inventory가 없어 `ansible-playbook --syntax-check` 및 Runtime 실행은 ansible01에서 수행해야 한다.

## Baseline impact

- D35 승인 및 v3.1.15 Parent Guide를 실행 기준으로 사용한다.
- IF-06A monitor01 `.30/32`는 Source Allowlist에 보존하되 Probe Runtime은 P1-MON-01에서 판정한다.
- P1-LB-01 상태는 Stage A PASS 후에도 `In Progress`를 유지한다.
- Backend Health, 인증 API, Failover와 Recovery는 Stage B Open Item으로 유지한다.

## v1.3 Security Corrective Change

- `Too many authentication failures`에 대한 Password 인증 우회안을 폐기했다.
- P1-ANS-01의 Node 관리키를 LB 접속에 재사용하지 않는다.
- ansible01 `.10`과 runner `.20`의 일회성 Key를 분리하고 LB Public Key를 Source와 Forced Command로 제한한다.
- Client에서 Password/Keyboard-interactive를 비활성화하고 단일 Identity와 Strict Host Key Checking을 강제한다.
- 전송·병합·키 폐기·Inbox 정리를 Evidence 18a~18c로 증명한다.
- 정상 HAProxy 구문검증 출력이 0 byte이던 Evidence 06을 구조화된 PASS Record로 수정했다.
- v1.2는 Runtime 전송·Finalize 단계에 한해 superseded하며 기존 실행 이력은 보존한다.

## v1.2 Corrective Change History

- v1.1의 Evidence 수집부가 `/run/haproxy/admin.sock`을 고정 사용하던 결함을 수정했다.
- 2026-09-03 실제 설정 `stats socket /var/lib/haproxy/stats mode 660 level admin`과 Socket 존재를 근거로 보정했다.
- Precheck와 IF-11/IF-11A/IF-06A Firewall 적용 결과에는 영향이 없으며 재적용하지 않는다.
- v1.1은 수집 단계에 한해 superseded 처리하고 실행 이력은 보존한다.
