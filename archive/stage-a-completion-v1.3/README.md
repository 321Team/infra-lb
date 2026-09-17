# P1-LB-01 Stage A 완료 실행 팩 v1.3

> Canonical Baseline: `FDS_Project_Implementation_Baseline_v3.1.15`  
> Parent Guide: `FDS_P1-LB-01_Stage_A_Build_Guide_v1.5`  
> Approval: `D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0`  
> 목적: IF-11A 적용, Source별 Listener 검증, Evidence 수집 및 Stage A Handoff 판정

## 1. 현재 판정

LB `k8s-api-lb01`에서 수행한 CP Backend 사전 시험 결과는 다음과 같다.

| Destination | 결과 | Stage A 판정 |
|---|---|---|
| `10.1.93.102:6443` | Connection refused | PASS — 경로 도달, API 미기동 |
| `10.1.93.103:6443` | Connection refused | PASS — 경로 도달, API 미기동 |
| `10.1.93.104:6443` | Connection refused | PASS — 경로 도달, API 미기동 |

이 결과는 LB→CP Pre-bootstrap 경로만 PASS한 것이다. IF-11A 설계 승인은 D35로 완료됐지만 Stage A 전체 PASS에는 Rule 적용, Node/Runner Positive, 미승인 Source Negative 및 Evidence/Handoff가 추가로 필요하다.

## 2. 파일

| 파일 | 실행 위치 | 용도 |
|---|---|---|
| `p1-lb-01-stage-a-lb.sh` | k8s-api-lb01 | LB Precheck, IF-11/IF-11A 적용, Evidence 수집·해시 생성 |
| `p1-lb-01-stage-a-nodes.yml` | ansible01 | K8s Node 6대→API LB Positive Test |
| `p1-lb-01-stage-a-client-test.sh` | runner 또는 미승인 Source | Runner Positive / 미승인 Source Negative Test |
| `p1-lb-01-stage-a-transfer-client.sh` | ansible01 / runner | Source별 일회성 Key 생성, Host Key Pinning, 정책 통제 전송 |
| `p1-lb-01-stage-a-transfer-lb.sh` | k8s-api-lb01 Console | 전용 Receiver 준비, Public Key 제한 등록, 병합·폐기·Evidence 18a 발행 |
| `p1-lb-01-stage-a-evidence-receiver.sh` | k8s-api-lb01 | Forced Command 전용 수신기; 파일명·크기·Source·SHA-256 제한 |
| `P1-LB-01_Secure_Evidence_Transfer_Control_v1.0.md` | 모든 실행 Host | 승인된 Evidence 전송 계약과 실행 절차 |
| `FDS_P1-LB-01_Secure_Transfer_Validation_Evidence_v1.0.md` | 배포/검토 위치 | 스크립트·Receiver·Key 제한 사전 검증 증적 |
| `19_stage_a_handoff_review.template.md` | 문서 작업 위치 | Stage A 인계 승인 기록 |

## 3. 실행 전 조건

1. VMware Console 또는 동등한 복구 경로를 확보한다.
2. D35 IF-11A 승인 Record와 Evidence Hash를 확인한다.
3. LB에서 firewalld 적용 Zone과 Bridged Interface가 실제 값인지 확인한다.
4. 기존 `6443/tcp` 광역 Port Open이나 소유 불명 Rule이 있으면 먼저 중지하고 검토한다.
5. Evidence 전송은 Password 우회, 기존 Node 관리키 재사용, `StrictHostKeyChecking` 완화를 금지한다.
6. LB Console에서 확인한 ED25519 Host Key Fingerprint를 Source별 전용 `known_hosts`에 고정한다.

`IF11A_APPROVED=YES`는 D35 승인본을 확인했다는 실행 가드이며 승인 자체를 대체하지 않는다.

## 4. LB Precheck

```bash
chmod +x p1-lb-01-stage-a-lb.sh
./p1-lb-01-stage-a-lb.sh precheck
```

기대값:

- LB Interface: `ens160`
- LB Endpoint: `10.1.93.109:6443`
- firewalld: enabled / active
- HAProxy: enabled / active
- SELinux: Enforcing
- `haproxy_connect_any`: on
- HAProxy Stats Socket: `/etc/haproxy/haproxy.cfg`의 `stats socket` 값과 실제 Unix Socket 일치

자동 식별 결과가 실제 값과 다르면 임의 적용하지 않고 다음처럼 명시한다.

