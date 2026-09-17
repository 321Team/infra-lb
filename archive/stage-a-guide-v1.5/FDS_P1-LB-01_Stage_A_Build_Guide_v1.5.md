# P1-LB-01 Stage A 구축 가이드 v1.5

> **Record ID:** P1-LB-01  
> **대상:** Kubernetes API Load Balancer Stage A  
> **작성일:** 2026-08-31  
> **Lead:** 이권욱  
> **Support / Stage A 인수:** 이하영  
> **Lifecycle Status:** In Progress  
> **Canonical Baseline:** `FDS_Project_Implementation_Baseline_v3.1.15`  
> **D35 영향:** IF-11A Node 6대→API LB를 승인하고 IF-06A monitor01 `.30/32`→API LB를 Source Allowlist에 보존한다. Kubernetes Node firewalld/Calico 통제는 P1-K8S-01·P1-SEC-01·ICR-D-NET-01-01로 분리한다.
> **문서 상태:** READY FOR DISTRIBUTION  
> **기준선:** `FDS_Project_Implementation_Baseline_v3.1.15`, `D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0`, `FDS_v3.1.15_Canonical_Ticket_Update_Pack_v1.0`
> **Runtime Pack:** `P1-LB-01_Stage_A_Completion_Pack_v1.3.zip` — Secure Evidence Transfer 및 Evidence 06/권한 보정본

---

## 1. 목적과 완료 경계

Stage A는 `10.1.93.109:6443`에 Kubernetes API용 HAProxy TCP Listener를 만들고, Control Plane `10.1.93.102~104:6443`를 Backend로 정의하여 `P1-K8S-01`의 kubeadm Bootstrap을 해제하는 단계다.

Stage A 완료 후에도 `P1-LB-01` 상태는 **In Progress**로 유지한다. 다음 항목은 Control Plane API 기동 후 Stage B에서 수행한다.

- Backend 3대 Health `UP`
- kubeconfig를 이용한 인증된 API 접근
- Backend 1대 중지 시 API 경로 지속
- Backend 복구와 재편입

### Stage A 대상 구성

| 구분 | 값 |
|---|---|
| 배치 Host | server01 — Windows Host `10.1.93.23` |
| VM | `k8s-api-lb01` |
| Windows 물리 NIC | `이더넷` — ifIndex `20` |
| VMware Network | `VMnet0` — Bridged to Windows `이더넷` |
| LB VM Bridged Interface | `ens160` |
| LB Endpoint | `10.1.93.109:6443/tcp` |
| Backend 1 | `k8s-control01` — `10.1.93.102:6443` |
| Backend 2 | `k8s-control02` — `10.1.93.103:6443` |
| Backend 3 | `k8s-control03` — `10.1.93.104:6443` |
| Management Deploy Source | `cicd-runner01` — `10.250.10.20` |
| External Monitoring Source | `monitor01` — `10.250.10.30/32` |
| Return Route | `10.250.10.0/24 via 10.1.93.58` |
| Load Balancing Mode | TCP / TLS Pass-through |
| Evidence 경로 | `docs/evidence/P1-LB-01/stage-a/` |

### 범위 제외

- Kubernetes/Calico Node Port Matrix — `P1-K8S-01`
- Application External Entry `.50:80/443 → NodePort 30080` — `P1-APP-01`, `P1-SEC-01`
- Kubernetes NetworkPolicy와 Pod Security — `P1-SEC-01`
- Backend Health·API·Failover 최종 검증 — P1-LB-01 Stage B

`externalTrafficPolicy: Local`은 Application NodePort 경로의 계약이다. `P1-LB-01` API LB `.109:6443`와 혼합하지 않는다. `P1-APP-01`은 transaction-api Replica와 topology/local endpoint를, `P1-SEC-01`은 `.50/32 → Worker:30080` preDNAT Allow/Deny를, edge01 구성 담당 이권욱은 backend health와 local endpoint가 없는 Worker 자동 제외를 검증한다.
- HAProxy HTTP 통계 페이지 — Stage A에서 외부 관리 Port를 추가하지 않음

---

