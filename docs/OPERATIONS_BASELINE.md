# LB 운영 기준과 확인 출처

2026-09-17 자료 편입 기준. 아래 관측은 각 원본의 수집 시점에 한정한다. 새 배포 또는 서버 설정 변경은 수행하지 않았다.

## HAProxy와 호스트

| 항목 | 기준 / 확인된 값 | 출처 |
|---|---|---|
| 호스트·NIC·주소 | k8s-api-lb01 / ens160 / 10.1.93.109/24 | Stage A 및 PR15 |
| API frontend | 10.1.93.109:6443, TCP TLS passthrough | [편입 cfg](../configs/haproxy.cfg) |
| backend | k8s-control01/02/03 → .102/.103/.104:6443, roundrobin·TCP check | 편입 cfg |
| check 기준 | inter 2s / fall 3 / rise 2, timeout check 5s | 편입 cfg |
| 실제 서비스 입력 | `/etc/haproxy/haproxy.cfg` + `/etc/haproxy/conf.d` | PR15 cmdline·파일 목록 |
| stats socket | `/var/lib/haproxy/stats`, mode 660, level admin | 편입 cfg |
| SELinux | Enforcing 및 haproxy_connect_any=on의 과거 확인 | [수신/보완 리뷰](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/received-20260907/19_stage_a_handoff_review.md), [Boolean 원본](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/received-20260907/11_selinux_boolean.txt) |
| 로그인 계정 | server01_k8s--api-lb / 실제 home `/home/server01_k8s--api-lb` | 제출 collector가 pwd로 조회한 결과 |

cfg SHA-256은 `afd19086ab8529d621185c231fa3c588eaeeb2025a08445e90f28cf27b00504f`다. cfg만 보관됐다는 사실로 conf.d·systemd·SELinux·firewalld 전체를 복원할 수 있다고 판단하지 않는다.

## 6443 Source 계약