```bash
LB_INTERFACE=ens160 \
LB_ZONE=public \
BRIDGED_CONNECTION='<실제 NetworkManager Connection 이름>' \
./p1-lb-01-stage-a-lb.sh precheck
```

이 환경의 확인값은 `/var/lib/haproxy/stats`다. v1.3 스크립트는 HAProxy 설정에서 Socket을 우선 탐지하고, 필요할 때만 다음처럼 명시한다.

```bash
HAPROXY_STATS_SOCKET=/var/lib/haproxy/stats \
./p1-lb-01-stage-a-lb.sh precheck
```

## 5. IF-11/IF-11A/IF-06A Source Allowlist 적용

D35 승인 기록을 확인한 후 LB에서 실행한다.

```bash
IF11A_APPROVED=YES ./p1-lb-01-stage-a-lb.sh apply-firewall
```

적용 Source:

- K8s Node: `.102`, `.103`, `.104`, `.105`, `.107`, `.108` `/32`
- Runner: `10.250.10.20/32`
- monitor01: `10.250.10.30/32` — IF-06A 보존; 실제 Probe 검증은 P1-MON-01 소유

스크립트는 기존 Rich Rule을 백업하고 없는 Rule만 추가한다. `6443/tcp`가 Zone 전체에 광역 개방돼 있으면 오류로 중지한다.

## 6. K8s Node 6대 Positive Test

ansible01 `10.250.10.10`의 Ansible Project에 Playbook을 배치하고 실행한다.

```bash
ansible-inventory --graph
ansible-playbook p1-lb-01-stage-a-nodes.yml
```

Playbook은 TCP 시험을 ansible01에서 대신 실행하지 않고 각 `k8s_nodes` 원격 Host에서 실행한다. 성공 시 다음 파일이 생성된다.

```text
stage-a-output/16_positive_test_nodes.txt
```

실패가 있으면 Stage A를 PASS 처리하지 않는다. 각 Host의 `ip route get 10.1.93.109` 결과에 표시된 Source IP가 승인된 Node IP인지 확인한다.

## 7. Runner Positive Test

`cicd-runner01(10.250.10.20)`에서 실행한다.

```bash
chmod +x p1-lb-01-stage-a-client-test.sh
./p1-lb-01-stage-a-client-test.sh positive-runner
```

출력 파일:

```text
/tmp/17_positive_test_runner.txt
```

Route가 선택한 Source IP가 `.20`이 아니면 실패한다. Source NAT 또는 Route 변경 여부를 먼저 확인한다.

## 8. 미승인 Source Negative Test

ansible01 `10.250.10.10`은 승인 Source 목록에 없으므로 Negative Test Host로 사용한다. monitor01 `.30`은 IF-06A 승인 Source이므로 Negative Test에 사용하지 않는다.

```bash
chmod +x p1-lb-01-stage-a-client-test.sh
./p1-lb-01-stage-a-client-test.sh negative
```

출력 파일:

```text
/tmp/18_negative_test.txt
```

`nc` 종료값이 0이면 미승인 Source가 Listener에 도달한 것이므로 FAIL이다. 이때 LB의 Zone, 광역 Port, Service, Rich Rule과 실제 수신 Source IP를 확인한다.

## 9. LB Evidence 수집

LB에서 실행한다. 현재 사용자 출력도 유효한 판단 자료지만, 정식 Evidence에는 시간·Source·명령·판정이 포함돼야 하므로 재수집한다.

```bash
./p1-lb-01-stage-a-lb.sh collect
```

수집기는 확인된 Stats Socket을 자동 사용한다. `13_haproxy_stats.csv`가 비어 있으면 이후 `finalize`를 수행하지 않는다.

수집 위치:

```text
/var/log/fds-evidence/P1-LB-01/stage-a/
```

스크립트가 `01`~`15`를 생성하며 세 Backend가 모두 `PASS_ROUTE_API_NOT_STARTED`인지 검증한다.

## 10. 정책 통제 Evidence 전송과 병합

`Too many authentication failures`를 Password 인증으로 우회하지 않는다. 다음 통제를 필수 적용한다.

- ansible01과 runner에서 서로 다른 Passphrase 보호 ED25519 일회성 Key 사용
- LB Console ED25519 Fingerprint 대조 후 전용 `known_hosts` mode `0600`
- `IdentityAgent=none`, `IdentitiesOnly=yes`, Publickey-only, `StrictHostKeyChecking=yes`
- LB Public Key의 `from=<source>`, `restrict`, Evidence 전용 Forced Command
- 보호 Inbox mode `0700`, 수신 파일 mode `0600`, 최종 Evidence mode `0640`
- 전송·병합 후 LB Public Key와 Source Private Key 폐기

