# P1-LB-01 Stage B least-privilege helper — 2026-09-27 KST

책임 티켓: fds-project-baseline#9

## 배경

2026-09-27 첫 Stage B Runtime은 `initial_cmdline`에서 `sudo -n`이 비밀번호를 요구해 fail-closed STOP했다.

- `fault_attempted=false`
- `cleanup=NO_MUTATION_ATTEMPTED`
- `drop_packets=0`
- CP API samples 14/14 성공
- 직접 원인: `sudo: a password is required`
- 서비스 장애 및 nft mutation 없음

광범위 `NOPASSWD:ALL` 대신 root-owned helper 한 개만 허용한다.

## 보안 경계

- helper: `/usr/local/sbin/p1-lb-stageb-privileged`, `root:root`, `0755`
- sudoers: `/etc/sudoers.d/p1-lb-stageb`, `root:root`, `0440`
- sudoers는 helper 한 개만 `NOPASSWD` 허용
- SELinux/firewalld/sshd 설정은 변경하지 않는다.

허용 범위:
- HAProxy MainPID의 `/proc/<pid>/cmdline` 읽기
- `/etc/haproxy/haproxy.cfg` 및 `/etc/haproxy/conf.d/*.cfg` 조회/hash/config-check
- `/var/lib/haproxy/stats`에 정확히 `show stat`
- nft table 목록과 `inet firewalld` 읽기
- exact Stage B rule의 `nft -c -f -` / `nft -f -`
- 정확한 `p1lb_<32hex>` table 조회/삭제

거부 범위:
- `flush ruleset`, firewalld table 변경/삭제
- 임의 파일 읽기/hash
- 다른 IP/port/interface fault rule
- shell 또는 임의 subprocess
- 다른 sudo 호출자
- reviewed helper SHA와 다른 설치 파일

## 코드 Gate

`source_files()`에 `stageb_privileged_helper.py`를 포함한다. 모든 privileged 호출은 helper를 통하고 helper는 매 호출마다 reviewed SHA를 재검증한다.

Runtime staging/observer보다 먼저 다음 read-only preflight가 수행된다:

~~~
sudo -n -- /usr/local/sbin/p1-lb-stageb-privileged \
  --preflight <reviewed-helper-sha256> <run_id>
~~~

preflight는 HAProxy cmdline/config hash/stats, nft table/firewalld read, exact rule의 `nft -c`까지만 수행하며 mutation은 하지 않는다.

## 독립 리뷰 후 현장 설치

아래는 PR exact HEAD 독립 승인 후에만 수행한다.

~~~bash
set -euo pipefail
HELPER_SRC=/absolute/path/to/reviewed/stageb_privileged_helper.py
SUDOERS_SRC=/absolute/path/to/reviewed/stageb_privilege.sudoers
test -f "$HELPER_SRC"
test -f "$SUDOERS_SRC"
sudo install -o root -g root -m 0755 "$HELPER_SRC" /usr/local/sbin/p1-lb-stageb-privileged
sudo install -o root -g root -m 0440 "$SUDOERS_SRC" /etc/sudoers.d/p1-lb-stageb
sudo visudo -cf /etc/sudoers.d/p1-lb-stageb
sudo restorecon -v /usr/local/sbin/p1-lb-stageb-privileged /etc/sudoers.d/p1-lb-stageb
sudo stat -c '%U:%G %a %n' /usr/local/sbin/p1-lb-stageb-privileged /etc/sudoers.d/p1-lb-stageb
~~~

성공 기준: helper `root:root 755`, sudoers `root:root 440`, `visudo` PASS, SELinux Enforcing 유지.

## 롤백

active Stage B process가 없음을 확인한 뒤:

~~~bash
sudo rm -f /etc/sudoers.d/p1-lb-stageb
sudo visudo -c
sudo rm -f /usr/local/sbin/p1-lb-stageb-privileged
~~~

## 재시험 조건

1. helper/sudoers exact reviewed source 설치
2. `visudo` PASS, SELinux Enforcing 유지
3. read-only privilege preflight PASS
4. 기존 LB/Ansible Readiness PASS 유지
5. fresh OOB 확인
6. fresh KST 작업창
7. Lead의 해당 회차 Runtime 승인
8. target `10.1.93.104:6443` 즉시 사전 확인

이전 19:30~20:00 작업창이나 첫 Runtime run_id는 재사용하지 않는다.
