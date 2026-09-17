# P1-LB-01 Stage A Secure Evidence Transfer Control v1.0

> **Record ID:** P1-LB-01-AC-01  
> **Parent Ticket:** P1-LB-01  
> **Date:** 2026-09-03  
> **Lead / Operational Owner:** 이권욱  
> **Reviewer / Stage A Receiver:** 이하영  
> **Canonical Baseline:** `FDS_Project_Implementation_Baseline_v3.1.15`  
> **Inherited Controls:** `D31`, `HO-ANS-07`, `HO-ANS-08`, `HO-ANS-09`  
> **Status:** READY FOR EXECUTION / RUNTIME EVIDENCE PENDING

## 1. 결정

Stage A Evidence 16~18은 암호 인증, SSH agent의 다중 키 제시 또는 기존 Kubernetes Node 관리키 재사용으로 전송하지 않는다. `ansible01(.10)`과 `cicd-runner01(.20)`에서 각각 생성한 Source별 일회성 ED25519 키를 사용하고, LB Console에서 확인한 ED25519 Host Key Fingerprint를 각 Source의 전용 `known_hosts`에 고정한다.

LB에는 Source 제한, OpenSSH `restrict`, 전용 Forced Command가 결합된 Public Key만 임시 등록한다. Forced Command는 승인된 파일명과 1 MiB 이하 Payload만 수신하고 전송 전·후 SHA-256이 일치할 때만 mode `0600`의 보호된 Inbox에 저장한다. 검증 후 Evidence 경로에 mode `0640`으로 병합하고 임시 Public/Private Key와 Inbox 사본을 폐기한다.

이 통제는 P1-ANS-01의 Node 관리키 범위를 확장하지 않으며, P1-ANS-01을 재개하지 않는다. LB의 `sshd_config`, Firewall, Route, SELinux Mode를 변경하지 않는 P1-LB-01 티켓 내부의 일회성 운영 접근 통제다.

## 2. 승인된 전송 계약

| Role | Source | 허용 파일 | 인증 키 | LB 제한 |
|---|---|---|---|---|
| ansible | `ansible01` / `10.250.10.10` | `16_positive_test_nodes.txt`, `18_negative_test.txt`, `18b_secure_transfer_ansible_client.txt` | Source 전용 일회성 ED25519 | `from=.10`, `restrict`, Forced Command |
| runner | `cicd-runner01` / `10.250.10.20` | `17_positive_test_runner.txt`, `18c_secure_transfer_runner_client.txt` | Source 전용 일회성 ED25519 | `from=.20`, `restrict`, Forced Command |

승인하지 않는 방식:

- `PubkeyAuthentication=no` 또는 Password/Keyboard-interactive 강제
- SSH agent의 비선택 다중 키 제시
- P1-ANS-01 Node 관리키를 LB 접속에 재사용
- Source 간 Private Key 복제 또는 공유
- `StrictHostKeyChecking=no`, `accept-new`, 검증되지 않은 `ssh-keyscan` 결과의 즉시 신뢰
- 일반 Shell/SCP 권한을 가진 임시 키
- `/tmp` 또는 mode가 통제되지 않은 공용 Staging
- Private Key, Passphrase, Password 원문의 Source/Log/Evidence 저장

## 3. 키 수명주기

| 단계 | 통제 |
|---|---|
| 발급 | 각 Source에서 `ed25519`, KDF rounds `100`, 비어 있지 않은 Passphrase로 생성 |
| 보관 | Private Key mode `0600`; 생성 Source 밖으로 복제 금지 |
| 등록 | LB Console에서 Public Key만 입력; Source IP, `restrict`, Forced Command 적용 |
| 사용 | `IdentityAgent=none`, `IdentitiesOnly=yes`, Publickey-only, Strict Host Key Checking |
| 만료 | Evidence 병합·검증 직후 또는 발급 후 24시간 중 먼저 도래하는 시점 |
| 폐기 | LB `authorized_keys`에서 Tag 제거·0건 확인 후 Source Private/Public Key 삭제 |
| 복구 | 실패 시 임시 키 폐기, Inbox 사본 제거, 기존 `authorized_keys` Backup으로 복구 후 재승인 |

키 Tag:

- `p1-lb-01-stage-a-ansible-20260903`
- `p1-lb-01-stage-a-runner-20260903`

## 4. Host Key 신뢰 설정

LB Console에서 다음 명령으로 서버 ED25519 Fingerprint를 확인한다.