전체 명령과 승인 경계는 다음 문서를 따른다.

```text
P1-LB-01_Secure_Evidence_Transfer_Control_v1.0.md
```

실행 순서 요약:

```bash
# LB Console
./p1-lb-01-stage-a-transfer-lb.sh precheck
TRANSFER_CONTROL_APPROVED=YES ./p1-lb-01-stage-a-transfer-lb.sh prepare

# 각 Source
./p1-lb-01-stage-a-transfer-client.sh prepare <ansible|runner>
./p1-lb-01-stage-a-transfer-client.sh pin-host-key '<LB_CONSOLE_FINGERPRINT>'

# LB Console에서 Source별 Public Key만 제한 등록
TRANSFER_CONTROL_APPROVED=YES ./p1-lb-01-stage-a-transfer-lb.sh authorize <ansible|runner>
```

Receiver는 승인 파일 외 Shell Command를 실행하지 않는다. 기존 Evidence Hash는 다음과 같다.

| Evidence | SHA-256 |
|---|---|
| `16_positive_test_nodes.txt` | `3386bfd4cf821c16aa3b522cfa11dafcca72e3c63124b1c1d19b65761eedfcc2` |
| `17_positive_test_runner.txt` | `1e6b8d5f9f44deb8be37cf9b6bbdb8d93942a454a714b23196118825827cdb54` |
| `18_negative_test.txt` | `4cf3d23fe3d2b019aedb15604667c226f706b48d3879e2ccff3dc2182e50361c` |

전송 완료 후 Client 통제 Evidence 18b/18c도 동일한 경로로 전송·병합한다. LB에서 임시 Key를 폐기하면 Evidence 18a가 생성된다.

```text
18a_secure_evidence_transfer_control.txt
18b_secure_transfer_ansible_client.txt
18c_secure_transfer_runner_client.txt
```

기존 v1.2 실행에서 mode `0644`로 생성된 파일이 있으면 검토 후 다음 명령으로 Evidence 파일을 `0640`으로 정규화한다.

```bash
EVIDENCE_PERMISSION_APPROVED=YES \
./p1-lb-01-stage-a-lb.sh normalize-evidence
```

`19_stage_a_handoff_review.template.md`를 `19_stage_a_handoff_review.md`로 복사한 뒤 18a~18c의 실제 검증 결과와 승인 기록을 입력한다. 빈 체크박스를 PASS로 간주하지 않는다.

## 11. SHA256 Manifest 생성

Evidence 01~19와 전송 통제 Annex 18a~18c가 모두 채워진 뒤 LB에서 실행한다.

```bash
./p1-lb-01-stage-a-lb.sh finalize
```

최종 생성 파일:

```text
/var/log/fds-evidence/P1-LB-01/stage-a/99_SHA256SUMS.txt
```

이후 승인된 Repository의 아래 경로로 복사하고 Commit ID를 Handoff 문서에 기록한다.

```text
docs/evidence/P1-LB-01/stage-a/
```

## 12. 최종 판정

다음 조건을 모두 충족한 경우에만 기록한다.

```text
P1-LB-01 Status: In Progress
Stage A Result: PASS / Listener Ready
P1-K8S-01 Bootstrap: RELEASED
Open Item: Stage B Backend Health / API / Failover
```

Node/Runner Positive, ansible01 Negative, IF-11/IF-11A/IF-06A Rule, 전송 통제 18a~18c, Evidence 또는 Hash 중 하나라도 미완료면 다음 상태를 유지한다.

```text
Stage A Result: Listener Configured / Handoff Blocked
P1-K8S-01 Bootstrap: HOLD
```

## 13. 결과 해석 주의사항

- `LB → CP nc`: `Connection refused`는 kube-apiserver 미기동 상태에서 경로 PASS다.
- `Node/Runner → LB nc`: TCP Handshake가 수락돼야 Positive PASS다.
- Backend가 모두 DOWN이면 HAProxy가 연결 직후 종료할 수 있으나 Stage A API 기능 실패는 아니다.
- Backend 3대 `UP`, 인증 API, 단일 Backend 장애 및 복구 시험은 Stage B 범위다.
- `Too many authentication failures`는 API LB Firewall 실패가 아니라 SSH Identity 선택 실패다. Password 인증으로 우회하지 않는다.
