# Kubernetes API Load Balancer

Calendar Days: 8
Category: Infrastructure / Load Balancer
End: 2026/09/03
Exit Criteria: 10.1.93.109:6443가 CP 10.1.93.102~104:6443로 전달되고 Backend Health·API 접근·장애 시 동작 Evidence 확보
Lead: 권욱
Phase: Phase 1
Priority: P0
Record ID: P1-LB-01
Related Decision IDs: D02; D05; D27
Related Risk IDs: RISK-02; RISK-03; RISK-04
Schedule Note: Stage A에서 .109:6443 Listener와 .102~.104 Backend 정의를 먼저 준비해 P1-K8S-01 Bootstrap을 해제한다. CP API 기동 후 Stage B Backend Health·API 접근·단일 Backend 장애 Test를 수행해 종결한다. DEC-P1-ENTRY-01은 직접 선행조건이 아니다.
Source: FDS_Project_Implementation_Baseline_v3.1.7
FDS_Network_Baseline_v2.3
FDS_Phase1_Logical_Architecture_v3.1.2
Start: 2026/08/27
Status: In Progress
Support: HaYoungLee
Type: Task
Working Days: 6

# 🎯 User Story

인프라 담당자로서 `k8s-api-lb01(10.1.93.109)`에 단일 Kubernetes API Endpoint를 제공한다. 이를 통해 Control Plane 개별 주소 변경 없이 `10.1.93.109:6443`을 기준으로 kubeadm Bootstrap, Control Plane Join, Worker Join 및 운영 접근을 일관되게 수행한다.

---

# 📌 Scope

## In Scope

### Stage A — Listener 및 Bootstrap 경로 준비

- `k8s-api-lb01`: `10.1.93.109:6443`
- HAProxy TCP/TLS Pass-through Listener
- Control Plane Backend:
    - `k8s-control01`: `10.1.93.102:6443`
    - `k8s-control02`: `10.1.93.103:6443`
    - `k8s-control03`: `10.1.93.104:6443`
- HAProxy TCP Health Check
- LB 및 Control Plane Host Firewall
- SELinux Enforcing 호환 구성
- IF-11 Management Source 접근 통제
- IF-11A Kubernetes Node 접근 통제
- 구성 백업·검증·Rollback
- Stage A 구축 및 운영 Runbook

### Stage B — Kubernetes API 기동 후 검증

- Control Plane Backend 3대 Health `UP`
- `10.1.93.109:6443` Kubernetes API 접근
- 인증된 API 요청 검증
- Backend 1대 중지·복구 시험
- 잔여 Backend를 통한 API 경로 지속성 검증
- Stage B 운영 및 장애 대응 Runbook

## Out of Scope

- Application External Entry `10.1.93.50:80/443`
- Application NodePort 및 Ingress 구성
- Calico 및 Kubernetes NetworkPolicy
- Harbor, PostgreSQL, Application 및 Monitoring 구성
- D-SEC-01에서 승인되지 않은 보안통제
- 명시되지 않은 P1/P2 기능과 Scope Out 기능

---

# 📋 핵심 요구사항

- [x]  HAProxy Listener와 Control Plane Backend를 구성 파일로 관리한다.
- [x]  Frontend와 Backend를 모두 `mode tcp`로 구성하여 Kubernetes API TLS Pass-through를 유지한다.
- [x]  `option tcp-check`와 Health Check 기준을 적용하여 비정상 Backend를 자동 제외한다.
- [x]  IF-11에 따라 `cicd-runner01(10.250.10.20)`의 `10.1.93.109:6443` 접근만 허용한다.
- [x]  비허용 Management Source `ansible01(10.250.10.10)`의 접근을 차단한다.
- [x]  LB에서 Control Plane 3대의 TCP 6443 경로가 방화벽을 통과하도록 구성한다.
- [x]  Control Plane 3대에서 `10.1.93.109/32 → TCP 6443`만 Source 제한 방식으로 허용한다.
- [x]  LB 및 Control Plane에서 Cockpit Socket과 TCP 9090 노출을 제거한다.
- [ ]  IF-11A에 대한 이권욱·이하영의 검토 및 승인을 기록한다.
- [ ]  승인된 IF-11A에 따라 Kubernetes Node 6대의 `10.1.93.109:6443` 접근 규칙을 적용한다.
- [ ]  kubeadm `controlPlaneEndpoint`를 `10.1.93.109:6443`으로 적용한다.
- [ ]  Kubernetes API Server 인증서에서 `10.1.93.109`에 대한 TLS 검증이 가능하도록 SAN 구성을 확인한다.

