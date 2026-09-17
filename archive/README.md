# Stage A 기존 자료 보존본

이 디렉터리는 2026-09-03 구축·전송 자료와 9/7 보완 소스를 원본 바이트로 보존한다. 현재 서버에 재적용할 실행 패키지가 아니다. 현재 운영 기준은 [OPERATIONS_BASELINE](../docs/OPERATIONS_BASELINE.md), 증적과 인수 상태는 [STAGE_A_HANDOFF](../docs/STAGE_A_HANDOFF.md)를 먼저 확인한다.

| 경로 | 보존 내용 |
|---|---|
| `stage-a-guide-v1.5/` | Stage A 구축 가이드 v1.5 원본 |
| `stage-a-completion-v1.3/` | 완료 팩 v1.3의 LB 검사·방화벽·전송 소스 5개, 문서·양식·원래 manifest |
| `stage-a-support/` | 기존 증적 export v1.1 및 SELinux/임시 키 폐기 확인 보완 v1.0 |

완료 팩의 공통 `p1-lb-01-stage-a-nodes.yml`은 [infra-ansible 고정본](https://github.com/321Team/infra-ansible/blob/57e7cc740e7a406387848c52f4aa56b98c516168/playbooks/p1-lb-01-stage-a-nodes.yml)과 Git blob이 동일함을 확인했다. 중복 관리하지 않으므로 여기에는 포함하지 않는다. `ORIGINAL_PACKAGE_SHA256SUMS.txt`는 원래 패키지의 manifest 원문으로, 제외한 playbook도 기재돼 있다. 이 저장소 전체의 무결성은 루트 `SHA256SUMS`로 검증한다.

원본 README 안의 파일 배치, 과거 HOLD/Pending, 테스트 PASS, 계정·키 수명주기와 적용 명령은 당시 문맥의 기록이다. 이번 이관이 전체 원본 실행 로직의 새 독립 승인이나 재실행 승인을 부여하지 않는다. 특히 `apply-firewall`, 네트워크·SELinux 설정, SSH 키 등록·삭제 명령은 서버를 변경한다. 현재 코드 검토와 실행 승인 없이 과거 구축 가이드를 운영 서버에 그대로 재적용하지 않는다.

이번 검증은 원본 byte·기존 패키지 manifest·Bash/Python 구문 확인이다. 과거 소스의 동작 시험이나 현재 호스트 호환성 검증을 새로 수행하지 않았다. [자료 manifest](../docs/MATERIALS_MANIFEST.json)에 출처, 원래 파일명, 개별 해시 및 제외 항목을 기록했다.
