# P1-LB-01 후속 실행 절차 v1.0 — LB 주입 위치 보완1

기준일: 2026-09-24 KST. 책임 Lead: 이권욱. 현행 소스 기준: `infra-lb` main `41b33b138d5e8a1dce3d4b2d9a3d7ed30afd72ed`. 이 문서와 추가 수집기는 후속 작업 후보이며, 현재 서버 실행 결과가 아니다.

## 현재 판단과 재사용 범위

| 항목 | 확인 근거와 처리 |
|---|---|
| 기존 성공 | [baseline#9](https://github.com/321Team/fds-project-baseline/issues/9)의 2026-09-23 현황: Stage A·9/18 backend 3/3·9/21 LB API 회복. 기존 시험은 재사용한다. 이번 서버 재검증 결과는 아니다. |
| 이관 완료 | [infra-lb PR2](https://github.com/321Team/infra-lb/pull/2)·[PR3](https://github.com/321Team/infra-lb/pull/3) 독립 승인·병합 완료. PR3의 9/17 DOWN은 과거 기록이다. |
| 실제 잔여 | 한 backend 장애 자동탐지 중 인증 API 연속성, 복구 후 3/3 정상, 지속성 확인, LB-A-01 잔여 수용 범위와 최종 Handoff. |
| 현재 미확인 | 지금의 LB stats·인증 API, 시험 대상·정확한 주입/복구 방식·작업창·OOB 경로. 원격 서버 접속이나 장애 주입은 수행하지 않았다. |
| 불필요한 대기 제거 | ICR 전체 종결, Join/Stage A/DAD 반복, LB→GitHub App 신규 발급을 사전점검 조건으로 추가하지 않는다. |

## 1. 이번에 바로 실행할 사전점검

대상은 LB와 control01 두 대다. 기존 일반 로그인 계정 및 승인된 sudo 권한을 사용한다. `sudo python3`로 실행하지 않는다. 파일은 WinSCP 등 기존 파일 전달 경로로 각 일반 계정의 작업 폴더에 전달한다. 새로운 SSH 키·토큰·권한을 만들지 않는다. 전달 ZIP을 새 폴더에 풀고 `cd`로 그 폴더에 들어간다. 기존 폴더에 덮어쓰거나 홈폴더를 초기화하지 않는다.

### LB — `k8s-api-lb01 / 10.1.93.109`

계정 기록: `server01_k8s-api-lb`, passwd home `/home/server01_k8s--api-lb`. 수집기가 실제 home을 조회한다. 기존 `collect_preflight.py`는 바이트 변경 없이 재사용한다.

```bash
(
set -euo pipefail
sha256sum -c SHA256SUMS
sudo -v
python3 tools/stage-b/collect_preflight.py --run
)
```

기대 결과는 `PRECHECK_READY`/rc0, backend 3대 각각 UP/L4OK, `.109` 출발 CP3대 TCP 성공, 설정·PID·서비스 전후 일치다. STOP/NOT_READY/INCOMPLETE(rc2)도 그대로 제출한다. 이미 통과한 Stage A 전체 검사가 아니라 장애 시험 직전의 시점 확인이다. Python 3.8+와 기존 도구가 필요하며 부족한 패키지·권한을 자동 설치/변경하지 않는다.

### API Source — `k8s-control01 / 10.1.93.102`

기존 `/etc/kubernetes/admin.conf`, context `kubernetes-admin@kubernetes`, 기존 예상 identity `kubernetes-admin`을 사용하는 경우 아래 명령을 실행한다. 계정·identity가 기존 승인 범위와 다르면 실행하지 말고 그 차이만 제출한다. 새로운 cluster-admin 권한을 부여하거나 admin.conf를 옮길 필요가 없다. 수집기는 해당 host/source 외 실행을 거절한다.

```bash
(
set -euo pipefail
sha256sum -c SHA256SUMS
sudo -v
python3 tools/stage-b/collect_api_precheck.py --run --expected-user kubernetes-admin
)
```

기대 결과는 `API_PRECHECK_READY`/rc0, 비익명 identity 일치, NodeList GET 성공과 예상 6대 Ready, readyz `ok`, 전후 라우트 일치다. whoami 성공과 GET 실패는 구분한다. TLS 검증·IP SAN 확인을 유지한다. API 점검은 짧은 순차 요청 3종이며 연속 관측·failover·완전 무중단 증거가 아니다. `route_selected_source=.102`는 로컬 라우팅 결과이며 LB에서 패킷 source를 관측했다는 뜻이 아니다.

`kubectl` 미설치/버전 미지원, sudo 거절, proxy/exec auth helper/impersonation 설정, TLS·인증·권한·노드 상태 오류는 STOP이다. 오류를 숨기거나 `--insecure-skip-tls-verify`를 허용으로 바꾸지 않는다. 기존 환경변수·설정은 변경하지 않으며, 수집 명령의 환경만 제한한다. discovery cache가 생성될 경우 결과 디렉터리 안에만 남고 제출 archive에서는 제외한다. 장비 밖으로 kubeconfig·토큰·개인키를 보내지 않는다.

### 제출·중단·복구

각 서버에서 마지막에 출력되는 `ARCHIVE=`와 `SIDECAR=` 파일을 제출한다. **LB 2개 + control01 2개 = 총 4개**다. 실패 결과도 원본 로그·즉시 명령 rc·UTC/KST·수집 코드 사본·내부/외부 SHA와 함께 보존된다. rc2 때문에 subshell이 끝나도 출력된 파일은 남는다. 포장 자체가 실패하면 출력된 결과 디렉터리를 보존하고 실패 문구를 전달한다.

이 단계에는 서버 설정·서비스·방화벽 변경, 재시작, 장애 주입이 없으므로 운영 설정 원복은 없다. 중단 시 Ctrl+C 후 결과를 보존한다. 기존 root 소유 cache 때문에 폴더 정리가 거절되더라도 chmod/chown으로 권한을 완화하지 않는다. 원본 일반 명령 오류에 예상치 못한 민감값이 있는지 제출 전에 확인하고, 발견 시 원본을 로컬 보존한 후 공유 사본만 별도 처리한다.

## 2. 사전점검 뒤 이어갈 장애·복구안 — LB 측 주입 확정, 미실행

**사용자 확정 제약(2026-09-24): 현장 Calico 정책이 적용된 CP에 직접 주입하지 않고 LB에서만 주입한다.** 주입 호스트는 `k8s-api-lb01(10.1.93.109)`이며 LB에서 backend 한 대의 TCP6443으로 나가는 경로만 일시 제한한다. 예비 목적지는 control03 `.104:6443` 한 대로, 실제 대상은 현재 상태 확인 뒤 고정한다. `target_one_cp`는 목적지 backend 식별값이며 CP에서 명령을 실행하라는 뜻이 아니다.

CP의 Calico HEP/GNP·방화벽·kube-apiserver/static Pod·kubelet·etcd·VM 전원은 유지한다. HAProxy의 실제 health check 실패와 DOWN 자동 탐지를 관측한다. 관리적 MAINT/disable은 대체하지 않는다. 시험 결과는 **LB→단일 backend 경로 장애**로 기록하고 CP 프로세스 자체 장애·VM 장애까지 검증했다고 확대하지 않는다.

control01은 기존 허용 경로에서 인증 API를 읽는 **관측자**로만 사용한다. 앞 절의 control01 사전점검은 CP 직접 장애 주입이 아니므로 그대로 재사용한다.

| 입력 | 제안 / 확정 조건 |
|---|---|
| 시험 종류 | 단일 backend 연결 경로 장애의 자동 탐지·인증 API 표본 연속성·복구. MAINT/disable은 관리적 제외이므로 대체하지 않음. |
| 주입 위치·예비 목적지 | 실행 호스트는 LB `.109`로 확정. 예비 목적지 `.104:6443`의 송신 경로만. 실행/복구 담당 이권욱. LB 콘솔/OOB 복구 경로는 현장 확인 필요. |
| 최소 준비 | 현재 3UP/L4OK, 기준 identity/API 성공, 다른 2backend 정상, 현재 LB 방화벽 관리자/규칙과 임시 변경 제거 경로 확인. |
| 관측 제안 | LB stats와 control01의 인증된 GET을 새 연결로 2초 간격 기록. 기준 30초·장애 최대60초·복구 후30초. 이 수치는 실행안이며 승인 AC에 새 SLA를 만든 것이 아님. |
| 성공 판정 제안 | 실제 대상 DOWN 관측, 다른2UP 유지, 실패한 GET 0건, 복구 후3UP/L4OK·인증 API 정상·임시 변경 0. 첫 실패도 원본에 남기며 재시도로 지우지 않음. |
| 중단 | 첫 API 실패·대상 외 backend 저하·관리 경로 불안정·최대60초 또는 작업창 초과 시 즉시 복구. 실제 기준은 실행 입력에 사전 고정. |
| 복구 | 이번 시험이 만든 임시 객체만 삭제하고 3UP/L4OK·API 정상·잔존 변경 없음 확인. 자동 만료/회수 장치와 수동 복구의 실효성을 주입 전에 검증. 광역 flush·방화벽 정지·etcd 조작 금지. |

정확한 주입/복구 명령은 **현재 LB 방화벽 상태 및 관리 경로 확인 전에는 실행 가능한 것으로 배포하지 않는다.** 기존 preflight는 이 방화벽 세부 정보를 수집하지 않는다. 후속 입력은 LB의 firewalld/nft 관리 주체와 현재 송신 규칙, `.104` 경로·출발지, 콘솔/OOB 접근, 임시 규칙의 최대 존속시간 및 원복 결과 확인 방법이다. CP 정책 재설계·정지나 CP 주입 가능성 확인은 요청하지 않는다. 고정되지 않은 대상·작업창·OOB·주입/복구 명령은 [기존 입력 양식](../../templates/EXECUTION_INPUTS.json)에 미확정으로 유지했다. 이번 API 수집기는 그 양식을 소비하거나 자동 장애 시험을 시작하지 않는다. 사전점검 결과를 받으면 현재 출력에 맞는 최소 변경과 역연산을 준비하고 해당 SHA의 리뷰/Lead 실행 판단을 연결한다.

## 3. 지속성과 최종 인수

1. 장애 복구 뒤 설정 hash·서비스 enabled·SELinux·Runtime/Permanent 방화벽 상태를 대조한다. enabled 및 Permanent 조회만으로 재부팅 지속성 PASS를 선언하지 않는다.
2. 실제 LB 재부팅은 별도 작업창과 콘솔 경로를 고정한다. 단일 LB이므로 재부팅 동안 API endpoint 단절 가능성이 있다. 단일 backend 장애 시험과 결합하지 않는다. 기존 사후 재부팅 원본이 있으면 boot ID/시각/해시/검증 범위를 대조해 재사용 가능성을 먼저 판단한다.
3. 재부팅 전후 boot ID 변화, 설정/보안 통제 유지, Listener·3backend·인증 API 회복을 확인한다. 실패 시 콘솔에서 원인을 분리하고 현재 유효한 백업에 따른 복구만 수행한다. 과거 `failed-runtime-socket` 파일을 복구 기준으로 사용하지 않는다.
4. LB-A-01: 현재 DAD 원본의 기술 PASS·PR2 병합은 유지하고, 과거 원본 누락 처리와 잔여 조건 수용 범위에 대한 Lead 판단을 Handoff에 연결한다. DAD를 반복하여 역사 원본을 만들어 내지 않는다.
5. 담당 Lead가 기존 AC·실제 원본·남은 조건에 근거해 최종 Handoff/종결을 판단한다. [현행 리뷰 권한 정책](../GOVERNANCE.md)을 적용하며 Support의 반복 승인을 일률적으로 추가하지 않는다.

## 검증 수준

- STATIC/MOCK: 별도 검증 기록에 실제 수행 결과를 남긴다. fixture/모의 응답은 서버 증적이 아니다.
- CI: 이 소스 기준 `.github/workflows` 없음. **NOT_RUN**.
- RUNTIME: 이 후속 회차 서버 실행 **NOT_RUN**.
- REVIEW/MERGE: PR 실제 상태로 별도 기록. 사전점검 예외를 서버 변경/장애 주입으로 확대하지 않는다.
- PUBLICATION: 실행용 파일 전달과 정본 Release 발행은 별개다. 정본 발행 없음.

명령 근거: [kubectl auth whoami](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_whoami/), [kubectl get](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_get/), [HAProxy 3.0 관리 문서](https://www.haproxy.org/download/3.0/doc/management.txt). 클라이언트 실제 버전의 호환성은 현장 점검 결과로 확인한다.
