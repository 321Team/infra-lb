# P1-LB-01 Stage B 사전점검 수신 검토 — 2026-09-17

**검토 결과: 수집·무결성 정상 / LB 설정·서비스·리스너 정상 / CP1 UP / CP2·CP3 DOWN / PRECHECK_NOT_READY.**

수집 시각: **2026-09-17 12:17:43 KST (03:17:43 UTC)**. `k8s-api-lb01` 일반 계정의 제출 원본을 검토했다. 검토자가 서버에 접속해 다시 실행한 결과가 아니다. 기준선 이슈: [P1-LB-01 #9](https://github.com/321Team/fds-project-baseline/issues/9).

## 실제 확인 결과

| 대상 | HAProxy 전/후 | LB .109 출발 TCP | 판정 범위 |
|---|---|---|---|
| CP1 .102:6443 | UP / L4OK | 연결 성공 | 현재 L4 접근 확인; API 인증·클러스터 인수 아님 |
| CP2 .103:6443 | DOWN / L4CON | Connection refused / errno111 | 3backend 준비 요건 미충족 |
| CP3 .104:6443 | DOWN / L4CON | Connection refused / errno111 | 3backend 준비 요건 미충족 |

HAProxy 전체 `BACKEND` 행은 UP이지만 실제 서버는 1/3 UP이다. 이를 3대 정상으로 읽지 않는다. CP2/CP3의 API 미기동, 서비스 이상, 방화벽 동작 중 어느 것이 원인인지는 이 자료로 확정하지 않는다.

## 무결성·실행 대조

- 원본 archive `FDS_P1_LB_01_STAGEB_PREFLIGHT_20260917T031743Z_ui0l6jwq.tar.gz`, 15,085 bytes.
- 외부 SHA-256: `a1a7bb272a770ba44f5ae6542f0f6aee2a948cbbcf773a6f31242b83abf23281`; sidecar 일치.
- 내부 manifest **46/46 일치**, manifest 포함 raw **47개**, 미등재 파일·중복·경로 이탈·링크 없음.
- 배포 v1.0 수집기와 제출 `collector-used.py` 바이트 일치. 수집기 SHA `b4e211dac2cee0eb4c926f90ee818dc83c727401b95173cb18a9174283707476`.
- 외부 조회 명령 **20/20 rc0**, stderr 전부 비어 있음. argv/stdin/UTC·KST/순서 대조 완료. TCP probe는 별도 Python socket 결과로 **1성공·2거절**이며 명령20건의 rc0으로 이를 성공 처리하지 않는다.
- IP/link·서비스·listener·MainPID/cmdline·설정 파일 목록/해시의 stdout **전후8쌍 바이트 일치**. MainPID1269, `ens160 10.1.93.109/24`, MAC `00:0c:29:f7:65:94`, 서비스 active, `.109:6443` LISTEN.
- 주 설정 SHA `afd19086ab8529d621185c231fa3c588eaeeb2025a08445e90f28cf27b00504f`: 기존 Stage A 설정과 동일. conf.d 비숨김 `.cfg`0개. 두 경로를 포함한 `haproxy -c` rc0.
- 보조 도구 해시10/11. sudo는 mode0o4111로 읽기 불가여서 해시 미수집이며 실행된 sudo 경유 조회는 정상이다. 수신 증적 해시는 모두 검증했다.

`raw/`는 제출 바이트 그대로다. `VERIFICATION.json`, `SOURCE_PACKAGE.json`, 이 문서는 수신 후 새 검토 기록이다. 별도 원본 archive는 첨부 보관본을 유지한다. 이 디렉터리의 `SHA256SUMS`는 새 등록 파일 manifest이며 서버의 `raw/SHA256SUMS`와 구분한다.

## 긍정적으로 갱신 가능한 범위

기존 Stage A의 bootstrap 전 **3DOWN** 기록과 비교하면, 이번에는 **CP1의 LB health UP과 .109→.102 TCP 성공**을 현재 원본으로 확인했다. LB 주 설정을 바꾸지 않은 상태에서 backend 한 대의 접근이 확인됐다. 과거 3DOWN 증적을 수정하거나 CP1 Ready·실제 인수·인증 API 성공으로 확대하지 않는다.

## 직접 후속 작업

1. [P1-K8S-01 #10](https://github.com/321Team/fds-project-baseline/issues/10)의 기존 CP1 인수 및 CP2/CP3 후속 준비 작업에 이번 LB 관측을 연결한다. CP2/CP3의 실제 6443 listener/API 기동과 해당 LB source 접근 근거를 기존 작업 증적에서 확인한다. 증거 없이 LB 설정 수정·방화벽 해제·Join 재실행을 지시하지 않는다.
2. 해당 준비/변경이 완료된 뒤 같은 LB preflight로 **3/3 UP과 TCP 성공**을 확인한다. 상태 변경 없이 같은 수집을 반복할 필요는 없다.
3. 허용 Runner .20 또는 승인 Node에서 기존 준비 절차로 TLS 검증·예정 identity·인증 API 요청을 확인한다. CP1만 있는 단계의 진단 성공은 Stage B 완료가 아니다.
4. 3backend/API 준비, 작업창·대상 한 대·주입/복구 방법·중단 기준을 확정한 후 단일 backend 장애·복구 중 API 지속을 시험한다. 현재 이 시험은 미수행이다.

## 별도 승인 상태

이번 수신 증적 편입과 최종 인수는 검토 대기다. DAD [PR14](https://github.com/321Team/fds-project-evidence/pull/14)는 별도이며 조회 당시 HEAD `f74bda7eac39658c297a4dd5d1c590bd0717bcce`, open·미병합, formal review0건이다. Stage A Technical/Evidence PASS·조건부 인수, Permanent 해소 범위는 유지한다. P1-LB-01 **In Progress**, Stage B **미완료**다.
