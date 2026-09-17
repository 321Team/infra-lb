# P1-LB-01 Stage A Handoff Review

## Record

| Field | Value |
|---|---|
| Ticket | P1-LB-01 |
| Canonical Baseline | FDS_Project_Implementation_Baseline_v3.1.15 |
| Approval Record | D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0 |
| Stage | Stage A |
| Lead | 이권욱 |
| Support / Receiver | 이하영 |
| Review timestamp | `<YYYY-MM-DDThh:mm:ss+09:00>` |
| Evidence repository path | `docs/evidence/P1-LB-01/stage-a/` |
| Git commit ID | `<COMMIT_ID>` |

## Interface approval

- [ ] IF-11 Runner `10.250.10.20/32 → 10.1.93.109:6443/tcp` 확인
- [x] IF-11A Node `.102/.103/.104/.105/.107/.108/32 → 10.1.93.109:6443/tcp` D35 승인 확인
- [ ] IF-06A monitor01 `10.250.10.30/32 → 10.1.93.109:6443/tcp` Rule 보존 확인
- [x] IF-11A 승인자 이하영 기록
- [x] 정본 발행 승인자 이권욱 기록

## Stage A checks

- [ ] LB-A-01 `.109` IP 충돌 없음
- [ ] LB-A-02 `.109/24`, Default `.254`, Return Route `10.250.10.0/24 via 10.1.93.58`
- [ ] LB-A-03 HAProxy configuration valid
- [ ] LB-A-04 HAProxy enabled / active
- [ ] LB-A-05 Listener가 `10.1.93.109:6443`에만 Bind
- [ ] LB-A-06 CP `.102/.103/.104:6443` Backend 정의
- [ ] LB-A-07 TCP / TLS Pass-through 유지
- [ ] LB-A-08 IF-11/IF-11A/IF-06A Source Allowlist 적용, 광역 `6443/tcp` 개방 없음
- [ ] LB-A-09 SELinux Enforcing, `haproxy_connect_any=on`, 미해결 AVC 없음
- [ ] LB-A-10 Node 6대와 Runner Positive Test PASS
- [ ] LB-A-11 ansible01 `.10` 미승인 Source Negative Test PASS
- [ ] LB-A-12 Evidence 16~18을 정책 통제 경로로 병합
- [ ] LB-A-13 Evidence 18a/18b/18c에서 Publickey-only, Host Key Pinning, Source 제한 확인
- [ ] LB-A-14 임시 LB Public Key Tag 0건, Source Private Key 폐기, 보호 Inbox 0건
- [ ] LB-A-15 Evidence 01~19·18a~18c 및 SHA256 Manifest 확보

## Secure Evidence transfer

| Check | Result |
|---|---|
| Password / Keyboard-interactive 사용 | `<NO>` |
| LB Host Key | `<ED25519 SHA256:FINGERPRINT>` |
| ansible01 `.10` Key Fingerprint | `<SHA256:FINGERPRINT>` |
| runner `.20` Key Fingerprint | `<SHA256:FINGERPRINT>` |
| Client Control | `IdentityAgent=none`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes` |
| LB Key Restriction | `from`, `restrict`, Forced Command |
| Authorized transfer key count after revoke | `<0>` |
| Protected Inbox file count after cleanup | `<0>` |
| Evidence | `18a_secure_evidence_transfer_control.txt`, `18b_secure_transfer_ansible_client.txt`, `18c_secure_transfer_runner_client.txt` |

## Pre-bootstrap backend result

| Backend | Result | Verdict |
|---|---|---|
| `10.1.93.102:6443` | `Connection refused` | PASS — Route reachable, API not started |
| `10.1.93.103:6443` | `Connection refused` | PASS — Route reachable, API not started |
| `10.1.93.104:6443` | `Connection refused` | PASS — Route reachable, API not started |

## Decision

- Stage A Result: `<PASS / Listener Ready | FAIL | Handoff Blocked>`
- P1-LB-01 Status: `In Progress`
- P1-K8S-01 Bootstrap: `<RELEASED | HOLD>`
- Open Item: Stage B Backend Health, authenticated API, failover, recovery/rejoin

## Reviewer notes

`<남은 조치, 예외, 승인 의견을 기록>`
