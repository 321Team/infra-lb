# P1-LB-01 Stage B 선행 작업 키트 v1.0

후속 검토 위치는 [PR 이관 현황](../PR_MIGRATIONS.md)을 따른다. 아래 원본 PR 링크는 당시 기록을 보존한 참조다.

2026-09-17 소스 편입본. 기존 실행은 [증적 PR15](https://github.com/321Team/fds-project-evidence/pull/15)에서 PRECHECK_NOT_READY(CP1 UP, CP2/3 연결 거절)로 수신·검증했다. 다음 실행은 현재 요청의 필요성과 범위를 확인한 뒤 진행한다.

## 승인된 다음 회차의 실행 방법

`k8s-api-lb01`의 **일반 로그인 계정**에서 검토된 commit의 저장소 루트로 이동한 뒤 실행한다. Python 3.8 이상 표준 라이브러리만 사용한다.

```bash
(
set -euo pipefail
sha256sum -c SHA256SUMS
sudo -v
python3 tools/stage-b/collect_preflight.py --run
)
```

첫 줄에서 하나라도 FAILED면 실행하지 않는다. `sudo -v`가 성공한 같은 터미널에서 Python을 실행한다. `sudo python3`로 실행하지 않는다. 도구가 없거나 sudo가 거절되면 그 상태를 제출하며 패키지·권한을 바꾸지 않는다.

결과는 pwd 데이터베이스에 등록된 **일반 계정의 실제 홈폴더**에 생성된다. 현재 알려진 계정은 `server01_k8s-api-lb`, 실제 홈은 `/home/server01_k8s--api-lb`다. 코드가 직접 조회하므로 경로를 입력할 필요가 없다.

- `FDS_P1_LB_01_STAGEB_PREFLIGHT_<UTC>_<random>/`
- 같은 이름의 `.tar.gz`
- 같은 이름의 `.tar.gz.sha256`

마지막에 출력되는 `ARCHIVE=`와 `SIDECAR=`의 **두 파일**을 제출한다. NOT_READY/INCOMPLETE/STOP도 원본 그대로 보존한다. 이 키트의 테스트용 fixtures를 서버 결과로 제출하지 않는다.

## 수집 범위와 결과

| 수집 | 내용 |
|---|---|
| 대상/전후 상태 | hostname, ens160 IPv4/link, HAProxy active, `.109:6443` listener |
| 실제 실행 설정 | MainPID, `/proc/<PID>/cmdline`, 주 설정과 conf.d의 파일 목록·SHA-256 |
| 구문 검사 | `haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/conf.d` |
| HAProxy backend | 기존 socket의 `show stat` 전후 조회; 세 서버의 주소·UP/L4OK·active weight 확인 |
| LB → CP TCP | `.109` 출발지 bind, `.102/.103/.104:6443` 각 1회, 최대3초 |
| 추적성 | 명령 argv/stdin/rc/stdout/stderr, UTC/KST 시각, TCP syscall 오류, 수집기 사본, 내부/외부 해시 |

| 결과 | 의미 / 다음 조치 |
|---|---|
| PRECHECK_READY | 제한된 현재 LB 준비 상태 확인. 인증 API와 장애복구 시험은 여전히 미수행 |
| PRECHECK_NOT_READY | 수집은 됐지만 backend DOWN 또는 TCP 연결 실패 등. 출력으로 원인을 분리 |
| PRECHECK_INCOMPLETE | socket/도구/출력 검증 누락, 설정 검사 비정상 종료·차이 또는 경고 등으로 리뷰 필요. 통과 아님 |
| STOP | 대상·실행 인자 불일치, 수집 오류 또는 전후 상태 변경. 자동 복구·변경 없음 |

종료 코드0은 PRECHECK_READY에만 사용한다. 나머지는2이며 실패 자료도 묶는다. backend UP은 TCP health check 상태다. 인증된 Kubernetes API 성공을 대신하지 않는다. 전후 조회 사이의 지속적 가용성도 이 스냅샷으로 증명하지 않는다.

설정 SHA가 기존 Stage A와 달라지거나 conf.d에 `.cfg`가 있으면 별도 검토가 필요하다고 표시한다. 수정된 설정을 되돌리거나 기존 해시를 강제로 맞추지 않는다. 설정 내용과 kubeconfig를 복사하지 않지만, 제출 전 일반 명령 오류 출력에 의도치 않은 비밀정보가 없는지 확인한다. 발견되면 원본은 로컬 보존하고 공유용 사본을 별도 처리한다.

## 함께 준비한 후속 자료

- [AUTHENTICATED_API.md](AUTHENTICATED_API.md): 허용 source와 로컬 자격증명을 사용하는 인증 API 증적 절차
- [FAILOVER.md](FAILOVER.md): 단일 backend 장애·복구의 시작/중단/복구·판정 절차 초안
- [EXECUTION_INPUTS.json](../../templates/EXECUTION_INPUTS.json): 실제 API/장애 시험 전에 확정해야 할 입력. null은 미확정이며 승인이 아님
- [MIGRATION_MAP.md](../MIGRATION_MAP.md): 기존 완료 증적과 새로 필요한 항목 연결
- [VALIDATION.json](../VALIDATION.json): 편입 시 로컬 검증 결과

서비스·방화벽·sudoers 변경, reload/restart, DAD, kubeadm init/join, 실제 장애 주입은 수집기 기능에 없다. 인증 API/장애 시험은 이 키트를 실행해도 자동 시작되지 않는다.

## 근거

- [P1-LB-01 기준선 이슈9](https://github.com/321Team/fds-project-baseline/issues/9)
- [Stage A 고정 설정](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/received-20260907/07_haproxy.cfg), [서비스 실행 인자](https://github.com/321Team/fds-project-evidence/blob/90093f88167055f81e8789d2a848f44ead0ee9ce/evidence/P1-LB-01/stage-a/received-20260907/08_haproxy_status.txt)
- [HAProxy 3.0 관리 문서: -c / -f / show stat](https://www.haproxy.org/download/3.0/doc/management.txt): -c 종료 코드를 판정에 사용하고, CSV 헤더로 필드를 찾는다.
- [DAD 증적 PR14](https://github.com/321Team/fds-project-evidence/pull/14): 이 키트와 별도 리뷰. Stage B preflight는 PR15에서 별도 검토하며 Stage B 완료는 아직 미충족이다.
