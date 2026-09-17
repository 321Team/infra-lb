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
| 로그인 계정 | server01_k8s-api-lb / 실제 home `/home/server01_k8s--api-lb` | 제출 collector가 pwd로 조회한 결과 |

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

## 현재 후속과 복구 참고

- 사전점검은 [LB_PREFLIGHT](runbooks/LB_PREFLIGHT.md), 인증 API와 failover는 각 runbook 및 미확정 실행 입력을 따른다.
- CP2/3 연결 거절은 준비 미완료 관측이다. LB 파일 이관만으로 CP API 기동 원인이나 firewall 원인을 확정하지 않는다.
- [Stage A 구축 가이드 원본](../archive/stage-a-guide-v1.5/FDS_P1-LB-01_Stage_A_Build_Guide_v1.5.md)은 당시 구성/복구 절차의 참고 자료다. 현재 환경 재적용을 검증한 배포 지침이 아니다.
- 노션의 `haproxy.cfg.before-stage-a`와 `haproxy.cfg.failed-runtime-socket`은 경로·해시 기록만 확보했다. 백업 파일 실물·현재 복구 적합성은 확인하지 않았다. 특히 실패한 socket 설정을 복구 기준으로 선택하지 않는다.
- 공통 Node→LB 검사는 [infra-ansible playbook](https://github.com/321Team/infra-ansible/blob/57e7cc740e7a406387848c52f4aa56b98c516168/playbooks/p1-lb-01-stage-a-nodes.yml)에서 관리한다. CP firewall·ICR 소스는 infra-kubernetes에서 관리한다.