---

# ✅ Acceptance Criteria

## Stage A

- [x]  `k8s-api-lb01`의 `10.1.93.109:6443` HAProxy Listener가 기동한다.
- [x]  HAProxy 서비스가 `enabled / active` 상태로 동작한다.
- [x]  HAProxy 구성 검사가 `Configuration file is valid / RC=0`으로 완료된다.
- [x]  HAProxy Runtime Socket `/var/lib/haproxy/stats`가 정상 생성된다.
- [x]  SELinux가 `Enforcing` 상태이며 HAProxy 관련 AVC가 발생하지 않는다.
- [x]  `cicd-runner01(10.250.10.20) → 10.1.93.109:6443` TCP 연결이 성공한다.
- [x]  `ansible01(10.250.10.10) → 10.1.93.109:6443` TCP 연결이 차단된다.
- [x]  LB에서 Control Plane `.102/.103/.104:6443` 연결 결과가 `No route to host`에서 `Connection refused`로 전환된다.
- [x]  kube-apiserver 미기동 상태에서 Control Plane Backend가 `DOWN / Connection refused`로 표시된다.
- [x]  Control Plane 3대의 SSH Runtime/Permanent 서비스 및 TCP 22 Listener가 정상임을 확인한다.
- [x]  LB 및 Control Plane 3대의 Cockpit Socket이 `disabled / inactive`이며 TCP 9090 Listener가 없음을 확인한다.
- [ ]  IF-11A 승인 기록을 확보한다.
- [ ]  IF-11A 승인 후 Control Plane·Worker 6대에서 `10.1.93.109:6443` 접근을 검증한다.
- [ ]  구성·검증·Rollback Evidence와 SHA-256 정보를 `docs/evidence/P1-LB-01/`에 저장한다.
- [ ]  Stage A 인계 기록을 작성하고 이하영에게 P1-K8S-01 Bootstrap을 인계한다.

## Stage B

- [ ]  kube-apiserver 기동 후 Control Plane 3대가 HAProxy Backend `UP`으로 표시된다.
- [ ]  `10.1.93.109:6443`을 통한 Kubernetes API 접근이 성공한다.
- [ ]  kubeconfig를 사용한 인증 API 요청이 성공한다.
- [ ]  Backend 1대 중지 시 나머지 Control Plane을 통해 API 경로가 유지된다.
- [ ]  중지한 Backend 복구 후 Health가 다시 `UP`으로 전환된다.
- [ ]  Stage B 구성·API·장애·복구 Evidence가 저장된다.

---

# 🧪 검증 및 증적

## 현재 확보된 Stage A 결과

| 검증 항목 | 실제 결과 | 판정 |
| --- | --- | --- |
| LB Hostname | `k8s-api-lb01` | PASS |
| LB 주소 | `10.1.93.109/24` | PASS |
| HAProxy 버전 | `3.0.5-8.el10` | PASS |
| HAProxy Config | `Configuration file is valid / RC=0` | PASS |
| HAProxy 서비스 | `enabled / active` | PASS |
| API Listener | `10.1.93.109:6443 LISTEN` | PASS |
| Runtime Socket | `/var/lib/haproxy/stats` | PASS |
| SELinux | `Enforcing`, 관련 AVC 없음 | PASS |
| IF-11 Positive | `.20 → .109:6443`, Connected, RC=0 | PASS |
| IF-11 Negative | `.10 → .109:6443`, TIMEOUT, RC=1 | PASS |
| LB → CP01 | `.109 → .102:6443`, Connection refused | PASS |
| LB → CP02 | `.109 → .103:6443`, Connection refused | PASS |
| LB → CP03 | `.109 → .104:6443`, Connection refused | PASS |
| Backend 상태 | 3대 모두 `DOWN / Connection refused` | Expected |
| Control Plane SSH | Runtime/Permanent `yes`, TCP 22 LISTEN | PASS |
| Cockpit | LB·CP 3대 `disabled / inactive`, TCP 9090 없음 | PASS |