## 2. 담당자별 착수 조건

| 구분 | 담당자 | 확인 사항 | Stage A 차단 여부 |
|---|---|---|---|
| LB VM·Network·HAProxy | 이권욱 | VMnet0, `.109`, HAProxy, Firewall, SELinux, Evidence | 필수 |
| Node Bootstrap Evidence | 이권욱 | P1-ANS-01 Done 증적 참조 | 충족 |
| kubeadm Endpoint | 이하영 | `controlPlaneEndpoint: 10.1.93.109:6443` 사용 | P1-K8S Bootstrap 전 필수 |
| API Server 인증서 | 이하영 | `.109`를 대상으로 TLS 검증 가능한 SAN 구성 확인 | P1-K8S Bootstrap 전 필수 |
| CP API Port | 이하영 | CP 3대에서 LB `.109` Source의 6443 접근 허용 | P1-K8S Preflight에서 수행 |
| Node → API LB Interface | 이권욱 / 이하영 | IF-11A D35 승인 확인 | 승인 완료; Runtime Evidence는 Stage A 필수 |
| monitor01 → API LB Interface | 이권욱 / 이재환 | IF-06A `.30/32` Rule 보존 | Rule 보존 필수; Probe Runtime은 P1-MON-01 |
| Stage A Evidence 전송 | 이권욱 | Source별 일회성 Key, Host Key Pinning, Forced Command, SHA-256, 키 폐기 | Handoff 전 필수 |
| Evidence 전송 검토 | 이하영 | Evidence 18a~18c, Key Tag 0건, Inbox 0건 | Bootstrap 해제 전 필수 |
| Application/Data | 이재환 | Stage A 직접 선행 작업 없음 | 비차단 |

### 2.1 IF-11A 승인 계약

기존 IF-11은 `runner 10.250.10.20 → API LB 10.1.93.109:6443`를 정의한다. kubeadm의 Control Plane·Worker Join과 이후 Node의 안정된 API Endpoint 사용에 필요한 다음 IF-11A는 D35로 승인·동결됐다.

| ID | Source → Destination | Protocol / Port | Purpose | Owner | Acceptance |
|---|---|---|---|---|---|
| IF-11A | CP/Worker `.102/.103/.104/.105/.107/.108` → API LB `.109` | TCP 6443 | kubeadm init/join 및 Node→Kubernetes API | 이권욱 / 이하영 | CP/Worker Positive, 미승인 Source Negative, Source IP 확인 |

- Endpoint와 Port는 변경하지 않는다.
- 승인 Evidence는 `D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0.md`를 사용한다.
- 실행 스크립트의 `IF11A_APPROVED=YES`는 승인 여부를 다시 결정하는 값이 아니라 D35 승인본을 확인했다는 실행 가드다.
- 승인 완료만으로 Stage A PASS가 되지 않는다. Node/Runner Positive, ansible01 `.10` Negative, Listener·Rule·Hash·Handoff Evidence가 모두 필요하다.
- IF-06A monitor01 `.30/32 → .109:6443`는 별도 기존 계약으로 보존하며, IF-11A 적용 중 삭제하거나 Negative Source로 사용하지 않는다.

---

## 3. 작업 전 중지 조건

다음 중 하나라도 확인되면 구성을 적용하지 않고 원인을 해소한다.

- `10.1.93.109`에 대한 ARP 응답이 이미 존재함
- server01의 VMnet0가 Windows `이더넷`에 Bridged로 연결되지 않음
- LB VM의 Bridged NIC 또는 실제 NetworkManager Connection을 식별하지 못함
- `.109/24`, Gateway `.254`, Return Route via `.58`가 기존 동결 Network와 충돌함
- 기존 프로세스가 `6443/tcp`를 사용 중임
- HAProxy 패키지 또는 Repository Source를 승인된 방식으로 확보할 수 없음
- 기존 Firewall/SELinux 구성을 백업하거나 조회할 수 없음
- LB Console ED25519 Host Key Fingerprint를 확보하지 못했거나 Source Scan 결과와 불일치
- 승인된 Source별 일회성 Key 대신 Password, SSH agent 다중 키 또는 기존 Node 관리키를 사용하려 함

