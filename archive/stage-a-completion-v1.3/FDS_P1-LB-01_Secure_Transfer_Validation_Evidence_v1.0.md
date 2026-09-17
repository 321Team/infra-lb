# P1-LB-01 Secure Transfer Validation Evidence v1.0

> Validation Date: `2026-09-03`  
> Target: `P1-LB-01_Stage_A_Completion_Pack_v1.3`  
> Result: `STATIC / ISOLATED TEST PASS`  
> Runtime Boundary: 실제 ansible01·runner·LB 전송 및 Reviewer 승인은 미수행

## 1. 검증 대상 무결성

| 파일 | SHA-256 |
|---|---|
| `p1-lb-01-stage-a-lb.sh` | `ec6ec7c12ac5507efc28f1a707523a57cd5f93238db3a250e3902f11f5d4d103` |
| `p1-lb-01-stage-a-client-test.sh` | `c03522901653eb8749f334a0c12ecbdca29f20173c055d3d071870f48403fc53` |
| `p1-lb-01-stage-a-nodes.yml` | `92b1893cd9a773aeb9b822269f09763e71a196c34f99accdc596377755fc3946` |
| `p1-lb-01-stage-a-transfer-client.sh` | `4d0d1fce2410b8e189767da29248b6e1547468204bbbd9660be393df2acc695f` |
| `p1-lb-01-stage-a-transfer-lb.sh` | `d91902cfda6297cdda99eecdec3c77fe471e95085990af70967d2a4c06df1dcb` |
| `p1-lb-01-stage-a-evidence-receiver.sh` | `503dd7bb7c824c050eb61dabfdc493ca84329526208a9cca67f30df0e07929df` |

## 2. 정적 검증

| 검증 | 결과 |
|---|---|
| Shell Script 5종 `bash -n` | PASS |
| Ansible Playbook YAML Parse | PASS |
| `shellcheck` | N/A — 검증 환경에 미설치 |

## 3. Evidence Receiver 격리 시험

임시 mode `0700` Inbox에서 Receiver를 직접 호출해 허용·거부 경계를 시험했다.

| TC | 입력 | 기대 | 실제 | 판정 |
|---|---|---|---|---|
| TR-RCV-01 | role `ansible`, Source `.10`, 승인 파일명, 일치 SHA-256 | 수신 허용 | exit `0`, `UPLOAD_OK` | PASS |
| TR-RCV-02 | role `ansible`, Source `.99` | Source 차단 | exit `21` | PASS |
| TR-RCV-03 | 승인되지 않은 파일명 | 파일명 차단 | exit `23` | PASS |
| TR-RCV-04 | 수신 Inbox | mode `0700` | `700` | PASS |
| TR-RCV-05 | 수신 파일 | mode `0600` | `600` | PASS |

## 4. Client Key 통제 시험

| TC | 입력 | 기대 | 실제 | 판정 |
|---|---|---|---|---|
| TR-KEY-01 | 비어 있지 않은 Passphrase | Key 생성, Private mode `0600` | exit `0`, mode `600` | PASS |
| TR-KEY-02 | 빈 Passphrase | 생성 거부 및 파일 제거 | exit `3`, Key 잔존 `no` | PASS |

## 5. LB Authorization 제한 시험

격리된 임시 HOME에서 ansible 역할 Public Key를 등록했다.

| 검증 | 실제 | 판정 |
|---|---|---|
| Source 제한 | `from="10.250.10.10"` | PASS |
| OpenSSH 제한 | `restrict` | PASS |
| 명령 제한 | Evidence Receiver Forced Command | PASS |
| `authorized_keys` mode | `0600` | PASS |
| Inbox mode | `0700` | PASS |

## 6. 미검증 Runtime 항목

다음은 실제 Host에서 수행해야 하며 본 검증 Evidence로 PASS를 대체할 수 없다.

- LB Console ED25519 Host Key Fingerprint와 각 Source Scan 결과 일치
- ansible01 `.10`·runner `.20`에서 Publickey-only SSH 수락
- Evidence 16/17/18 및 18b/18c 실제 전송·병합
- LB sshd `Accepted publickey` Log
- LB 임시 Public Key 0건과 Inbox 0건
- Source별 Private Key 폐기
- Evidence 18a~18c, Evidence 19, `99_SHA256SUMS.txt`, Repository Commit ID
- 이하영 Reviewer의 Stage A Handoff 승인

## 7. 판정

```text
Secure Transfer Design/Tool Validation: PASS
Runtime Evidence: PENDING
Stage A Result: Listener Configured / Handoff Blocked
P1-K8S-01 Bootstrap: HOLD
```

Runtime 항목을 완료하기 전에는 Stage A `PASS / Listener Ready`로 전환하지 않는다.
