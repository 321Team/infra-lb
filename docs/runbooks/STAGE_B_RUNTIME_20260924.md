> 2026-09-24 추가: [읽기 전용 잔여 점검](STAGE_B_READINESS_20260924.md)으로 별도 inventory 파일 없이 LB SSH를 확인하고, LB native nft --check 결과를 수집할 수 있다. Runtime v1.0의 수동 cleanup 명령 이력 보존 결함을 수정했으므로 운영 후보는 v1.1이며 검토 SHA도 수정 후 HEAD로 바뀐다.

# P1-LB-01 Stage B Runtime 검토 후보 — 2026-09-24 KST

책임 티켓: [baseline#9](https://github.com/321Team/fds-project-baseline/issues/9). Lead 이권욱. 코드: [infra-lb PR10](https://github.com/321Team/infra-lb/pull/10).

**구현·로컬 검증용 후보이다. 운영 장애 주입은 NOT_RUN, 독립 REVIEW/MERGE는 미완료이다.** 이 코드가 포함된 PR10은 Runtime 코드와 Pre-check의 혼합 PR이다. 과거 Pre-check 예외 표기는 해당 시점 이력이며 현재 전체 diff에 적용하지 않는다. `docs/GOVERNANCE.md`와 중앙 `REVIEW_AUTHORITY_POLICY.md` §3·3.2에 따라 정확한 SHA의 독립 리뷰와 Lead의 병합/실행 판단을 연결한다. 입력 JSON의 리뷰 참조·SHA 기입은 운영자가 남기는 기록이며 GitHub 승인을 자동 검증하거나 대신하지 않는다.

## 확정 범위와 추가 연결 입력

- 기존 현장 PASS: LB05:10의 backend3UP/L4OK, API05:44의 control01/svc_ansible → LB TLS 인증 API. 해당 증거를 반복 제출하도록 요구하지 않는다.
- 장애 위치는 LB `10.1.93.109`만. 실행 후보는 `.104:6443` 한 목적지로 고정했다. 다른 목적지를 선택하려면 코드/시험/리뷰를 다시 맞춘다.
- CP는 기존 control01 `10.1.93.102`, `svc_ansible`에서 `/etc/kubernetes/admin.conf`, context `kubernetes-admin@kubernetes`, 사용자 `kubernetes-admin`을 사용한다. endpoint는 `https://10.1.93.109:6443`, IP SAN/TLS 검증을 유지한다.
- CP 정책·서비스·VM 변경, HAProxy MAINT/disable, firewalld reload/stop, 영구 설정 변경은 없다.
- **ansible01 → LB SSH는 아직 확인되지 않았다.** 기존 `p1-ans-01/inventory/hosts.yml`에는 LB가 없다. 이미 승인된 LB SSH 접근이 있는 별도 inventory 파일을 `--lb-inventory`로 받는다. alias `k8s-api-lb01`, `ansible_host=10.1.93.109`, 승인된 일반 계정이 필요하다. 임시 inventory를 자동 생성하거나 키·권한·known_hosts를 변경하지 않는다. LB 접근이 없으면 이 조정기는 사용할 수 없고 주입 전에 STOP한다.
- LB 접속 계정 후보는 이전 로그인에서 확인한 `server01_k8s-api-lb`이다. ansible01에서 이 계정으로 기존 SSH 인증과 `sudo -n` 명령 실행이 가능한지는 미확인이다. 계정 변경은 승인된 기존 범위에서 확인해야 한다.

## 동작과 중단·회수

1. Ansible이 **두 서버의 실제 host/account/home을 먼저 확인**한다. 일반 계정의 새 0700 작업 폴더에 소스와 비밀값 없는 입력만 전달하고 SHA256을 확인한다. 기존 inventory/config 내용이나 SSH 비밀값은 증적으로 수집하지 않는다.
2. control01에서 수정·현장 검증된 API precheck 로직을 사용해 실행 시점 조건을 확인한 뒤, 유한 시간 관측기를 실행한다. NodeList GET(정확한6개 Ready)와 readyz를 목표2초 간격으로 호출한다. 실제 간격·요청 시간이 7초를 넘거나 첫 요청이 실패하면 STOP하며 재시도로 덮지 않는다. 표본별 원문·rc·UTC/KST·monotonic 시간을 보존한다. 관측기는 최대240초 후 STOP한다.
3. LB 감독기는 현재 주소/리스너/HAProxy PID·argv·설정 hash·3UP/L4OK·송신 경로·firewalld 상태를 확인한다. 같은 계정 중복 프로세스와 기존 `p1lb_` 테이블이 있으면 STOP한다. 실제 현장의 `nft -c -f -` 검사에 성공해야 한다. 이 검사는 아직 여기서 실행되지 않았다.
4. 제어기는 새 CP 성공 sequence만 LB에 전달한다. 중복 sequence는 lease를 연장하지 않는다. LB는 자신의 monotonic 시계로 수신 후10초만 lease를 유효하게 본다. CP/LB 시계의 동기화를 lease 판정에 사용하지 않는다. 제어기 CP 상태 조회·LB 전달·LB 상태 조회에는 각각5초 Ansible task 제한을 둔다.
5. fresh lease와 backend3UP가30초 유지된 뒤 임시 테이블을 만든다. nft 배치는 `create table inet p1lb_<run_id>`, 만료60초의 `.104` set 원소, output hook priority0/policy accept, `ens160 / saddr .109 / daddr @target / TCP dport6443 / counter drop`만 포함한다. firewalld의 소유 테이블과 priority10 출력 체인을 수정하지 않는다. 패킷·heartbeat가 set 만료를 갱신하지 않는다.
6. 정상 경로는 약55초에 임시 테이블을 삭제한다. 그 전에 HAProxy target `DOWN`+`L4TOUT/L4CON`을 실제 관측하고 나머지2대 UP/L4OK를 요구한다. 이후3UP/L4OK와 API 성공 관측이30초 유지되어야 한다. drop counter>0, 자체 테이블 부재, HAProxy 설정/PID 및 firewalld stateless 규칙의 일치도 확인한다.
7. API 실패를 제어기가 수신하면 LB abort를 요청한다. 제어기/SSH 단절 시 lease 만료를 LB가 확인하여 회수한다. **즉시·0초 복구를 보장하지 않는다.** SSH 전달·진행 중인 제한 명령·poll에 따른 지연이 있다. LB privileged 명령은 inner2초/outer4초 제한이며 여러 회수 조회가 이어질 수 있다. 감독기까지 강제 종료되면 커널 set의60초 만료가 별도 차단 해제 장치다. set 만료는 테이블 삭제나3UP 확인과 다르다.
8. 실패해도 자신이 시도한 run marker의 테이블만 회수하고 최대40초의 backend 복구 확인을 남긴다. 삭제 실패/marker 불일치/복구 미확인은 STOP으로 남긴다. `.104`의 기존 연결도 차단 대상이므로 전환 중 API 실패0건을 사전에 보장하지 않는다.

API 호출은 전수 트래픽이 아니라 제한된 표본이다. 목표2초, baseline30초, fault최대60초, recovery30초, gap한도7초는 이 후보의 **시험 파라미터**이며 새 SLA/AC 승인으로 해석하지 않는다.

## 전달 묶음과 명령

전달명: `FDS_P1_LB_01_StageB_Runtime_Review_20260924_v1.1.zip` 및 같은 이름의 `.zip.sha256`. ZIP에는 정확한 저장소 source, 검증용 시험, 실행 설명, `SOURCE_REVISION`, 내부 `SHA256SUMS`가 있다. 이 문서에 사후 commit SHA를 자체 삽입하지 않으며, ZIP의 `SOURCE_REVISION`과 PR 본문에 결과 SHA를 고정한다.

ansible01의 일반 계정에서 ZIP/sidecar를 홈에 둔 경우:

```bash
(
set -euo pipefail
cd "$HOME"
sha256sum -c FDS_P1_LB_01_StageB_Runtime_Review_20260924_v1.1.zip.sha256
unzip FDS_P1_LB_01_StageB_Runtime_Review_20260924_v1.1.zip
cd FDS_P1_LB_01_StageB_Runtime_Review_20260924_v1.1
sha256sum -c SHA256SUMS
source "$HOME/.config/ansible/p1-ans-01.env"
# 아래 경로는 기존 승인된 LB inventory의 실제 경로로 지정한다.
python3 run_stageb.py --check-access \
  --lb-inventory /absolute/path/to/existing-lb-inventory.yml \
  --lb-user server01_k8s-api-lb
)
```

`--check-access`는 `access` 태그의 host/account 조회만 실행한다. 원격 Runtime source 전달·async 시작·nft 호출이 없다. 경로를 모르면 임의로 새 inventory/SSH 키를 만들지 말고 기존 접근 경로를 확인한다. `ACCESS_CONFIRMED`도 nft/sudo/장애전환 PASS를 뜻하지 않는다.

운영 실행은 exact source 리뷰·병합과 Lead 실행 판단 후에만 한다. `ansible/inputs.example.json`을 별도 `runtime-inputs.json`으로 복사하여 검토 SHA/참조, `runtime_authorized=true`, `.104:6443`, 기존 LB 계정, KST 작업창과 실제 접근 가능한 OOB/콘솔 참조를 완성한다. source SHA는 `SOURCE_REVISION`과 같아야 한다. 시작 시점에300초 이상이 남아야 하므로 여유 있는 작업창을 사용한다. 내용의 승인 여부는 사람이 확인하며 빈값·잘못된 시간·SHA 불일치는 프로그램도 거부한다.

```bash
python3 run_stageb.py --run \
  --lb-inventory /absolute/path/to/existing-lb-inventory.yml \
  --inputs runtime-inputs.json
```

출력의 `ARCHIVE`와 `SIDECAR`를 STOP인 경우에도 함께 회수한다. 바깥 archive에는 Ansible 원문·조정 시각/sequence·소스 사본·CP/LB 중첩 archive와 hash가 포함된다. 각 원격 결과는 `P1_LB_STAGEB_<run_id>`에 남으며 `cp_LOCATION.json`, `lb_LOCATION.json`이 정확한 경로를 기록한다. async cache와 원격 작업 폴더는 이 후보가 삭제하지 않는다. daemon/cron/systemd를 설치하지 않는다.

## OOB 복구

LB에서 해당 `lb_LOCATION.json`의 **source 경로**와 `INPUTS.json`의 run_id를 확인한다. 아래 SOURCE_DIR은 실제 기록의 경로다.

```bash
python3 SOURCE_DIR/stageb_agent.py abort --role lb --inputs SOURCE_DIR/inputs.json
```

감독기가 종료됐는데 테이블이 남았으면 같은 계정에서 `sudo -v` 후:

```bash
python3 SOURCE_DIR/stageb_agent.py cleanup --role lb --inputs SOURCE_DIR/inputs.json
```

`cleanup`은 live process lock이 있으면 경합 삭제를 거부한다. 그 경우 감독기의 회수/최대60초 set 만료를 확인한다. 이 명령도 실패하면 OOB 콘솔에서 `nft -j list table inet p1lb_<정확한_run_id>`의 이름과 `P1-LB-01:<run_id>` comment를 확인한 후 **해당 테이블만** `sudo nft delete table inet p1lb_<정확한_run_id>`로 삭제한다. `flush ruleset`, firewalld stop/reload를 사용하지 않는다. 이후 stats3UP/L4OK와 인증 API 회복을 별도 확인·보존한다. 임시 테이블 부재만으로 복구 전체 PASS를 만들지 않는다.

## 검증 범위와 판정

- Python3.8 문법 및 local/mock 단위시험. 기존 kubectl native parser 회귀시험은 실제 로컬 v1.34.1을 사용한다. 현장 precheck v1.36.4 PASS는 이전 제출 원본의 범위이다.
- 실제 Ansible Core2.16.19 엔진 + **로컬 mock agent**로 조정 성공, API 실패 후 LB abort 전달·양쪽 증거 회수, 변경 없는 실제 host/account gate의 잘못된 호스트 STOP을 검증한다. SSH·sudo·nft 또는 현장 장애를 실행한 시험이 아니다.
- CI=NOT_RUN, 실제 nft native/kernel 적용=NOT_RUN, Runtime=NOT_RUN, REVIEW/MERGE 미완료. 로컬에는 nft 바이너리가 없으며 규칙 native 검사를 성공했다고 주장하지 않는다.
- 성공 시 자동 결과는 `PASS_CANDIDATE`까지만 가능하다. 제어기 rc0만으로 PASS하지 않으며 nested archive/manifest/source와 전체 API 표본을 검증한다. 최종 원본의 시각/sequence·구간 coverage와 시험 결과를 Lead가 판정한다.
- 실제 단일 장애 시험·재부팅 지속성·LB-A-01 수용·최종 Handoff는 별도 잔여다. Stage A/Join/DAD 반복, ICR/MON 전체 종결을 새 조건으로 추가하지 않는다.

설계의 공식 참조:

- [nftables manpage — create/check/table/timeout](https://www.netfilter.org/projects/nftables/manpage.html)
- [nftables element timeouts](https://wiki.nftables.org/wiki-nftables/index.php/Element_timeouts)
- [Ansible Core2.16 async/poll](https://docs.ansible.com/projects/ansible-core/2.16/playbook_guide/playbooks_async.html)