> `10.1.93.254`는 프로젝트 비관리 장비다. ICMP 응답 하나만으로 네트워크 정상·비정상을 판정하지 않고 ARP, Route, TCP 결과를 함께 사용한다.

---

## 4. VMware 및 VM 사전점검

### 4.1 server01 VMware 점검

1. `k8s-api-lb01` VM이 server01에 배치됐는지 확인한다.
2. VM NIC를 `VMnet0`에 연결한다.
3. VMnet0가 Windows NIC **이더넷**에 명시적으로 Bridged됐는지 확인한다.
4. NAT용 VMnet8에는 연결하지 않는다.
5. Network 변경 전 VMware Snapshot 또는 동등한 복구 지점을 만든다.

### 4.2 LB VM 기본정보 수집

```bash
sudo hostnamectl
sudo nmcli device status
sudo nmcli -t -f NAME,DEVICE,TYPE connection show --active
sudo ip -br address
sudo ip route
sudo ss -lntp
sudo getenforce
sudo systemctl is-enabled firewalld
sudo systemctl is-active firewalld
```

이 환경의 자원 매핑은 `VMnet0 → Windows 이더넷(ifIndex 20) → k8s-api-lb01 ens160`이다. 이후 Linux 명령의 Bridged Interface에는 `ens160`을 직접 사용한다. NetworkManager Connection 이름과 firewalld Zone은 인터페이스명이 아니므로 위 명령 결과로 각각 확인한 뒤 `<BRIDGED_CONNECTION>`, `<LB_ZONE>`에 입력한다.

---

## 5. IP 중복 검사와 Network 설정

> IP 변경은 SSH 연결이 끊길 수 있으므로 VMware Console에서 수행한다.

### 5.1 `.109` 중복 검사

```bash
sudo dnf install -y iputils
sudo arping -D -c 3 -I ens160 10.1.93.109
```

- ARP 응답 0건: 다음 단계 진행
- MAC 주소가 포함된 응답 1건 이상: **STOP**. `.109`를 설정하지 않고 충돌 장비를 식별한다.

### 5.2 Hostname 및 Static IP 설정

적용 전 현재 Connection 정보를 Evidence로 저장한다.

```bash
sudo hostnamectl set-hostname k8s-api-lb01
sudo nmcli connection show "<BRIDGED_CONNECTION>"
```

다음 값으로 변경한다.

```bash
sudo nmcli connection modify "<BRIDGED_CONNECTION>" \
  ipv4.method manual \
  ipv4.addresses "10.1.93.109/24" \
  ipv4.gateway "10.1.93.254" \
  ipv4.dns "10.1.93.52 10.1.93.53" \
  ipv4.dns-search "fds.internal" \
  ipv4.ignore-auto-dns yes \
  ipv4.routes "10.250.10.0/24 10.1.93.58" \
  ipv6.method disabled

sudo nmcli connection up "<BRIDGED_CONNECTION>"
```

### 5.3 Network 검증

```bash
hostnamectl --static
ip -br address
ip route
ip route get 10.1.93.102
ip route get 10.250.10.20
arping -c 3 -I ens160 10.1.93.102
```

기대 결과:

- Hostname: `k8s-api-lb01`
- Local IP: `10.1.93.109/24`
- Default Route: `via 10.1.93.254`
- Resolver: `10.1.93.52 → 10.1.93.53`, Search Domain `fds.internal`
- Management Return Route: `10.250.10.0/24 via 10.1.93.58`
- `.102`가 Bridged NIC를 통해 직접 연결됨

P1-DNS-01 v1.1에 따라 Stage A 전에 dns01/dns02의 BIND ACL과 firewalld `fds-dns-clients` IPSet에 `.109`가 포함됐는지 확인한다. `.109` DNS Consumer 추가는 P1-DNS-01 변경 이력으로 관리하며 Routing/SNAT이 바뀌지 않는 한 별도 ICR을 발행하지 않는다.

---

## 6. HAProxy 설치

### 6.1 패키지 설치