## Runtime Socket 장애 및 조치

- 최초 구성:
    - `/run/haproxy/admin.sock`
- 장애:
    - HAProxy 기동 실패
    - `cannot bind UNIX socket (No such file or directory)`
- 조치:
    - Runtime Socket을 `/var/lib/haproxy/stats`로 변경
    - HAProxy Config 재검증
    - 서비스 재기동
- 최종 결과:
    - HAProxy `enabled / active`
    - Runtime Socket 생성
    - SELinux Context `haproxy_var_lib_t`
    - 관련 AVC 없음

## 구성 백업

- 초기 구성 백업:
    - `/var/backups/fds/P1-LB-01/haproxy.cfg.before-stage-a`
    - SHA-256: `8afc9a0bcc462f08af54b6ac1cbfc3b8343b1feee00b4ab07d7a8c7b47065f0b`
- Runtime Socket 장애 구성:
    - `/var/backups/fds/P1-LB-01/haproxy.cfg.failed-runtime-socket`
    - SHA-256: `0f1b7502daa0b41416b7056d3225ef8efd7ec5f57751770347ddd2a7dd1b173c`

## Stage B 대기 증적

- Control Plane Backend Health `UP`
- Kubernetes API TCP 및 TLS 검증
- 인증 API 요청
- 단일 Backend 장애·복구
- API 경로 지속성
- 최종 구성 및 Evidence SHA-256

## Evidence Path

`docs/evidence/P1-LB-01/`

---

# 🔗 Dependency

- **Blocked By:** D-NET-01, P1-LNX-01, P1-NET-01 — `DONE/CLOSED`
- **Stage A 선행 증적:** P1-ANS-01 Node Bootstrap Evidence — 확인 완료
- **Stage A 현재 차단 항목:** IF-11A 검토·승인 및 Kubernetes Node 6대 접근 검증
- **Blocks / Next:** Stage A `Listener Ready` → P1-K8S-01 Bootstrap
- **Stage B 선행조건:** Control Plane API 기동
- **Stage B Next:** Backend Health·인증 API·단일 Backend 장애 검증 후 P1-LB-01 종결
- **후행 영향:** P1-CICD-01
- **Related Ticket:** P1-K8S-01, P1-SEC-01
- **Non-blocking Decision:** DEC-P1-ENTRY-01
- **Milestone:** G1 Infrastructure Ready

---

# ⚖️ Decision / Risk Control

- **Related Decision IDs:** D02; D05; D27
- **Decision Control:** 관련 Decision Register를 준수하며 신규 의사결정이 발생하면 별도 Decision 레코드를 발행한다.
- **IF-11:** `cicd-runner01(10.250.10.20) → k8s-api-lb01(10.1.93.109):6443`
- **IF-11A 승인 대상:**
    - `k8s-control01(10.1.93.102) → 10.1.93.109:6443`
    - `k8s-control02(10.1.93.103) → 10.1.93.109:6443`
    - `k8s-control03(10.1.93.104) → 10.1.93.109:6443`
    - `k8s-worker01(10.1.93.105) → 10.1.93.109:6443`
    - `k8s-worker02(10.1.93.107) → 10.1.93.109:6443`
    - `k8s-worker03(10.1.93.108) → 10.1.93.109:6443`
- **IF-11A 승인 책임:** 이권욱·이하영
- **Firewall Control:** TCP 6443 전역 개방을 금지하고 승인된 Source만 허용한다.
- **Related Risk IDs:** RISK-02; RISK-03; RISK-04
- **Risk Control:** 관련 Risk의 예방·탐지·복구 통제를 Acceptance와 Evidence에 연결한다.

---

# 📝 Completion Record

