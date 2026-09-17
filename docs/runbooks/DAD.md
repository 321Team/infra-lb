# DAD v1.1 실행 참고

2026-09-17 소스 편입본. 기존 회차는 [증적 PR14](https://github.com/321Team/fds-project-evidence/pull/14)에서 기술 확인 후 최종 리뷰 대기다. 아래 승인 URL과 수집기 내부 approval_url은 그 회차의 역사 기록이다. 향후 실행 전에 해당 요청의 승인 범위가 유효한지 확인하며, 이관 자체로 재실행하지 않는다.

실행 대상은 **k8s-api-lb01**입니다. 일반 로그인 사용자 `server01_k8s-api-lb`로 실행합니다. 다른 서버에서 실행하면 중단합니다.

## 승인과 범위

- [이하영 재검사 승인](https://github.com/321Team/fds-project-evidence/issues/4#issuecomment-5699238203)
- 승인 회신 게시: 2026-09-16 23:34:34 KST. 실제 검토 시각을 별도로 추정하지 않습니다.
- 현재 시점 DAD 보완검사와 증적 수집용입니다. 8/31 원본 미확보 이력, 기존 Stage A PASS, Permanent 조건 해소 상태는 보존합니다.
- `PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED`도 최종 인수·Stage B 완료·티켓 종결은 아닙니다. 결과 수신 검증과 인수자 확인이 남습니다.

## v1.0 STOP 수정

9/16 23:54:28 KST 제출 결과는 도구 해시 수집 중 `/usr/bin/sudo` 파일 읽기 권한 오류로 중단됐으며 DAD는 시작되지 않았습니다. v1.1은 도구 바이너리 해시를 읽지 못하면 `TOOLS.json`에 `sha256: null`, `UNAVAILABLE_PERMISSION_DENIED`와 오류·파일 권한 메타데이터를 기록합니다. 실제 명령 실행이 거부되면 그대로 STOP합니다.

이번 수정은 sudo 파일 권한·SELinux·sudoers를 변경하지 않습니다. 필수 증적 파일과 압축 체크섬 검증, L2 확인, DAD 판정, 검사 전후 상태 확인은 유지합니다. 기존 STOP 원본은 보존하며 v1.1 결과와 구분합니다.

## 준비

1. 검토된 infra-lb commit을 LB 일반 로그인 계정의 작업 폴더에 준비합니다.
2. commit SHA를 확인하고 저장소 루트의 SHA256SUMS를 검증합니다.
3. 필요한 도구는 Python 3.8 이상, ip, ss, systemctl, iputils arping, sudo, env, GNU timeout입니다. 스크립트는 도구를 설치하거나 설정을 변경하지 않습니다.
4. 알려진 환경 `ens160 / 10.1.93.109/24 / L2 확인 대상 10.1.93.254`가 실제 상태와 다르면 중단합니다. 임의로 스크립트를 수정해 통과시키지 말고 STOP 증적을 제출합니다.

## 실행

현재 요청의 실행 범위를 확인한 뒤 저장소 루트에서 실행합니다.

```bash
(
set -euo pipefail
sha256sum --check SHA256SUMS
sudo -v
python3 tools/dad/collect_dad.py --run
)
```

`sudo python3 ...`로 실행하지 않습니다. sudo 암호는 `sudo -v`에서 직접 입력하며 수집 파일에 포함되지 않습니다. sudo 인증 자체가 실패하면 실제 검사는 시작되지 않습니다.

## 수행 내용

1. 호스트명·NIC·IPv4·MAC·링크, HAProxy active 및 .109:6443 Listener 확인
2. 동일 NIC로 .254가 직접 연결되는지 확인하고 단회 ARP 응답 확인
3. `arping -D -c 3 -I ens160 10.1.93.109` 단회 수행
4. 검사 전후 NIC/IP/MAC·서비스·Listener 비교
5. 원본 출력·종료 코드·UTC/KST 시각·도구 버전·해시·결과 JSON 저장 및 압축

sudo 명령은 비대화형이며, arping에는 10초 실행 제한과 2초 종료 유예를 둡니다. 반복 실행이나 자동 재시도는 없습니다. 실제 소요시간은 호스트 상태에 따라 달라집니다.

IP 제거/변경, NIC 재시작, 서비스 재시작, 방화벽·SELinux 변경은 없습니다. 전체 네트워크 스캔도 하지 않습니다.

## 결과와 제출

| STATUS | 의미 | 후속 |
|---|---|---|
| PASS_CURRENT_SNAPSHOT_REVIEW_REQUIRED | 통신 확인 성공, DAD 송신 3·수신 0·정상 RC=0, 전후 상태 일치 | 표시된 ARCHIVE와 SIDECAR 제출 |
| FAIL_CONFLICT_SUSPECTED_REVIEW_REQUIRED | DAD 응답 수신 | 재실행·임의 네트워크 변경 없이 두 파일 제출. 응답 MAC 검토 필요 |
| STOP | 대상·통신·도구·권한·출력·시간 제한·전후 상태 확인 실패 | 생성된 두 파일 제출. 원인 확인 전 반복하지 않음 |

증적은 로그인 계정의 **홈폴더**에 생성됩니다.

```text
~/FDS_P1_LB_01_DAD_<UTC>_<고유값>/
~/FDS_P1_LB_01_DAD_<UTC>_<고유값>.tar.gz
~/FDS_P1_LB_01_DAD_<UTC>_<고유값>.tar.gz.sha256
```

화면의 `ARCHIVE=`와 `SIDECAR=` 파일 2개를 업로드하면 됩니다. 실패 시에도 가능한 범위에서 압축합니다. 압축 실패나 증적 디렉터리 생성 전 실패라면 화면 출력과 보존된 디렉터리를 먼저 확인합니다.

이번 해시는 현재 증적의 전송 무결성 식별값입니다. 과거 실행·원본 복구나 미래 충돌 부재를 증명하지 않습니다. 꺼진 장비·다른 링크·응답하지 않는 장비는 이 관측으로 배제할 수 없습니다.

## 개발 검증

저장소 루트에서 `python3 -m unittest discover -s tools/dad -p 'test_*.py' -v`로 기존 모의 테스트를 실행한다. 편입 검증은 [VALIDATION.json](../VALIDATION.json)에 기록한다. 로컬 테스트는 서버 실행·독립 리뷰·인수 승인을 대신하지 않는다.