```bash
sudo dnf install -y haproxy policycoreutils-python-utils socat
rpm -q haproxy policycoreutils-python-utils socat
haproxy -vv
```

### 6.2 기존 구성 백업

```bash
sudo install -d -m 0750 /var/backups/fds/P1-LB-01
sudo cp -a /etc/haproxy/haproxy.cfg \
  /var/backups/fds/P1-LB-01/haproxy.cfg.before-stage-a
sudo sha256sum /var/backups/fds/P1-LB-01/haproxy.cfg.before-stage-a
```

기존 구성 파일이 없으면 설치 상태를 다시 확인하고 임의로 빈 파일을 만들지 않는다.

---

## 7. HAProxy Stage A 구성

`/etc/haproxy/haproxy.cfg`를 다음 내용으로 작성한다. Kubernetes API TLS를 HAProxy에서 종료하지 않으므로 `bind`와 Backend Server에 `ssl`, 인증서 경로 또는 HTTP 검사 옵션을 추가하지 않는다.

```haproxy
global
    log         /dev/log local0
    log         /dev/log local1 notice
    user        haproxy
    group       haproxy
    daemon
    maxconn     2048
    stats socket /var/lib/haproxy/stats mode 660 level admin

defaults
    log         global
    mode        tcp
    option      tcplog
    timeout connect 5s
    timeout client  1m
    timeout server  1m
    timeout check   5s

frontend kubernetes_api_frontend
    bind 10.1.93.109:6443
    mode tcp
    default_backend kubernetes_api_backend

backend kubernetes_api_backend
    mode tcp
    balance roundrobin
    option tcp-check
    default-server inter 2s fall 3 rise 2
    server k8s-control01 10.1.93.102:6443 check
    server k8s-control02 10.1.93.103:6443 check
    server k8s-control03 10.1.93.104:6443 check
```

### 7.1 구문 검증

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
```

`Configuration file is valid`가 확인되기 전에는 서비스를 시작하거나 Reload하지 않는다.

---

## 8. SELinux 설정과 검증

SELinux는 `Enforcing`을 유지한다.

### 8.1 현재값 기록

```bash
getenforce
getsebool haproxy_connect_any
sudo semanage boolean -l | grep '^haproxy_connect_any'
```

### 8.2 HAProxy Backend 연결 허용

```bash
sudo setsebool -P haproxy_connect_any on
getsebool haproxy_connect_any
```

### 8.3 AVC 확인

```bash
sudo ausearch -m AVC,USER_AVC -ts recent
```

AVC가 발생하면 원인을 분석한다. `setenforce 0` 또는 검토되지 않은 `audit2allow` 정책으로 우회하지 않는다.

---

## 9. firewalld Source Allowlist

### 9.1 적용 Zone 확인

```bash
sudo firewall-cmd --get-active-zones
sudo firewall-cmd --get-zone-of-interface=ens160
sudo firewall-cmd --zone=<LB_ZONE> --list-all
```

Stage A에서는 `--add-port=6443/tcp`로 전체 Source에 Port를 개방하지 않는다. IF-11 Runner, D35 승인 IF-11A Node 6대, 기존 IF-06A monitor01 Source만 `/32` Rich Rule로 관리한다.

```bash
# IF-11 — 승인된 Runner Source
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.250.10.20/32" port port="6443" protocol="tcp" accept'

# IF-11A — D35 승인 Node Sources
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.102/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.103/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.104/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.105/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.107/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.1.93.108/32" port port="6443" protocol="tcp" accept'

# IF-06A — 기존 monitor01 External Probe Source 보존
sudo firewall-cmd --permanent --zone=<LB_ZONE> --add-rich-rule='rule family="ipv4" source address="10.250.10.30/32" port port="6443" protocol="tcp" accept'