```bash
sudo ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

출력된 `SHA256:<fingerprint>`를 음성·Console 화면 등 현재 SSH 세션과 독립된 경로로 각 Source 작업자에게 전달한다. Source에서는 Completion Pack의 `pin-host-key`가 `ssh-keyscan` 결과와 Console Fingerprint가 정확히 일치할 때만 전용 `known_hosts_p1_lb_01`을 mode `0600`으로 생성한다.

Fingerprint가 다르거나 LB Console Fingerprint를 확보하지 못하면 전송을 중지한다.

## 5. 실행 순서

### 5.1 LB Console — Receiver 준비

```bash
chmod +x \
  p1-lb-01-stage-a-transfer-lb.sh \
  p1-lb-01-stage-a-evidence-receiver.sh

./p1-lb-01-stage-a-transfer-lb.sh precheck

TRANSFER_CONTROL_APPROVED=YES \
./p1-lb-01-stage-a-transfer-lb.sh prepare
```

`precheck`에 출력된 LB ED25519 Fingerprint를 별도 경로로 Source 작업자에게 전달한다.

### 5.2 ansible01 — 키 생성·Host Key 고정

```bash
chmod +x p1-lb-01-stage-a-transfer-client.sh

./p1-lb-01-stage-a-transfer-client.sh prepare ansible

./p1-lb-01-stage-a-transfer-client.sh \
  pin-host-key '<LB_CONSOLE_ED25519_SHA256_FINGERPRINT>'
```

출력된 Public Key 한 줄만 LB Console의 다음 명령에 입력한다.

```bash
TRANSFER_CONTROL_APPROVED=YES \
./p1-lb-01-stage-a-transfer-lb.sh authorize ansible
```

### 5.3 cicd-runner01 — 키 생성·Host Key 고정

```bash
chmod +x p1-lb-01-stage-a-transfer-client.sh

./p1-lb-01-stage-a-transfer-client.sh prepare runner

./p1-lb-01-stage-a-transfer-client.sh \
  pin-host-key '<LB_CONSOLE_ED25519_SHA256_FINGERPRINT>'
```

출력된 Public Key 한 줄만 LB Console의 다음 명령에 입력한다.

```bash
TRANSFER_CONTROL_APPROVED=YES \
./p1-lb-01-stage-a-transfer-lb.sh authorize runner
```

### 5.4 기존 Evidence 16~18 전송

ansible01:

```bash
./p1-lb-01-stage-a-transfer-client.sh send ansible \
  /home/server01_ansible/p1-ans-01/stage-a-output/16_positive_test_nodes.txt \
  3386bfd4cf821c16aa3b522cfa11dafcca72e3c63124b1c1d19b65761eedfcc2

./p1-lb-01-stage-a-transfer-client.sh send ansible \
  /tmp/18_negative_test.txt \
  4cf3d23fe3d2b019aedb15604667c226f706b48d3879e2ccff3dc2182e50361c
```

cicd-runner01:

```bash
./p1-lb-01-stage-a-transfer-client.sh send runner \
  /tmp/17_positive_test_runner.txt \
  1e6b8d5f9f44deb8be37cf9b6bbdb8d93942a454a714b23196118825827cdb54
```

### 5.5 Client 통제 Evidence 발행·전송

ansible01:

```bash
./p1-lb-01-stage-a-transfer-client.sh export-control-evidence ansible
ansible_control_file="${HOME}/.local/state/p1-lb-01-stage-a-transfer/18b_secure_transfer_ansible_client.txt"
ansible_control_sha="$(sha256sum "$ansible_control_file" | awk '{print $1}')"

./p1-lb-01-stage-a-transfer-client.sh send ansible \
  "$ansible_control_file" "$ansible_control_sha"
```

cicd-runner01:

```bash
./p1-lb-01-stage-a-transfer-client.sh export-control-evidence runner
runner_control_file="${HOME}/.local/state/p1-lb-01-stage-a-transfer/18c_secure_transfer_runner_client.txt"
runner_control_sha="$(sha256sum "$runner_control_file" | awk '{print $1}')"

./p1-lb-01-stage-a-transfer-client.sh send runner \
  "$runner_control_file" "$runner_control_sha"
```

### 5.6 LB Console — 병합

다음 세 Hash는 현재 발행된 Evidence 16~18의 승인값이다.

```bash
./p1-lb-01-stage-a-transfer-lb.sh merge \
  16_positive_test_nodes.txt \
  3386bfd4cf821c16aa3b522cfa11dafcca72e3c63124b1c1d19b65761eedfcc2

./p1-lb-01-stage-a-transfer-lb.sh merge \
  17_positive_test_runner.txt \
  1e6b8d5f9f44deb8be37cf9b6bbdb8d93942a454a714b23196118825827cdb54

./p1-lb-01-stage-a-transfer-lb.sh merge \
  18_negative_test.txt \
  4cf3d23fe3d2b019aedb15604667c226f706b48d3879e2ccff3dc2182e50361c
```

Client 통제 파일은 실행 시 생성된 Hash를 사용한다.

```bash
ansible_control_sha='<18B_SHA256>'
runner_control_sha='<18C_SHA256>'

