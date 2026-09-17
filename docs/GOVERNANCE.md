# 변경·리뷰·증적 정책

## 소유와 승인

이하영(`hayeounglee`)이 LB 독립 리뷰·인수를 담당하고, 이권욱(`GWONUK`)이 최종 병합 여부를 판단한다. 작성자와 다른 리뷰어의 현재 PR HEAD 검토를 기록한다. AI 자체 검토·로컬 테스트 결과만으로 독립 리뷰를 대체하지 않는다. 리뷰어가 해당 PR 작성자라면 별도 독립 리뷰어를 지정한다.

1. `feat/`, `fix/`, `docs/`, `chore/` 브랜치에서 변경한다. `main` 직접 push·force push·무승인 병합을 금지한다.
2. PR에 문제, 범위, 기준 커밋, 검증, 서버 영향, 복구 방법을 적는다. 준비 중에는 Draft를 사용한다.
3. 검토할 HEAD 전체 SHA를 PR에 기록하고 독립 리뷰를 요청한다. 새 commit이 생기면 기존 승인 효력을 자동 승계하지 않고 변경분을 재검토한다.
4. 최종 승인에는 대상 PR과 HEAD를 명시한다. 승인 후 HEAD가 바뀌면 다시 확인한다. 자동 병합은 사용하지 않는다.
5. 코드 병합 승인·서버 실행 승인·Runtime 결과·인수 승인은 각각 구분한다. 저장소 생성/소스 이관은 기존 검사를 다시 실행하라는 지시가 아니다.

## 저장소와 실제 보호 설정

2026-09-17 초기 조회: private, 기본 브랜치 main, `protected=false`, auto-merge 비활성. 초기 README commit 이후 모든 변경은 PR로 처리한다.

현재 연결 도구는 브랜치 보호·Rulesets 등 저장소 관리 설정의 변경 기능을 제공하지 않는다. 이 정책 파일로 GitHub 설정을 강제할 수 없다. 조직의 현재 플랜에서 private 저장소 보호를 사용할 수 있는지 관리자가 확인한 뒤, 사용할 수 있으면 main에 다음을 설정한다.

- PR 필수 및 작성자 외 최소 1명 승인
- 새 push 시 오래된 승인 해제 및 대화 해결
- force push와 브랜치 삭제 제한; 관리자 우회 범위 검토
- 실제 CI가 도입되기 전에는 존재하지 않는 required status check를 지정하지 않음

미지원 상태에서는 같은 기준으로 수동 운영하고 강제 보호가 활성화됐다고 표시하지 않는다. 활성화 시 Ruleset/branch protection의 실제 조회 결과를 별도 변경으로 기록한다.

참조: [GitHub protected branches 공식 안내](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches).

## 소스와 증적

- 설정·수집기·시험 절차는 infra-lb에서 수정한다. 실행에는 검토된 commit SHA를 고정한다.
- 원본 로그·명령 rc·archive·내부/외부 해시는 evidence 절차로 접수한다. 이 저장소에 실제 수집 결과나 압축 묶음을 쌓지 않는다.
- 키·토큰·kubeconfig·admin.conf·환경 비밀값은 커밋하지 않는다. 테스트 fixture는 실제 신규 Runtime 증거로 사용하지 않는다.
- 원본 byte와 과거 승인 이력을 수정하지 않는다. 보완 해석·새 결과는 새 기록으로 남긴다.
- `docs/SOURCE_LOCK.json`은 초기 편입 출처 기록이다. 소스 변경 시 초기 출처를 지우지 않고 변경 PR 및 새 검증 근거를 남긴다.
- `SHA256SUMS`는 자기 자신을 제외한 이 저장소의 관리 파일 전체를 대상으로 갱신한다. `.git`, 캐시, 로컬 출력은 포함하지 않는다.

## 실행과 복구

새 LB 서버 변경에는 대상·작업창·정확한 변경/복구 명령·허용 source·실행/복구 담당·중단 조건과 승인 기록이 필요하다. 기존 검사에서 PASS라는 이유로 자동 배포·reload·restart·방화벽 변경을 수행하지 않는다. Failover의 미확정 입력은 `templates/EXECUTION_INPUTS.json`에 남기며 공란을 완료로 처리하지 않는다.

복구 가능성 검토와 실제 복구 확인은 구분한다. 장애 시험 실패도 원상복구 결과까지 보존한다. 이 초기 PR에는 배포나 장애 주입 자동화가 없다.