sudo firewall-cmd --reload
sudo firewall-cmd --zone=<LB_ZONE> --list-rich-rules
```

허용 근거:

- CP/Worker: 승인된 IF-11A에 따른 kubeadm init/join 및 안정된 Control Plane Endpoint 사용
- `10.250.10.20`: IF-11의 Self-hosted Runner Deploy Source
- `10.250.10.30`: IF-06A의 monitor01 External Probe Source. Stage A는 Rule 보존을 확인하고 실제 Probe/Failure-Recovery는 P1-MON-01에서 검증

그 외 Source의 운영 API 접근이 필요하면 Endpoint·Owner·Expiry·시험 항목을 먼저 확정하고 Interface Change Control을 수행한다.

---

## 10. HAProxy 시작

```bash
sudo systemctl enable --now haproxy
sudo systemctl is-enabled haproxy
sudo systemctl is-active haproxy
sudo systemctl --no-pager --full status haproxy
sudo ss -lntp | grep ':6443'
sudo journalctl -u haproxy -b --no-pager
```

기대 결과:

- `haproxy.service`: enabled / active
- Listener: `10.1.93.109:6443`
- `0.0.0.0:6443` 또는 `:::6443`로 광역 Bind되지 않음
- Backend가 아직 기동되지 않았다면 HAProxy Log/Stats에서 `DOWN` 표시 가능

Backend 상태 확인:

```bash
sudo test -S /var/lib/haproxy/stats
echo 'show stat' | sudo socat stdio UNIX-CONNECT:/var/lib/haproxy/stats
```

---

## 11. Stage A 검증

### 11.1 LB 자체 검증

```bash
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
sudo ss -lntp | grep '10.1.93.109:6443'
sudo firewall-cmd --zone=<LB_ZONE> --list-all
sudo ausearch -m AVC,USER_AVC -ts recent
```

### 11.2 LB에서 Backend 방향 검증

```bash
nc -zv -w 2 10.1.93.102 6443
nc -zv -w 2 10.1.93.103 6443
nc -zv -w 2 10.1.93.104 6443
```

Control Plane API 기동 전 결과 해석:

| 결과 | 해석 | 조치 |
|---|---|---|
| Connection refused | Network는 도달했지만 API Listener 미기동 | Stage A에서 허용, P1-K8S 진행 |
| Timed out | Route 또는 CP Host Firewall이 패킷을 Drop할 가능성 | P1-K8S Preflight에서 `.109 → CP:6443` 해결 후 kubeadm 실행 |
| Succeeded | 이미 6443 Listener가 존재 | 소유 프로세스 확인 후 Stage B 조건으로 재판정 |

`Timed out`을 무시하고 kubeadm을 실행하지 않는다. 단, CP Firewall Port Matrix는 `P1-K8S-01` 소유이므로 Stage A의 HAProxy 구성 실패와 분리해 Handoff Action으로 기록한다.

### 11.3 승인 Source Positive Test

다음 Source에서 수행한다.

```bash
# k8s-control01 또는 승인된 Kubernetes Node
nc -zv -w 2 10.1.93.109 6443

# cicd-runner01 10.250.10.20
nc -zv -w 2 10.1.93.109 6443
```

HAProxy Listener가 TCP Handshake를 수락해야 한다. 모든 Backend가 `DOWN`이면 연결이 즉시 종료될 수 있으며, 이는 Stage A에서 API 기능 실패로 판정하지 않는다.

### 11.4 미승인 Source Negative Test

승인 목록에 없는 ansible01 `10.250.10.10`에서 다음 연결이 차단되는지 확인한다. monitor01 `.30`은 IF-06A 승인 Source이므로 Negative Test에 사용할 수 없다.

```bash
nc -zv -w 2 10.1.93.109 6443
```

Negative Test Host의 IP와 시험 시각을 반드시 기록한다. 이 결과는 LB Host Firewall 통제 증적이며 Kubernetes NetworkPolicy 또는 P1-SEC-01 완료 증적으로 대체하지 않는다.

---

## 12. P1-K8S-01 인계 항목

이하영은 kubeadm 실행 전에 다음을 확인한다.

```yaml
# 실제 Kubernetes 버전이 지원하는 kubeadm API 버전을 사용한다.
kind: ClusterConfiguration
controlPlaneEndpoint: "10.1.93.109:6443"
apiServer:
  certSANs:
    - "10.1.93.109"
