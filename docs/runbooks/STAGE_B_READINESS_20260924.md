# P1-LB-01 실행 전 잔여 점검 — 2026-09-24 KST

대상은 **기존 LB SSH 접근 확인**과 **현장 nft 문법·권한의 비적용 검사**다. 앞서 PASS한 CP 인증 API를 반복하지 않으며, 장애 주입·계정/키/권한 생성·방화벽 적용·서비스 조작은 하지 않는다. 아직 현장 결과를 받지 않았으므로 두 항목의 상태는 NOT_RUN이다.

PR10은 Runtime 코드가 포함된 혼합 PR이다. 운영 주입은 중앙 정책과 `docs/GOVERNANCE.md`에 따른 exact SHA 독립 리뷰·Lead 병합/실행 판단 이후다. 이 문서의 명령은 읽기 전용 점검 경로만 실행하며 순수 검증기 범위에서 Lead가 실행할 수 있다. 작업창·OOB를 허위로 채우거나 기존 준비 결과를 실행 승인으로 바꾸지 않는다.

## 이번 변경 및 확인한 사실

- 기준 HEAD `eec6383be564d953ece55bf08c90aaeb829161ea` 조회 시 PR10 OPEN/unmerged, GitHub reviews0·issue comments0. GitHub 밖의 별도 리뷰는 미확인.
- infra-ansible main의 `inventory/hosts.yml`에는 여전히 LB가 없다. `ansible.cfg`는 host-key checking=true다.
- 수동 cleanup에서 새 RuntimeRunner가 기존 `COMMANDS.json`을 덮어쓰는 결함을 로컬 실제 파일로 재현하고, 기존 명령 배열에 이어 기록하도록 수정했다. 원래 ledger가 잘못된 형식이면 보존한 채 STOP한다.
- 삭제 실패 후 재조회한 동일 누적 packet counter의 중복 합산을 막았다. nft table JSON 형식이 잘못되면 테이블 부재/회수 완료로 판정하지 않는다.
- nft 규칙 생성기를 순수 함수 모듈 `stageb_rules.py`로 분리했다. 기존 후보와 생성 바이트가 동일함을 확인했다. 읽기 전용 ZIP에는 주입/삭제 실행기 자체를 넣지 않는다.
- 최신 전체 local/native-parser 단위시험67건 PASS(이전57+신규10). Ansible Core2.16.19가 inline inventory를 정확한1대 `.109`로 해석함을 `--list-hosts`로 확인했다. 기존 coordinator mock3건은 조정 play 변경이 없으므로 재사용한다.
- 로컬 nft 바이너리가 없고, 격리 network namespace 생성도 이 실행 환경에서 허용되지 않았다. native nft/kernel 적용 성공을 주장하지 않는다. 현장 `--check` 결과와 실제 장애/만료/복구 결과는 구분한다.

## 공통 준비 — 각 서버의 일반 계정 홈

ZIP과 `.zip.sha256`을 ansible01와 LB의 **각 일반 계정 홈**에 전달한다.

| 서버 | 계정 | 이번 실행 |
|---|---|---|
| ansible01 | server01_ansible | 기존 인증으로 LB SSH identity 1회 확인 |
| k8s-api-lb01 | server01_k8s-api-lb | native nft `--check` 및 전후 stateless 규칙 비교 |

각 서버에서 아래 공통 부분을 실행한다. 폴더가 없으면 생성하며, 기존 파일을 무조건 덮어쓰지 않는다. SHA가 다르면 다음 명령을 실행하지 않는다.

```bash
(
set -euo pipefail
cd "$HOME"
sha256sum -c FDS_P1_LB_01_StageB_Readiness_20260924_v1.0.zip.sha256
mkdir -p "$HOME/p1-lb-stageb-readiness-20260924"
unzip -n "$HOME/FDS_P1_LB_01_StageB_Readiness_20260924_v1.0.zip" \
  -d "$HOME/p1-lb-stageb-readiness-20260924"
cd "$HOME/p1-lb-stageb-readiness-20260924/FDS_P1_LB_01_StageB_Readiness_20260924_v1.0"
sha256sum -c SHA256SUMS
)
```

## 1. ansible01: 기존 LB 접근만 확인

```bash
(
set -euo pipefail
cd "$HOME/p1-lb-stageb-readiness-20260924/FDS_P1_LB_01_StageB_Readiness_20260924_v1.0"
sha256sum -c SHA256SUMS
source "$HOME/.config/ansible/p1-ans-01.env"
python3 collect_stageb_readiness.py --role ansible \
  --private-key "$ANSIBLE_PRIVATE_KEY_FILE" \
  --run
)
```

