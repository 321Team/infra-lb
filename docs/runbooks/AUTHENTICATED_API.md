# 인증 API 시험 준비

상태: 절차 준비. 실제 인증/API 요청 미수행. 시작 시 [EXECUTION_INPUTS.json](../../templates/EXECUTION_INPUTS.json)의 해당 입력과 현재 CP 준비 상태를 확인한다.

## 2026-09-24 후속의 실행 경로

이번에는 이미 IF-11A 허용 Source이며 기존 `/etc/kubernetes/admin.conf` 사용 이력이 있는 control01 `.102`를 점검 Source로 선택한다. Runner에 자격증명을 신규 배포하지 않는다. 일반 로그인 계정에서 `sudo -v` 후 [후속 절차](STAGE_B_FOLLOWUP_20260924.md)의 수집기를 실행한다. 기존 승인 계정·권한과 예상 identity가 맞지 않으면 중단한다. 이 사전점검으로 장애 구간의 API 연속성을 판정하지 않는다.

수집기는 정해진 host/source/context, proxy·TLS·인증 helper/impersonation 유무를 확인하고 `whoami`, 제한된 NodeList GET, readyz를 각 1회만 실행한다. 비익명 identity 일치와 Node 6대 Ready를 분리해 기록하며 실패·timeout·권한 부족은 STOP으로 남긴다. Go-template의 boolean 출력만 저장하므로 kubeconfig·토큰·개인키·proxy URL·exec 인자를 수집하지 않는다. 공개 discovery cache가 생기면 실행 결과 디렉터리에만 남고 제출 archive에서는 제외한다.

## 시작 조건

1. 허용 source는 우선 Runner `10.250.10.20/32`. 대체 source는 승인된 Node 6대 중 한 대로 명시한다. `ansible01 10.250.10.10`은 기존 Negative 대상이므로 Positive 시험 source로 쓰지 않는다.
2. LB preflight 결과와 Kubernetes 담당자의 현재 준비 상태를 대조한다. CP1만 준비됐을 때의 진단 API 성공을 3CP Stage B 완료로 처리하지 않는다.
3. 해당 source에 이미 허가된 전용 kubeconfig/context와 CA 검증 수단이 있어야 한다. 자격증명이 없으면 담당자가 허용된 전달 절차로 준비한다. `admin.conf`나 토큰을 채팅·Git·수집 ZIP에 넣지 않는다. 권한 부족을 이유로 cluster-admin을 새로 부여하지 않는다.
4. Endpoint는 `https://10.1.93.109:6443`. 아래 예시는 `.109` IP SAN을 검증한다. 인증서가 이를 지원하지 않으면 오류 원인을 확인하고 승인된 DNS/TLS 이름을 확정한다. `-k` 또는 TLS 검증 생략으로 통과시키지 않는다.

## 수집할 최소 명령

아래는 **준비 절차**다. 실제 kubeconfig/context를 로컬에서 확정한 후 실행한다. 비밀 값을 명령줄 인자로 직접 붙이거나 `set -x`를 사용하지 않는다.

```bash
# 로컬 경로와 context만 지정한다. 인증서·토큰 원문은 넣지 않는다.
LB_KUBECONFIG=/actual/local/approved-kubeconfig
LB_CONTEXT=actual-approved-context

ip -j -4 route get 10.1.93.109
kubectl --kubeconfig "$LB_KUBECONFIG" --context "$LB_CONTEXT" config view --minify \
  -o jsonpath='{.clusters[0].cluster.server}{"\n"}{.clusters[0].cluster.proxy-url}{"\n"}{.clusters[0].cluster.insecure-skip-tls-verify}{"\n"}'
```

route의 실제 source가 승인된 주소인지 확인한다. kubeconfig proxy-url이 비어 있지 않으면 예상 source 경로가 달라질 수 있으므로 확인 전 진행하지 않는다. HTTP(S)_PROXY/ALL_PROXY 환경 설정 역시 시험 요청을 우회하지 않도록 검토한다. 아래 명령은 해당 프록시 환경변수만 요청 프로세스에서 제외한다. 현재 shell 환경이나 kubeconfig 파일은 바꾸지 않는다.

```bash
env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  timeout --signal=TERM --kill-after=2s 15s \
  kubectl --kubeconfig "$LB_KUBECONFIG" --context "$LB_CONTEXT" \
  --server=https://10.1.93.109:6443 --tls-server-name=10.1.93.109 \
  --insecure-skip-tls-verify=false --request-timeout=5s \
  auth whoami -o json

env -u HTTP_PROXY -u HTTPS_PROXY -u ALL_PROXY -u http_proxy -u https_proxy -u all_proxy \
  timeout --signal=TERM --kill-after=2s 15s \
  kubectl --kubeconfig "$LB_KUBECONFIG" --context "$LB_CONTEXT" \
  --server=https://10.1.93.109:6443 --tls-server-name=10.1.93.109 \
  --insecure-skip-tls-verify=false --request-timeout=5s \
  get nodes -o name
```

`whoami`가 반환한 identity가 예정된 사용자와 일치하고 `system:anonymous`가 아닌지 확인한다. 해당 버전에서 지원되지 않거나 권한이 없으면 인증 증거 미충족으로 남기고 담당자와 대체 증거를 확정한다. `get nodes`는 허가된 읽기 권한이 있을 때만 사용한다. 필요한 경우 담당자가 승인한 비밀정보 없는 조회 리소스로 명령·예상 출력을 미리 고정한다.

인증 성공과 API 조회 성공은 모두 확인한다. `/readyz`, `/version`의 응답이나 TCP 성공만으로 인증 성공을 선언하지 않는다. whoami만 성공하고 GET이403이면 인증 확인 / 조회 권한 미충족으로 분리한다.

## 증적 형식

일반 계정 실제 home에 새 디렉터리를 만들고 각 명령의 시작/종료 UTC·KST, 명령, 즉시 캡처한 rc, stdout/stderr를 별도 보존한다. 후처리 명령의 rc를 API rc로 쓰지 않는다. 실패/timeout/403/TLS 오류를 삭제하지 않는다. 대상 URL, 실제 source, context 식별자, 비밀정보 없는 예상 identity, kubectl 버전을 기록한다. kubeconfig·토큰·개인키·CA 원문은 묶지 않는다.

장애 시험 때는 위 승인된 GET을 새 프로세스로 반복해 새 연결을 관찰한다. 관측 간격·총시간·허용 실패 수·최대 연속 실패시간은 실행 입력에서 사전 확정한다. 인위적인 재시도로 실패를 숨기지 않는다. 정기 표본 사이의 완전 무중단까지 입증한다고 표현하지 않는다.

검토용 고정본과 내부 SHA256SUMS를 만든 뒤 `.tar.gz` 및 외부 `.sha256`을 제출한다. 성공 응답 수/전체 요청 수, 실패 유형·최대 공백을 기록해 담당자가 판정한다.

## 공식 명령 근거

- [kubectl auth whoami](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_auth/kubectl_auth_whoami/): 현재 인증된 주체 조회
- [kubectl get](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_get/): server, context, TLS 검증 및 요청 timeout 옵션