```

필수 확인:

- 실제 Kubernetes 버전과 kubeadm Configuration API Version 호환성
- LB 주소와 `controlPlaneEndpoint` 일치
- API Server 인증서 SAN에 `10.1.93.109` 포함
- 각 Control Plane의 Local `advertiseAddress`가 `.102`, `.103`, `.104`로 구분됨
- CP Host Firewall이 Source `.109/32 → 6443/tcp`를 허용함
- `cockpit.socket :9090` 비활성화 또는 별도 승인 통제
- Stage A Evidence 인수 기록

> Kubernetes 버전이 현재 자료에 고정되어 있지 않으므로 kubeadm `apiVersion`은 이 가이드에서 임의로 확정하지 않는다. `kubeadm config validate --config <FILE>`을 실행해 사용 버전과의 호환성을 확인한다.

---

## 13. Evidence 수집과 정책 통제 전송

LB VM에서 임시 Evidence 디렉터리를 만든다.

```bash
sudo install -d -m 0750 -o "$(id -un)" -g "$(id -gn)" \
  /var/log/fds-evidence/P1-LB-01/stage-a
```

Completion Pack v1.3 수집기를 사용한다. 수집기는 실제 HAProxy Stats Socket을 탐지하고 HAProxy 구문검증이 성공하면서 출력이 없더라도 Evidence 06에 구조화된 PASS Record를 기록한다.

```bash
HAPROXY_STATS_SOCKET=/var/lib/haproxy/stats \
./p1-lb-01-stage-a-lb.sh collect
```

별도 Host에서 생성된 Evidence는 일반 SCP, Password 우회 또는 기존 P1-ANS 관리키로 전송하지 않는다. `P1-LB-01_Secure_Evidence_Transfer_Control_v1.0.md`에 따라 Source별 일회성 ED25519 Key, LB Host Key Pinning, Publickey-only, `from`/`restrict`/Forced Command와 SHA-256 검증을 적용한다.

Evidence 목록:

- `15_backend_prebootstrap_test.txt`
- `16_positive_test_nodes.txt`
- `17_positive_test_runner.txt`
- `18_negative_test.txt`
- `18a_secure_evidence_transfer_control.txt`
- `18b_secure_transfer_ansible_client.txt`
- `18c_secure_transfer_runner_client.txt`
- `19_stage_a_handoff_review.md`

v1.2 실행에서 mode `0644`로 생성된 기존 파일은 검토 후 다음 명령으로 `0640`을 적용한다.

```bash
EVIDENCE_PERMISSION_APPROVED=YES \
./p1-lb-01-stage-a-lb.sh normalize-evidence
```

Evidence 19 작성 후 다음 명령은 필수 파일의 non-empty, Symlink 부재, mode `0640`을 검증하고 `99_SHA256SUMS.txt`를 생성한 뒤 즉시 재검증한다.

```bash
./p1-lb-01-stage-a-lb.sh finalize
```

최종적으로 승인된 Repository의 `docs/evidence/P1-LB-01/stage-a/`에 복사하고 Commit ID를 인계 기록에 남긴다. 계정 Token, kubeconfig, Private Key 또는 인증서 Private Key는 Evidence에 저장하지 않는다.

---

## 14. Stage A PASS 기준

| ID | 검증 항목 | 기대 결과 |
|---|---|---|
| LB-A-01 | IP 중복 검사 | `.109` ARP 충돌 없음 |
| LB-A-02 | Network | `.109/24`, Default `.254`, Return Route via `.58` |
| LB-A-03 | HAProxy 구문 | Configuration valid |
| LB-A-04 | Service | enabled / active |
| LB-A-05 | Listener | `10.1.93.109:6443`만 Listen |
| LB-A-06 | Backend 정의 | `.102/.103/.104:6443` 3대 등록 |
| LB-A-07 | TLS 경계 | TCP Pass-through, LB TLS Termination 없음 |
| LB-A-08 | Firewall | IF-11 Runner·IF-11A Node 6대·IF-06A monitor01 `/32`만 허용, Zone-wide 6443 미개방 |
| LB-A-09 | SELinux | Enforcing 유지, 미해결 AVC 없음 |
| LB-A-10 | Positive Test | 승인 Source에서 Listener 도달 |
| LB-A-11 | Negative Test | 미승인 Source 차단 |
| LB-A-12 | Secure Transfer | Evidence 16~18을 Source별 Publickey-only/Strict Host Key/Forced Command로 병합 |
| LB-A-13 | Transfer Evidence | 18a~18c의 Source·Key Fingerprint·SHA-256·파일 mode PASS |
| LB-A-14 | Key Revocation | LB 임시 Public Key Tag 0건, Source Private Key 폐기, Inbox 0건 |
| LB-A-15 | Evidence | Config/Test/Rollback/Handoff와 `99_SHA256SUMS.txt` 전체 검증 PASS |

Stage A PASS 후 기록:

- `P1-LB-01 Status`: **In Progress 유지**
- `Stage A Result`: **PASS / Listener Ready**
- `Next`: 이하영이 P1-K8S-01 Bootstrap 수행
- `Open Item`: Stage B Backend Health·API·Failover

D35로 IF-11A 설계 승인은 완료됐다. 그러나 Node/Runner Positive, ansible01 Negative, Listener·Rule·전송 통제·Key 폐기·Evidence·Hash·Handoff 중 하나라도 미완료면 `Stage A Listener Configured / Handoff Blocked`로 기록하고 `Listener Ready` 또는 P1-K8S Bootstrap 해제를 선언하지 않는다.

---

## 15. Rollback

### 15.1 HAProxy Rollback

```bash
sudo systemctl stop haproxy
sudo cp -a /var/backups/fds/P1-LB-01/haproxy.cfg.before-stage-a /etc/haproxy/haproxy.cfg
sudo haproxy -c -f /etc/haproxy/haproxy.cfg
```

기존 HAProxy 서비스가 원래 활성 상태였을 때만 다시 시작한다. 원래 비활성 상태였다면 임의로 활성화하지 않는다.

### 15.2 Firewall Rollback

Stage A에서 추가한 Rich Rule만 동일 문자열로 `--remove-rich-rule` 처리한 뒤 Reload한다. 기존 Rule 또는 Service를 삭제하지 않는다.

예시:

```bash
sudo firewall-cmd --permanent --zone=<LB_ZONE> --remove-rich-rule='rule family="ipv4" source address="10.250.10.20/32" port port="6443" protocol="tcp" accept'
sudo firewall-cmd --reload
sudo firewall-cmd --zone=<LB_ZONE> --list-all
```

나머지 6개 Node Rule도 Stage A에서 실제로 추가된 경우에만 같은 방식으로 제거한다. IF-06A `.30/32`가 변경 전부터 존재했다면 Rollback에서 제거하지 않는다.

### 15.3 SELinux Rollback

작업 전 `haproxy_connect_any`가 `off`였고 HAProxy를 사용하지 않기로 Rollback한 경우에만 되돌린다.

```bash
sudo setsebool -P haproxy_connect_any off
```

### 15.4 Network Rollback

VMware Console에서 작업 전 NetworkManager 설정 또는 Snapshot으로 복구한다. 현재 접속에 사용 중인 Connection을 SSH에서 삭제하지 않는다. 복구 후 IP, Route, Gateway와 `.109` 미사용 상태를 다시 검증한다.

---

## 16. Troubleshooting

| 증상 | 확인 | 조치 |
|---|---|---|
| HAProxy 시작 실패 | `haproxy -c`, `journalctl -u haproxy` | Bind IP·구문·권한 확인 |
| `cannot bind socket` | `ss -lntp`, `.109` Local IP | Port 충돌 또는 IP 미설정 해결 |
| SELinux AVC | `ausearch -m AVC -ts recent` | Boolean·Port Context 확인, SELinux 비활성화 금지 |
| Runner `.20` 접근 실패 | LB Return Route, mgmt-gw, Rich Rule | Source 보존·IF-11 경로 재확인 |
| Backend 전부 DOWN | LB→CP `nc`, CP Firewall, API Process | API 기동 전이면 Stage A 정상; P1-K8S Handoff 기록 |
| Backend TCP Timeout | Route/ARP/CP Firewall | P1-K8S Preflight에서 해결 후 kubeadm 실행 |
| Backend Refused | CP Host 도달, API 미기동 | kubeadm 전 정상 가능 |
| API TLS 오류 | `controlPlaneEndpoint`, API Server SAN | P1-K8S kubeadm 구성 보정 |
| `Too many authentication failures` | SSH agent와 기본 Identity 다중 제시 | Password로 우회하지 않고 Source별 일회성 Key와 `IdentitiesOnly=yes` 적용 |
| LB Host Key 불일치 | Console Fingerprint와 Scan 결과 비교 | 전송 중지, IP/MITM/Host 재설치 여부 확인 |
| Evidence Receiver DENY | Source, 파일명, 크기, Hash, Forced Command | 원인을 수정하고 새 Key 승인부터 재수행 |

---

## 17. 참조

- `FDS_Project_Implementation_Baseline_v3.1.15`
- `D35_Interface_Register_Correction_and_IF-11A_Approval_Record_v1.0.md`
- `D-SEC-01_Kubernetes_Security_Design_Baseline_v1.0`
- `ICR-D-NET-01-01_Kubernetes_Node_Host_Firewall_및_Monitoring_Route_변경요청_v1.4`
- `P1-DNS-01_Notion_Description_v1.1.md`
- `P1-LB-01_Secure_Evidence_Transfer_Control_v1.0.md`
- `FDS_P1-LB-01_Stage_A_Secure_Transfer_Release_Notes_v1.0.md`
- `FDS_P1-LB-01_Secure_Transfer_Validation_Evidence_v1.0.md`

### v1.5 변경기록

- Password 인증 우회안 폐기 및 Source별 일회성 ED25519 Key 적용
- LB Host Key Pinning, Publickey-only, `IdentityAgent=none`, `IdentitiesOnly=yes`, Strict Host Key Checking 강제
- LB Public Key에 Source 제한·`restrict`·Evidence 전용 Forced Command 적용
- 보호 Inbox, Evidence 18a~18c, Key 폐기와 Inbox 정리 Gate 추가
- Evidence 06 0-byte 결함 수정 및 전체 Evidence mode `0640`/Symlink/Hash 검증 추가
- Completion Pack v1.3으로 상향

### v1.4 변경기록

- 2026-09-03 실제 HAProxy 설정과 일치하도록 Stats Socket을 `/var/lib/haproxy/stats`로 정정
- Completion Pack v1.2의 Socket 자동 탐지·검증 절차 반영
- v1.1 Firewall 적용 결과는 유효하며 수집 단계만 보정

### v1.3 변경기록

- D35 IF-11A 승인 반영 및 실행 승인 가드의 의미 명확화
- IF-06A monitor01 `.30/32 → .109:6443` Source Allowlist 보존
- ansible01 `.10`을 Negative Test Source로 고정하고 monitor01을 Negative Source에서 제외
- Stage A Runtime PASS와 설계 승인을 분리

- `FDS_Project_Implementation_Baseline_v3.1.15.md`
- `FDS_v3.1.15_Canonical_Ticket_Update_Pack_v1.0.md`
- `FDS_DEC-P1-ENTRY-01_Dependency_Correction_v1.0.md`
- Kubernetes, *Creating Highly Available Clusters with kubeadm*: https://kubernetes.io/docs/setup/production-environment/tools/kubeadm/high-availability/
- Kubernetes, *kubeadm Configuration API*: https://kubernetes.io/docs/reference/config-api/kubeadm-config.v1beta4/
- HAProxy, *TCP*: https://www.haproxy.com/documentation/haproxy-configuration-tutorials/protocol-support/tcp/
- HAProxy, *Health checks*: https://www.haproxy.com/documentation/haproxy-configuration-tutorials/reliability/health-checks/
- Red Hat, *Configuring firewalls and packet filters — RHEL 10*: https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/10/html/configuring_firewalls_and_packet_filters/index