별도 inventory 파일은 요구하지 않는다. 프로세스 인자로만 `10.1.93.109,` 한 대를 지정하고 기존 계정 `server01_k8s-api-lb`로 host/user/uid/euid를 조회한다. 저장소 inventory를 수정하거나 영구 inventory를 만들지 않는다. 기존 p1-ans-01 설정과 이미 사용 가능한 SSH 인증만 사용한다. `--private-key "$ANSIBLE_PRIVATE_KEY_FILE"`로 기존 승인 키 경로를 명시하고 **BatchMode=yes·StrictHostKeyChecking=yes·IdentitiesOnly=yes·become=false**를 강제한다. 환경 파일의 변수가 export되지 않은 경우에도 키 선택이 모호해지지 않도록 경로를 명시적 인자로 전달한다. 키/비밀번호/known_hosts를 생성·완화하지 않는다. 현재 전용 키가 LB 일반 계정에 등록되지 않았다면 실패할 수 있으며, 이때 권한을 자동 확대하지 않는다.

정상: `LB_SSH_IDENTITY_CONFIRMED`. 실제 host/user 일치와 nonroot/euid 동일이 필요하며 sudo/nft 접근은 이 단계에서 판정하지 않는다. `STOP`이면 Ansible 원문을 회수하여 route/known-host/authentication/계정 중 실패 원인을 구분한다. 출력 메시지에 대한 추측으로 키를 추가하지 않는다.

## 2. LB: 실제 nft 검사만 수행

```bash
(
set -euo pipefail
cd "$HOME/p1-lb-stageb-readiness-20260924/FDS_P1_LB_01_StageB_Readiness_20260924_v1.0"
sha256sum -c SHA256SUMS
sudo -v
python3 collect_stageb_readiness.py --role lb --run
)
```

내부 실행은 `nft -j list tables`, `nft -s -j list ruleset`, `nft --version`, **`nft -c -f -`** 및 전후 동일 조회다. 후보 규칙은 표준입력으로만 검사하며 `-c` 없는 적용 명령은 호출하지 않는다. firewalld stop/reload나 기존 ruleset 복원 명령도 없다. sudo는 기존 권한만 사용하고 명령별 timeout을 둔다.

정상: `NFT_CHECK_ONLY_PASS`. native 검사 rc0, 후보 테이블 부재, 전후 stateless ruleset 동일이 필요하다. 이 결과는 실제60초 만료·HAProxy DOWN·API 무중단·회수/재부팅 지속성을 입증하지 않는다.

`STOP` 또는 전후 차이가 있으면 결과를 보존한다. 이 점검은 적용하지 않으므로 자동 원복/flush를 시도하지 않는다. 기존 `p1lb_` 테이블이 있으면 검사 전에 STOP하며 기존 실행/회수 기록과 연결한다.

## 반환 자료와 다음 연결

각 실행이 출력하는 `ARCHIVE`와 `SIDECAR`, **두 서버 총4개 파일**을 STOP 결과도 포함해 반환한다. `EVIDENCE_DIR`은 시작 시 즉시 출력된다. archive의 모든 포함 파일은 내부 manifest에 대응하며, SSH 자격증명·환경 변수·inventory 원문은 수집하지 않는다. API/StageA 증적을 다시 제출할 필요는 없다.

두 결과가 확인되면 검증된 LB 연결값으로 Runtime용 inventory 입력을 구체화할 수 있다. **현재 runtime 조정기의 `--lb-inventory` 조건을 이 읽기 전용 점검이 자동 충족하거나 우회하지 않는다.** 독립 리뷰 대상은 수정 후 HEAD다. Runtime v1.0은 수동 cleanup 증적 결함 때문에 운영 실행 후보에서 제외하며 수정 v1.1을 사용한다. v1.1도 독립 리뷰·운영 적용 PASS가 아니다.

사용자가 새로 확정해야 할 운영 입력은 `.104:6443` 시험 선택, KST 작업창, 실제 OOB/콘솔 접근이다. 확인 전에는 예시값이나 과거 시각을 승인값으로 사용하지 않는다.

공식 참조: [nft --check](https://www.netfilter.org/projects/nftables/manpage.html), [Ansible host_list](https://docs.ansible.com/projects/ansible-core/2.16/collections/ansible/builtin/host_list_inventory.html).
