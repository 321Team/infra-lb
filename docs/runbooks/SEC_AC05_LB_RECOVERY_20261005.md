# SEC AC05 control03 LB 제외·복귀 절차 — v1.0 초안

상태: DRAFT / Runtime 미실행 / 실행자·연락 가능 시간 미확정.
책임: LB Lead 이권욱, SEC 실행 이하영. 위임·대기 가능 시간을 추정하지 않는다.

## 근거와 범위

- [SEC 시작 Gate 요청](https://github.com/321Team/fds-project-baseline/issues/19#issuecomment-5990738263)
- [10/6 조건부 Runtime GO](https://github.com/321Team/fds-project-baseline/issues/19#issuecomment-5990414380): 11:00 시작, 11:15 복원 우선, 11:30 복구 목표. 복구가 미완료이면 목표 시각 때문에 강제 종료하거나 정상 선언하지 않는다.
- [SEC v4.3 고정 절차](https://github.com/321Team/infra-kubernetes/blob/f023caff4f20b7cac6a15308b735431d7166cf2c/ops/p1-sec01-secretbox-rollback/ac05-rollback-runbook-v4.md) §7·12를 보완한다. 정상 시험 흐름·코드·Secret 인수 기준은 바꾸지 않는다.
- 이 문서는 복구가 필요한 경우의 관리적 제외/복귀 절차다. 별도 LB 장애 주입이나 자동 DOWN 시험이 아니다. 시험 시작 전에 무조건 제외하라는 지시가 아니다.
- 대상은 LB를 경유하는 control03 연결뿐이다. CP 직접 연결·내부 컨트롤러 쓰기 격리를 증명하지 않으며 실제 Secret audit를 대체하지 않는다.

## 확인된 현장 관측

2026-10-05 18:53:17 KST 사용자가 제출한 콘솔 전사 기준. 서버 원본 파일·hash·명령별 rc가 봉인된 archive는 미제출이므로 원본 증적 인수로 표시하지 않는다.

| 항목 | 관측 |
|---|---|
| 호스트 / 계정 | k8s-api-lb01 / server01_k8s-api-lb / uid1000 |
| 서비스 | haproxy active/running, MainPID1241 |
| socket | /var/lib/haproxy/stats, root:root 660, 설정상 level admin |
| 도구·접근 | /usr/bin/socat 설치, sudo 인증 후 show servers state / show stat 조회 성공 |
| live 대상 | kubernetes_api_backend/k8s-control03, 10.1.93.104:6443 |
| peers | k8s-control01 10.1.93.102:6443, k8s-control02 10.1.93.103:6443 |
| 상태 | 3대 UP / L4OK, srv_admin_state=0; scur 각각6/2/1 |
| 미확인 | disable/enable 실제 실행, 직접 readyz, 이하영의 LB 접근·sudo, 내일 실제 실행자·연락 가능 시간 |

L4OK는 TCP 검사이며 readyz 정상의 증거가 아니다. 과거 누적 오류 카운터는 현재 장애로 단정하지 않는다.

## 시작 전 확정

1. #19에 LB 실행자, 10/6 11:00~11:30 연락·대응 가능 시간, 승인된 이 문서 SHA와 명령 범위를 연결한다. 담당자 미확정이면 기존 Gate 미충족이다.
2. 현장 실행은 LB 계정의 기존 sudo 범위에서 한다. 위임이면 위임된 실행자가 자신의 기존 접근 경로로 조회 가능함을 확인한다. 이 절차는 새 권한 부여를 허용하지 않는다.
3. SEC 담당자가 기존 관리자 경로로 3CP 직접 readyz, etcd, 노드 및 LB API 정상 근거를 확보한다. LB에 admin.conf를 복사하지 않는다.
4. 기존 SEC 변경창·비중첩·복구 사본 Gate를 유지한다. LB restart/reload, 설정 수정, 방화벽 변경은 이 절차 범위 밖이다.
5. 실행 직전 live 대상·주소·관리 상태를 다시 확인한다. target 불일치, 기존 MAINT, 서비스 재시작/다중 프로세스 상태 의심이면 원인 확인 후 진행한다. 오늘 캡처로 내일 상태를 대체하지 않는다.

## 명령 실행과 기록 원칙

아래는 승인된 창에서 실행자가 단계별로 사용하는 명령 예시다. 전체 블록을 연속 실행하지 않는다.
각 명령의 시각·stdout·stderr·pipeline rc를 고유 회차 작업 폴더에 보존한다.
socat rc0 또는 빈 응답만으로 관리 명령 성공을 판정하지 않고 반드시 후속 조회로 확인한다.
오류·timeout·결과 불명확이면 변경 명령을 자동 재시도하지 말고 읽기 조회로 실제 상태부터 확인한다.

LB Bash에서 기존 sudo 인증 후 사용:

```bash
test "$(hostname -s)" = k8s-api-lb01 || exit 1
test "$(id -un)" = server01_k8s-api-lb || exit 1
sudo -v || exit 1
set -o pipefail
printf 'show servers state\n' | sudo -n /usr/bin/socat -T 5 stdio UNIX-CONNECT:/var/lib/haproxy/stats
printf 'show stat\n' | sudo -n /usr/bin/socat -T 5 stdio UNIX-CONNECT:/var/lib/haproxy/stats
```

출력의 CSV 헤더를 기준으로 status/check_status/scur/addr를 읽는다. 고정 열 위치를 추정하지 않는다.

## 복구 목적 제외

1. SEC 실행자와 대상 CP 장애·복구 필요성을 확인하고 시각·사유를 기록한다. 정상 peers2대의 직접 readyz와 LB 서비스 상태를 확인한다. peers도 이상이면 단일 CP 복구 가정이 깨진 것이므로 새 시험을 멈추고 공동 장애 대응으로 전환한다.
2. 승인된 실행자는 다음 한 명령으로 control03만 관리적 제외한다.

```bash
printf 'disable server kubernetes_api_backend/k8s-control03\n' |
  sudo -n /usr/bin/socat -T 5 stdio UNIX-CONNECT:/var/lib/haproxy/stats
```

3. show stat / show servers state를 다시 보존한다. target MAINT, peers UP/L4OK 및 peer 직접 readyz·LB API를 확인한다.
4. MAINT는 기존 연결 종료의 증거가 아니다. target scur가0이 아니면 '신규 배정 제외 / 기존 연결 잔존'으로 기록한다. 이 상태를 완전 격리로 보고하지 않는다.
5. 기존 연결까지 끊어야 하는 복구 상황이면 대상 연결 종료의 영향과 실행 승인을 확인한 뒤 아래 명령을 별도로 사용한다. 무조건 자동 실행하지 않는다. watch 등 장기 연결이 끊기고 클라이언트가 재연결할 수 있다.

```bash
printf 'shutdown sessions server kubernetes_api_backend/k8s-control03\n' |
  sudo -n /usr/bin/socat -T 5 stdio UNIX-CONNECT:/var/lib/haproxy/stats
```

6. target MAINT·scur0을 다시 확인한다. 확인 실패면 제외 미확인으로 보고하고 범위를 확대하지 않는다. 직접 CP 경로는 여전히 별개다.
7. SEC v4.3 §7에 따라 control03 원 설정·대상 API를 복구한다. LB 작업 때문에 SEC 복원을 늦추지 않는다.

## 복귀

1. SEC 실행자가 원 설정 해시 일치, secretbox 우선 설정 복원, control03 직접 readyz 정상 및 기존 §7·12 복구 진행 상태를 보고한다. identity 상태나 readyz 불명확이면 재편입하지 않는다.
2. peers2대와 etcd·LB 서비스 정상, 재편입 판단·시각을 기록한다. 이 절차가 만든 MAINT인지 확인한다.
3. 다음 한 명령으로 동일 target만 복귀시킨다.

```bash
printf 'enable server kubernetes_api_backend/k8s-control03\n' |
  sudo -n /usr/bin/socat -T 5 stdio UNIX-CONNECT:/var/lib/haproxy/stats
```

4. health check 회복 후 show stat에서3대 UP/L4OK, target 관리적 제외 해제, 대상 직접 readyz 및 LB 경유 인증 API 정상을 확인한다. 단순 enable 응답을 복구 완료로 보지 않는다.
5. target 재편입 후 이상이면 추가 시험 STOP. control03 재제외 필요성을 실행자·Lead가 판단하고 위 제외 절차로 대응한다. 무조건 반복 toggle하지 않는다. peers 이상 시 공동 장애 대응한다.
6. HAProxy reload/restart가 있었다면 Runtime 상태가 유지됐다고 추정하지 말고 실제 상태부터 확인한다. 재시작으로 제외/복귀를 대신하지 않는다.

## Secret 대응과 종료

실제 Secret PLAIN/UNKNOWN/조회 실패는 SEC 실패·복구 잔여다. LB 재편입 성공이 이를 해소하지 않는다.
원 설정·대상 readyz 복원이 우선이며, 대상별 metadata(namespace/name/UID/RV)와 승인된 창을 확인한 뒤 SEC 담당자가 §12의 새 GET→replace와 class 검증을 수행한다.
업무 Secret 일괄 replace·원문 출력·기존 JSON 재사용은 허용하지 않는다. 실제 대상별 재쓰기 승인은 별도다.

실행 기록에는 문서 SHA, 실행자·승인 링크, 시작/종료 시각, 명령과 rc, 전/후 state/stat, peers·target readyz 및 LB API 근거, 잔여 연결 처리 여부, 복구·미해결 사항을 연결한다.
명령별 원본과 manifest를 보존하고 기존 회차를 덮어쓰지 않는다. 인증서 개인키·kubeconfig·Secret 값은 증적에 넣지 않는다.
사용자 콘솔 전사, 무결성 검증, 독립 리뷰, Runtime 성공, 최종 AC 인수를 구분한다.

## 기술 참고

- https://www.haproxy.com/documentation/haproxy-runtime-api/reference/disable-server/
- https://www.haproxy.com/documentation/haproxy-runtime-api/reference/enable-server/
- https://www.haproxy.com/documentation/haproxy-runtime-api/reference/shutdown-sessions-server/

AI usage: CODEX_ASSISTED. 이 문서 작성 자체는 서버 변경·실행자 확정·Runtime GO 추가 승인·AC 인수가 아니다.