- **Result:** Node Bootstrap Evidence 확인 완료 / HAProxy Listener 구성 완료 / IF-11 Positive·Negative Test PASS / LB→Control Plane Backend Path Preflight PASS / IF-11A 승인 대기
- **Stage A Result:** `Listener Configured / Handoff Blocked`
- **Status:** `In Progress`
- **Completed Items:**
    - `10.1.93.109:6443` HAProxy TCP Listener 구성
    - Control Plane `.102/.103/.104:6443` Backend 등록
    - HAProxy Config 및 Runtime Socket 검증
    - SELinux Enforcing 검증
    - LB·Control Plane Firewall 최소 허용 구성
    - IF-11 Positive·Negative Test
    - Control Plane Backend Path Preflight
    - LB 및 Control Plane Cockpit 제거
    - Control Plane SSH 접근 상태 검증
- **Open Items:**
    - IF-11A 검토·승인
    - Node 6대의 `10.1.93.109:6443` 접근 적용 및 검증
    - Stage A Evidence 파일화 및 SHA-256 저장
    - P1-K8S-01 Bootstrap 인계
    - Stage B Backend Health·인증 API·단일 Backend 장애·복구 검증
- **Exit Criteria:** HO-ANS-04B 기준 Stage A Listener와 IF-11/IF-11A 검증 Evidence, Stage B Backend Health·API 접근·단일 Backend 장애·복구 Evidence를 모두 확보한다.
- **Completed Date:** 미입력
- **Support / Reviewer:** 이하영 — IF-11A 및 Stage A 단위 테스트·영향성 검토 대기
- **Approver:** 미입력
- **Next Action:** IF-11A 승인 후 Node Source Allowlist를 적용하고 P1-K8S-01 Bootstrap 인계 여부를 판정한다.

===============================================================

@HaYoungLee 확인 부탁드립니다.

===============================================================
Interface Register 누락과 보정안

현재 기준선의 IF-11은 `runner 10.250.10.20 → API LB 10.1.93.109:6443`만 정의한다. 그러나 kubeadm의 Control Plane·Worker Join과 이후 Node의 안정된 API Endpoint 사용에는 Kubernetes Node 6대가 `.109:6443`에 접근하는 경로가 필요하다. 따라서 다음 Interface를 보정·승인해야 한다.

| ID | Source → Destination | Protocol / Port | Purpose | Owner | Acceptance |
| --- | --- | --- | --- | --- | --- |
| IF-11A(보정안) | CP/Worker `.102/.103/.104/.105/.107/.108` → API LB `.109` | TCP 6443 | kubeadm init/join 및 Node→Kubernetes API | 이권욱 / 이하영 | CP/Worker Positive, 미승인 Source Negative, Source IP 확인 |
- Endpoint와 Port는 변경하지 않는다.
- Source/Consumer 누락을 보완하는 Interface Change이므로 이권욱·이하영 검토 기록을 남긴다.
- IF-11A 승인 전에는 9장의 Node 6대 Rich Rule을 적용하지 않는다.
- IF-11A 미승인 상태에서는 Runner Rule과 Listener 구성까지만 가능하며 P1-K8S Bootstrap은 해제하지 않는다.

===============================================================

IF-11 Positive Test
Source: cicd-runner01 / 10.250.10.20
Destination: k8s-api-lb01 / 10.1.93.109:6443
Result: Connected
Return Code: 0
Verdict: PASS

IF-11 Negative Test
Source: ansible01 / 10.250.10.10
Destination: k8s-api-lb01 / 10.1.93.109:6443
Result: TIMEOUT
Return Code: 1
Verdict: PASS

P1-LB-01: In Progress
HAProxy Listener: PASS
IF-11 Positive/Negative Test: PASS
LB → Control Plane Backend Path: PASS
Backend DOWN: Expected — kube-apiserver 미기동
IF-11A: 승인 대기
P1-K8S Handoff: Blocked

IF-11A 승인 범위
10.1.93.102 → 10.1.93.109:6443
10.1.93.103 → 10.1.93.109:6443
10.1.93.104 → 10.1.93.109:6443
10.1.93.105 → 10.1.93.109:6443
10.1.93.107 → 10.1.93.109:6443
10.1.93.108 → 10.1.93.109:6443

Protocol: TCP
Purpose: kubeadm init/join 및 Kubernetes Node의 API Server 접근
Application Entry와 분리
전역 6443 개방 금지