# infra-lb

FDS Kubernetes API Load Balancer configuration, validation and recovery

P1-LB-01의 HAProxy 설정, 검사 소스와 운영 절차를 관리한다. 기준선은 [baseline 이슈9](https://github.com/321Team/fds-project-baseline/issues/9), 현재 LB 전용 증적 PR의 검토는 이 저장소로 이관한다. 원본 PR 이력과 이전 인수 기록은 [fds-project-evidence](https://github.com/321Team/fds-project-evidence)에 보존하며 [PR 이관 현황](docs/PR_MIGRATIONS.md)에서 후속 위치를 확인한다.

## 추가 이관 자료

[LB 자료·증적 통합 목록](docs/EVIDENCE_INDEX.md)에서 Stage A 구축 가이드 v1.5, 완료 팩 v1.3, 과거 export/보완 소스, 노션 작업 원본과 대화 발췌를 확인한다. [운영 기준](docs/OPERATIONS_BASELINE.md)과 [Stage A 인계 근거](docs/STAGE_A_HANDOFF.md)에 당시 기록과 후속 판정을 구분했다. `archive/`는 원본 보존용이며 현재 서버 재적용 패키지가 아니다.

## 현재 범위와 상태

2026-09-17 편입 시점의 확인 결과다. 실시간 상태를 의미하지 않는다.

| 항목 | 확인 상태 | 근거 |
|---|---|---|
| Stage A | 기존 Technical/Evidence PASS 및 조건부 인수 유지 | evidence PR [#1](https://github.com/321Team/fds-project-evidence/pull/1), [#5](https://github.com/321Team/fds-project-evidence/pull/5) |
| Firewall Permanent | 9/9 출력 범위 보완; 재부팅 지속성까지 확대하지 않음 | evidence [PR #6](https://github.com/321Team/fds-project-evidence/pull/6) |
| 현재 DAD | 9/17 00:07 KST 현재 시점 기술 PASS, 최종 해소 리뷰 대기 | evidence [PR #14](https://github.com/321Team/fds-project-evidence/pull/14) |
| Stage B 사전점검 | 9/17 12:17 KST PRECHECK_NOT_READY: CP1 UP, CP2/3 DOWN·TCP 연결 거절 | evidence [PR #15](https://github.com/321Team/fds-project-evidence/pull/15) |
| 인증 API·단일 backend 장애/복구 | 절차 준비, 실제 시험 미수행 | [API 절차](docs/runbooks/AUTHENTICATED_API.md), [장애/복구 초안](docs/runbooks/FAILOVER.md) |

현재 DAD 재검사는 8/31 역사 원본의 복구를 뜻하지 않는다. BACKEND 집계 UP은 서버 세 대 모두 UP이라는 뜻이 아니다. 새 저장소 편입·코드 병합·로컬 테스트 PASS로 Stage B 완료나 인수를 선언하지 않는다.

## 대상과 책임

- LB: `k8s-api-lb01`, `ens160`, `10.1.93.109/24`; frontend `.109:6443`, TCP TLS passthrough.
- Backend: `k8s-control01/02/03`, `10.1.93.102/.103/.104:6443`.
- 기준 HAProxy 버전 3.0.5, stats socket `/var/lib/haproxy/stats`.
- 서비스 설정은 `/etc/haproxy/haproxy.cfg`와 `/etc/haproxy/conf.d`를 함께 읽는다. 이 저장소의 cfg만으로 전체 호스트 구성을 재현했다고 보지 않는다.
- 코드·혼합 PR 독립 검토 경로: 이하영 (`hayeounglee`, PR 작성자인 경우 다른 적격 검토자). 최종 병합 판단: 이권욱 (`GWONUK`). 문서·운영 실행·결과 수용·AC 인수·종결은 책임 티켓의 Lead가 판단한다.

| 저장소 | 관리 범위 |
|---|---|
| infra-lb | LB 설정·검사 소스·절차·출처 잠금 및 이관된 LB 전용 증적 검토 |
| [infra-ansible](https://github.com/321Team/infra-ansible) | 공통 inventory·OS/SSH/DNS·노드→LB Stage A playbook |
| [infra-kubernetes](https://github.com/321Team/infra-kubernetes) | CP runtime/bootstrap/join·CNI·ICR 후속 노드 준비 |
| [fds-project-evidence](https://github.com/321Team/fds-project-evidence) | 이전 원본 PR·승인 이력, 공통 FUP 및 미이관 증적 |
| [fds-project-baseline](https://github.com/321Team/fds-project-baseline/issues/9) | 요구사항·범위·최종 진행 상태 |

공통 inventory와 Ansible playbook을 복제하지 않는다. CP2/3 준비 의존성은 Kubernetes 담당자의 실제 인수·준비 근거로 확인한다. 이번 편입은 ICR 전체 종결이나 새 진단 프레임워크를 추가 선행 조건으로 만들지 않는다.

## 파일과 사용

| 경로 | 용도 |
|---|---|
| `configs/haproxy.cfg` | 고정 Stage A 설정 원본; 배포·reload 자동 실행 없음 |
| `tools/dad/` | 기존 DAD v1.1 소스와 모의 테스트 |
| `tools/stage-b/` | 기존 preflight v1.0 소스·테스트·과거 검사용 fixture |
| `docs/runbooks/` | [DAD](docs/runbooks/DAD.md), [LB preflight](docs/runbooks/LB_PREFLIGHT.md), API, 장애/복구 절차 |
| `templates/EXECUTION_INPUTS.json` | 다음 시험 입력 양식. NOT_RUN/null은 양식 상태이며 현재 운영 결과가 아님 |
| `docs/SOURCE_LOCK.json` | 가져온 소스의 고정 Git SHA·파일 해시·키트 출처 |
| `docs/MIGRATION_MAP.md` | 기존 PR과 새 저장소의 대응 및 남는 검토 범위 |

검토된 **고정 커밋**을 사용하며 main 최신본을 서버에 자동 적용하지 않는다. 저장소 루트에서 `sha256sum --check SHA256SUMS`로 무결성을 확인한다. 실제 실행은 각 runbook의 대상·권한·현재 승인 범위를 확인한 뒤 진행한다. 기존 DAD 승인 링크는 당시 회차 기록이며 미래 실행의 포괄 승인이 아니다.

로컬 검증은 서버 접근 없이 실행한다.

```bash
python3 -m unittest discover -s tools/dad -p 'test_*.py' -v
python3 -m unittest discover -s tools/stage-b -p 'test_*.py' -v
```

## 변경 정책

`main` 직접 push·force push·자동 병합을 금지하고 작업 브랜치와 PR을 사용한다. 코드·실행 설정·혼합 PR은 현재 HEAD의 독립 리뷰 후 이권욱이 병합을 판단한다. 문서·증적만 변경하는 PR은 책임 Lead 검토로 처리한다. 코드 외 실행·인수·종결은 책임 Lead에게 위임하며, fds-project-evidence의 모든 PR은 독립 리뷰를 유지한다. 병합·Runtime·인수 결과는 구분해 기록한다. [정책](docs/GOVERNANCE.md)과 [PR 양식](.github/PULL_REQUEST_TEMPLATE.md)을 사용한다.

초기 확인 시 `main.protected=false`다. 이 PR의 문서·양식은 운영 규칙이며 GitHub 강제 보호 설정이 켜졌다는 뜻이 아니다. 기술 강제 설정 상태와 후속 설정 항목은 정책 문서에 기록한다.