목적지는 API LB `10.1.93.109:6443/TCP`. [D35](https://github.com/321Team/fds-project-baseline/blob/121fb744f0d816b3910a0bb07cf2bbe0d8883a16/releases/v3.1.15/D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0.md)와 기존 Runtime/Permanent 원본의 8개 /32 규칙을 대조했다.

| 계약 | source | LB 범위의 확인 |
|---|---|---|
| IF-11 | cicd-runner01 10.250.10.20/32 | 기존 TCP Positive; 인증 API는 별도 |
| IF-11A | control01/02/03 10.1.93.102/32, .103/32, .104/32 | 기존 Node Positive 포함 |
| IF-11A | worker01/02/03 10.1.93.105/32, .107/32, .108/32 | 기존 Node Positive 포함 |
| IF-06A | monitor01 10.250.10.30/32 | 규칙 보존; 실제 probe·장애복구는 P1-MON 소유 |
| Negative | ansible01 10.250.10.10 | API 6443 비허용 source; SSH 관리/증적 전송 역할과 구분 |

[9/9 Runtime](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/supplement-20260909T072022Z/raw/03_public_runtime.txt)과 [Permanent](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/supplement-20260909T072022Z/raw/04_public_permanent.txt)의 zone은 public, services는 dhcpv6-client·ssh, ports는 공란이다. 6443 zone-wide 개방 없이 8개 rich rule이 일치했다. Runtime interfaces=ens160, Permanent interfaces=공란이므로 전체 설정이 같다고 기록하지 않는다. 재부팅 지속성을 새로 검증한 자료도 아니다.

## LB → GitHub 접근 (infra-lb pull 전용)

2026-09-22 Lead(이권욱) 결정, 2026-09-22 **정정**. LB 서버(`k8s-api-lb01`)에서 Stage B preflight 등 실행 전 검토된 commit의 `infra-lb`를 직접 pull해야 할 필요가 확인됐다. 정본(baseline)에는 이 방향(LB→GitHub) 접근을 위한 별도 키 발급 절차가 없다 — 기존 [Secure Evidence Transfer Control](../archive/stage-a-completion-v1.3/P1-LB-01_Secure_Evidence_Transfer_Control_v1.0.md)은 반대 방향(LB→ansible01/cicd-runner01 증적 전송)의 source별 1회성 키·forced command 절차이며 이 사안과 목적·방향이 다르다.

**정정 사유:** 최초 결정(아래 이력)은 저장소 Deploy Key를 전제했으나, GitHub 저장소 Settings 조회에서 **321Team 조직 정책이 Deploy Key 생성 자체를 차단**하고 있음을 확인했다(`Deploy keys — Disabled by 321Team`, GitHub App 사용을 조직 차원에서 권고). 이 확인은 스크린샷 기준이며 조직 정책 문서 원문은 별도 확인 전이다. Deploy Key는 선택지에서 제외한다.

`docs/GOVERNANCE.md`의 "새 LB 서버 변경은 책임 Lead가 대상·근거·복구 조건을 확인해 결정한다" 원칙에 따라 방식은 아래로 재검토한다.

| 항목 | 값 |
|---|---|
| 방식 | **재검토 중** — 조직 정책상 GitHub App(Contents: Read, `infra-lb` 한정 설치) 후보. 기존 [FDS Project Sync 앱](https://github.com/321Team/fds-project-baseline/blob/main/governance/PROJECT_SYNC_RUNBOOK.md)은 범위(Issues/Projects, `fds-project-baseline` 전용, private key는 Actions Secret 전용)가 달라 재사용 불가 — 신규 App 필요 |
| 대상 저장소 | `321Team/infra-lb` (이 저장소 한정) |
| 대상 서버·계정 | `k8s-api-lb01` / `server01_k8s--api-lb` |
| 목적 | 검토된 commit의 `tools/stage-b/collect_preflight.py` 등 소스 pull. push·branch 생성 등 쓰기 동작 없음 |
| 미결정 사항 | App private key의 물리적 보관 위치(LB 서버 직접 보관 vs. ansible01 등 중개 서버가 보관하고 fresh token/파일만 LB로 전달) — 보안 설계 결정으로 Lead 확정 필요 |

**상태: RECONSIDERING — Deploy Key 방식은 조직 정책으로 사용 불가 확인, GitHub App 방식으로 재설계 중. 실제 등록 없음.**

<details>
<summary>정정 전 원래 결정 (참고용 이력, 실행되지 않음)</summary>

- 방식: 저장소 Deploy Key, 읽기 전용(Allow write access 미체크)
- 상태: DECIDED / 등록 준비 → 실제 등록 시도 중 조직 정책 차단 확인, 실행되지 않음

</details>

**현행 상태는 위 RECONSIDERING이다.** 기존 DECIDED / 등록 준비 문구는 철회된 Deploy Key안의 이력이다. 신규 App·키 보관 위치는 미확정이며 이번 후속에서 생성하지 않는다. 고정 SHA와 파일 해시를 포함한 전달 묶음으로 점검 소스를 옮길 수 있으므로 직접 pull 준비가 Stage B 사전점검을 차단하지 않는다.

## 현재 후속과 복구 참고

- 사전점검은 [LB_PREFLIGHT](runbooks/LB_PREFLIGHT.md), 인증 API와 failover는 각 runbook 및 미확정 실행 입력을 따른다.
- CP2/3 연결 거절은 9/17 당시 관측이다. 이슈9의 9/18 backend 3/3·9/21 API 복구 기록을 유지하고, 다음 장애 시험 직전에는 현재 3/3과 인증 API를 확인한다. 과거 미준비를 현행 차단으로 사용하지 않는다.
- [Stage A 구축 가이드 원본](../archive/stage-a-guide-v1.5/FDS_P1-LB-01_Stage_A_Build_Guide_v1.5.md)은 당시 구성/복구 절차의 참고 자료다. 현재 환경 재적용을 검증한 배포 지침이 아니다.
- 노션의 `haproxy.cfg.before-stage-a`와 `haproxy.cfg.failed-runtime-socket`은 경로·해시 기록만 확보했다. 백업 파일 실물·현재 복구 적합성은 확인하지 않았다. 특히 실패한 socket 설정을 복구 기준으로 선택하지 않는다.
- 공통 Node→LB 검사는 [infra-ansible playbook](https://github.com/321Team/infra-ansible/blob/57e7cc740e7a406387848c52f4aa56b98c516168/playbooks/p1-lb-01-stage-a-nodes.yml)에서 관리한다. CP firewall·ICR 소스는 infra-kubernetes에서 관리한다.