./p1-lb-01-stage-a-transfer-lb.sh merge \
  18b_secure_transfer_ansible_client.txt "$ansible_control_sha"

./p1-lb-01-stage-a-transfer-lb.sh merge \
  18c_secure_transfer_runner_client.txt "$runner_control_sha"
```

### 5.7 LB 키 폐기 및 Evidence 18a 발행

```bash
TRANSFER_REVOKE_APPROVED=YES \
./p1-lb-01-stage-a-transfer-lb.sh revoke-and-evidence
```

성공 시 다음 파일을 발행한다.

```text
/var/log/fds-evidence/P1-LB-01/stage-a/18a_secure_evidence_transfer_control.txt
```

### 5.8 Source Private Key 폐기

LB 출력이 `TRANSFER_KEYS_REVOKED_AND_EVIDENCE_ISSUED`이고 Evidence 18a가 `verdict=PASS`인 것을 확인한 후 실행한다.

ansible01:

```bash
TRANSFER_REVOKE_APPROVED=YES \
./p1-lb-01-stage-a-transfer-client.sh revoke-local ansible
```

cicd-runner01:

```bash
TRANSFER_REVOKE_APPROVED=YES \
./p1-lb-01-stage-a-transfer-client.sh revoke-local runner
```

## 6. Evidence 계약

| Evidence | 생성 위치 | 필수 검증 |
|---|---|---|
| `18a_secure_evidence_transfer_control.txt` | LB | Publickey 수락 Log, Source/Key Fingerprint, Forced Command, 병합 Hash/Mode, 키 폐기 0건, Inbox 정리 |
| `18b_secure_transfer_ansible_client.txt` | ansible01→LB | `.10`, Host Key Pinning, Publickey-only, `IdentitiesOnly=yes`, 16/18 전송 PASS |
| `18c_secure_transfer_runner_client.txt` | runner→LB | `.20`, Host Key Pinning, Publickey-only, `IdentitiesOnly=yes`, 17 전송 PASS |
| `19_stage_a_handoff_review.md` | LB/Repository | 18a~18c 검토와 Reviewer 판정 |
| `99_SHA256SUMS.txt` | LB/Repository | 01~19 및 18a~18c 전체 무결성 |

## 7. Acceptance Criteria

- [ ] Source별 Private Key가 서로 다르고 mode `0600`이다.
- [ ] LB Console ED25519 Fingerprint와 Source 고정값이 일치한다.
- [ ] Password/Keyboard-interactive가 Client에서 비활성화됐다.
- [ ] `IdentityAgent=none`, `IdentitiesOnly=yes`, `StrictHostKeyChecking=yes`가 적용됐다.
- [ ] LB Public Key에 `from`, `restrict`, Forced Command가 적용됐다.
- [ ] Evidence 16/17/18의 SHA-256과 의미 검증이 PASS다.
- [ ] Evidence 18a/18b/18c가 존재하고 mode `0640`이다.
- [ ] 임시 Public Key Tag가 LB `authorized_keys`에서 0건이다.
- [ ] 보호된 Inbox 파일이 0건이다.
- [ ] Source별 임시 Private Key가 폐기됐다.
- [ ] `99_SHA256SUMS.txt` 전체 검증이 PASS다.

하나라도 미충족이면 `Stage A Result: Handoff Blocked`, `P1-K8S-01 Bootstrap: HOLD`를 유지한다.

## 8. 책임 및 검증 주체

| 항목 | 실행 | 검증/승인 |
|---|---|---|
| Source별 키 생성·전송·폐기 | 이권욱 | 이하영 |
| LB Host Key Console 확인 | 이권욱 | 이하영 |
| LB 임시 Public Key 등록·폐기 | 이권욱 | 이하영 |
| Evidence 16~18 Hash·의미 검증 | 이권욱 | 이하영 |
| Evidence 18a~18c 및 Manifest | 이권욱 | 이하영 |
| P1-K8S Bootstrap 해제 | 이하영 | Stage A Handoff 승인 후 수행 |

## 9. Rollback

1. 전송 실패 시 추가 재시도 전에 LB `authorized_keys` Backup과 현재 Tag를 비교한다.
2. Tag 2개를 제거하고 0건을 확인한다.
3. 보호된 Inbox의 승인 파일만 삭제한다. Evidence 경로에 설치된 파일은 삭제하지 않고 Hash와 상태를 검토한다.
4. Source의 임시 Private Key를 폐기한다.
5. 원인을 수정한 새 키를 발급하고 Reviewer 재승인 후 처음부터 수행한다.

Password 인증 전환, Host Key 검증 완화 또는 기존 Node 관리키 재사용을 Rollback으로 사용하지 않는다.
