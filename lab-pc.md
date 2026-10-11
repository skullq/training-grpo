# 다른 컴퓨터에서 이어갈 L2/STP 랩 테스트

이 문서 하나로 현재 작업의 상태와 랩에서 검증할 내용을 파악할 수 있습니다.
Git 이동, 환경 설치 및 실행 명령 예시는 포함하지 않습니다.

## 1. 현재 상태와 다음 작업

- 테스트 묶음 ID: `L2_TRANSFER_V1`.
- 신규 20문제는 **미승인·미검증 초안**입니다.
- 사람 리뷰와 신규 문제의 랩 테스트는 아직 수행하지 않았습니다.
- 신규 문제의 모델 응답은 아직 생성하지 않았습니다.
- 이전 SFT 어댑터와 실험 결과는 삭제됐습니다. 과거 결과나 철회된 리뷰를 이번 평가의 근거로 사용하지 않습니다.
- 현재 목적은 학습 실행이 아니라 **신규 문제와 정답 후보의 랩 재현성 확인**입니다.
- 정답 후보를 먼저 검증한 다음, 추후 생성한 모델의 원본 응답을 동일 조건에서 평가합니다.
- 이번 문제를 학습에 사용하면 독립 최종 평가가 아닌 개발용 데이터로 분류합니다.

이 문서는 아래 원본 자료를 사람이 읽기 쉽게 통합한 인계본입니다.
내용을 수정하면 원본과 인계본이 서로 달라지지 않도록 함께 갱신해야 합니다.

- [검증 기준](docs/LAB_TRANSFER_GUIDE.md)
- [배선 및 베이스라인](data/lab-transfer/topology_and_baseline.md)
- [20문제의 구조화된 원본](data/lab-transfer/scenarios_v1.json)
- [결과 양식 원본](data/lab-transfer/results_template.json)

## 2. 랩 배선과 안전 조건

운영망이 아닌 전용 격리 랩에서만 시험합니다. 인증과 관리 설정은 변경하지 않습니다.
다른 실험과 동시에 같은 노드를 사용하지 않습니다.

### 노드 매핑

| 논리 노드 | 기존 Lab 1 노드 |
|---|---|
| A | lab1-sw1 |
| B | lab1-sw2 |
| C | lab1-sw3 |

### 포트 연결

| 포트 | 상대 포트 또는 용도 |
|---|---|
| A Ethernet0/1 | B Ethernet0/1 |
| A Ethernet0/2 | B Ethernet0/2 |
| A Ethernet0/3 | C Ethernet0/1 |
| B Ethernet0/3 | C Ethernet0/2 |
| A Ethernet1/0 | 단말 시험용, 기본 미연결 |
| B Ethernet1/0 | 단말 시험용, 기본 미연결 |
| C Ethernet0/3 | 단말 시험용, 기본 미연결 |
| 각 노드 Ethernet0/0 | 관리 포트, 변경 금지 |

**A/B의 Ethernet0/3은 스위치 연결 포트입니다. 단말용 PortFast를 적용하지 않습니다.**
단말 포트가 미연결이면 설정 검증은 가능하지만 실제 포워딩이나 BPDU 수신 기능은
검증한 것으로 기록하지 않습니다. 다른 랩을 사용하면 실제 노드와 배선 매핑을 기록합니다.

## 3. 공통 초기 상태

인증과 관리 접속이 이미 준비된 깨끗한 격리 랩을 전제로 합니다.
아래 조건만 맞췄다고 임의의 기존 설정이 모두 제거됐다고 판단하지 않습니다.

| 항목 | 공통 베이스라인 |
|---|---|
| VLAN | 110, 120, 130 존재 |
| STP 모드 | 모든 노드 Rapid-PVST+ |
| Extended system ID | 활성 |
| 경로 비용 방식 | short |
| A의 VLAN 110/120/130 Bridge Priority | 각각 16384 |
| B/C의 VLAN 110/120/130 Bridge Priority | 각각 32768 |
| 스위치 연결 포트 | dot1q trunk, 허용 VLAN은 110/120/130 |
| 단말 시험 포트 | access, VLAN 110 |
| 시험 포트의 관리 상태 | 활성 |
| PortFast, BPDU Guard, Root Guard, Loop Guard | 명시 설정 없음 |
| 전역 PortFast/BPDU Guard/Loop Guard 기본 적용 | 꺼짐 |
| 수동 인터페이스·VLAN별 Cost/Port Priority | 없음 |
| Port Priority | 기본값 128 |
| 기존 EtherChannel 및 다른 실험 설정 | 시험에 영향을 주는 설정 없음 |

베이스라인의 Bridge Priority는 VLAN 확장 값을 더하기 전 구성값입니다.
실제 이미지 버전, 링크 속도·대역폭, 포트 상태와 VLAN별 STP 상태를 기록합니다.
이미지별 미지원 기능은 숨기지 않고 승인된 베이스라인 변형으로 기록합니다.

초기 베이스라인을 저장하기 전에 기존 startup-config를 로컬에 별도로 백업해야 합니다.
이후 저장한 시험 베이스라인을 각 문항의 복구 기준으로 사용합니다.
문항의 사전 설정이나 후보 적용 결과는 startup-config로 저장하지 않습니다.

## 4. 매 문항의 시험 순서

1. A/B/C를 모두 저장된 베이스라인으로 복구하고 구성과 상태가 일치하는지 확인합니다.
2. 해당 문항의 사전 설정을 지정 노드에 적용합니다.
3. 구문 수락뿐 아니라 실제 값, 포트 역할 및 문항 전제 조건을 확인합니다.
4. 적용 전 모든 노드의 구성과 STP 상태를 증거로 보존합니다.
5. 정답 후보 또는 모델의 원본 후보를 지정 대상에 적용합니다. 두 종류의 결과는 분리합니다.
6. CLI 수락, 요구 설정, 보존 조건과 필요한 실제 기능을 각각 검증합니다.
7. 적용 후 상태와 관찰 시간을 기록합니다.
8. A/B/C 및 추가로 변경한 모든 노드를 복구하고 복구 증거를 기록합니다.

초기 상태가 성립하지 않거나 원복이 실패하면 `blocked`로 기록하고 중단합니다.
원복이 확인되기 전에는 다음 후보를 실행하지 않습니다.
일시적 상태만으로 성공 판정하지 않으며 관찰 간격과 제한 시간을 사전에 정해 기록합니다.
시간 초과는 자동 성공이 아닙니다.

## 5. 모델에 전달할 공통 문제 조건

다음 공통 조건과 해당 문항의 대상·문제만 모델에 전달합니다.
이 문서 전체, 사전 설정 명령, 정답 후보 또는 검증 기준을 모델 입력에 합치지 않습니다.

> Cisco IOL L2 IOS에서 대상 장비의 전역 구성 모드부터 실행할 최소 명령을 작성한다.
> 필요하면 인터페이스 선택과 구성 모드 전환을 포함한다.
> Ethernet0/0 관리 포트는 변경하지 않는다. VLAN 110/120/130은 이미 존재한다.
> 명시하지 않은 설정과 다른 장비는 유지한다.
> 접속, 전역 구성 모드 진입, 설정 저장 및 조회 명령은 액션에 포함하지 않는다.
> 응답은 `<think>` 판단과 주의사항 요약 `</think><commands>` 명령 `</commands>` 형식이다.
> Bridge Priority는 extended system ID를 더하기 전 값이다.
> 실제로 확인하지 않은 수렴 시간이나 장애 방지 결과를 보장하지 않는다.

## 6. 신규 20문제와 검증 기대값

아래 사전 상태는 매번 공통 베이스라인으로 복구한 뒤 준비합니다.
특별히 명시하지 않은 다른 노드와 설정은 베이스라인을 유지합니다.
기대값은 아직 랩에서 입증하지 않은 정답 후보의 의도이며 성공 결과가 아닙니다.

### TRANSFER_001 — B를 VLAN 110 루트로 변경

- 대상: B. 별도 사전 설정 없음.
- 문제: VLAN 110에서 A Priority 16384, B/C 32768인 상태에서 B의 Priority만 정확히 8192로 설정한다. 루트 매크로는 금지한다.
- 확인: B 구성 Priority 8192, B의 Root ID와 Bridge ID 일치, VLAN 120/130 Priority 보존.

### TRANSFER_002 — 보조 루트 매크로

- 대상: C. 사전 상태: A의 VLAN 120 Priority를 4096으로 준비한다.
- 문제: C의 VLAN 120에 root secondary 매크로를 적용하되 A 루트와 다른 VLAN을 유지한다.
- 확인: 매크로 수락과 변환된 Priority 기록, A 루트 유지, C Priority가 B보다 낮음.
- 장애 후 C의 루트 승계는 별도의 기능 시험 없이는 성공으로 주장하지 않는다.

### TRANSFER_003 — 인터페이스 Cost 설정

- 대상: C Ethernet0/2. 별도 사전 설정 없음.
- 문제: 트렁크의 인터페이스 단위 Cost를 12로 설정한다. VLAN별 Cost는 사용하지 않고 루트 포트 선출을 단정하지 않는다.
- 확인: 인터페이스 Cost 12, 다른 속성과 포트 보존.

### TRANSFER_004 — Cost만 기본으로 복원

- 대상: B Ethernet0/2. 사전 상태: Cost 12, Port Priority 96.
- 문제: 수동 Cost만 제거하고 Port Priority 96은 유지한다.
- 확인: 명시 Cost 설정 제거와 자동 계산된 Cost, Port Priority 96 유지.

### TRANSFER_005 — Port Priority 설정

- 대상: A Ethernet0/2. 별도 사전 설정 없음, Port Priority 기본 128.
- 문제: 인터페이스 Port Priority만 32로 설정하고 Cost와 Bridge Priority를 유지한다.
- 확인: Port Priority 32, Cost와 Bridge Priority 보존.

### TRANSFER_006 — Port Priority만 기본으로 복원

- 대상: C Ethernet0/2. 사전 상태: Port Priority 32, Cost 18.
- 문제: 명시 Port Priority만 제거해 기본 128로 복원하고 Cost 18을 유지한다.
- 확인: 명시 Port Priority 설정 제거와 기본값, Cost 18 보존.

### TRANSFER_007 — 명시 BPDU Guard 활성화

- 대상: B Ethernet1/0. 사전 상태: 단말 access VLAN 110, PortFast 활성, 전역 BPDU Guard 기본 적용 꺼짐.
- 문제: 인터페이스 BPDU Guard만 명시적으로 활성화한다.
- 확인: BPDU Guard 활성 설정, PortFast와 access VLAN 보존.
- BPDU 주입 시험을 하지 않았으면 실제 기능은 `not_run`이다.

### TRANSFER_008 — BPDU Guard만 제거

- 대상: C Ethernet0/3. 사전 상태: PortFast와 명시 BPDU Guard 활성, 전역 기본 적용 꺼짐, errdisable 아님.
- 문제: BPDU Guard 활성 설정만 제거하고 PortFast를 유지한다. 포트 재시작은 금지한다.
- 확인: 명시 BPDU Guard 설정 제거, PortFast 보존, 포트 재시작 없음.

### TRANSFER_009 — 지정 다운링크 Root Guard

- 대상: B Ethernet0/3. 사전 상태: B의 VLAN 110/120/130 Priority를 4096으로 준비한다.
- 전제: B가 루트이며 C 방향 Ethernet0/3이 designated임을 실제 확인한다.
- 문제: Guard와 PortFast가 꺼진 해당 포트에 Root Guard만 설정한다.
- 확인: Root Guard 적용, PortFast와 Loop Guard 추가 없음.
- superior BPDU 기능 시험은 별도 승인된 자극과 복구 확인이 필요하다.

### TRANSFER_010 — 대체 포트 Loop Guard

- 대상: C Ethernet0/2. 사전 상태: C Ethernet0/1 Cost 4, Ethernet0/2 Cost 100.
- 전제: VLAN 130에서 Ethernet0/2가 alternate이고 BPDU를 수신하는지 확인한다. 아니면 `blocked`이다.
- 문제: 상위 B 방향 정상 트렁크에 BPDU 소실 대비 Loop Guard만 설정한다.
- 확인: Loop Guard 적용, Root Guard와 PortFast 없음.
- 기능 시험은 링크를 활성 상태로 유지하고 BPDU 수신만 중단시키는 조건에서 수행한다.

### TRANSFER_011 — 특정 VLAN Priority 제거

- 대상: B. 사전 상태: VLAN 110 Priority 8192, VLAN 120 Priority 12288.
- 문제: VLAN 110의 명시 Priority만 제거해 기본 32768로 복원하고 VLAN 120을 유지한다.
- 확인: VLAN 110 명시 설정 제거와 기본값, VLAN 120 Priority 12288 보존.

### TRANSFER_012 — 단말 PortFast만 활성화

- 대상: C Ethernet0/3. 별도 사전 설정 없음, 단말 access VLAN 110.
- 문제: PortFast만 켠다. 트렁크용 구문이나 BPDU Guard는 추가하지 않는다.
- 확인: PortFast 적용, BPDU Guard와 access VLAN 보존.

### TRANSFER_013 — 불연속 VLAN만 변경

- 대상: B. 사전 상태: B VLAN 120 Priority 12288.
- 문제: VLAN 110/130에서 A Priority 16384, B/C 32768인 상태에서 B의 두 VLAN에만 정확히 Priority 8192를 설정한다. 루트 매크로와 110부터 130까지의 연속 범위는 금지한다.
- 허용 대안: 두 VLAN을 불연속 목록으로 지정하거나 각각 개별 지정한다.
- 확인: VLAN 110/130 Priority 8192와 B 루트, VLAN 120 Priority 12288 보존.

### TRANSFER_014 — 모드 변경과 특정 VLAN Priority

- 대상: A. 사전 상태: A/B/C 모두 PVST+, VLAN 120 A/C Priority 32768, B 16384.
- 문제: 격리 유지보수 랩에서 A의 장비 전체 STP 모드를 Rapid-PVST+로 변경하고 VLAN 120 Priority를 정확히 8192로 지정한다.
- 확인: A 모드와 VLAN 120 Priority, B/C PVST+ 유지, 다른 VLAN의 명시 Priority 보존, 혼용 경계 안정화 기록.
- A의 모드 변경은 모든 VLAN에 영향을 준다. 특정 수렴 시간을 보장하지 않는다.

### TRANSFER_015 — 단말 PortFast와 BPDU Guard

- 대상: A Ethernet1/0. 별도 사전 설정 없음, access VLAN 110이며 인터페이스와 전역 두 기능 모두 꺼짐.
- 문제: PortFast와 명시 BPDU Guard를 모두 켜고 VLAN을 유지한다.
- 확인: 두 기능 설정, access와 VLAN 보존. 설정 순서 변경은 허용한다.

### TRANSFER_016 — 단말의 두 명시 설정 제거

- 대상: B Ethernet1/0. 사전 상태: PortFast와 명시 BPDU Guard 활성, 포트 정상, 전역 두 기능 기본 적용 꺼짐.
- 문제: 두 인터페이스 설정을 모두 제거하되 VLAN/access를 유지한다. 포트 재시작은 금지한다.
- 확인: 두 명시 설정 제거, access/VLAN 보존, 재시작 없음. 제거 순서 변경은 허용한다.

### TRANSFER_017 — Cost/Priority 복원과 Guard 보존

- 대상: C Ethernet0/2. 사전 상태: Cost 18, Port Priority 32, Loop Guard.
- 문제: 인터페이스 Cost와 Port Priority의 명시 설정만 제거하고 Loop Guard와 trunk를 유지한다.
- 확인: Cost 자동 계산, Port Priority 128, Loop Guard/trunk 보존. 제거 순서 변경은 허용한다.

### TRANSFER_018 — 서로 다른 두 포트 설정

- 대상: B. 별도 사전 설정 없음, Ethernet0/1과 Ethernet0/2는 정상 trunk이며 Cost/Priority 기본값.
- 문제: Ethernet0/1에는 인터페이스 Cost 8만, Ethernet0/2에는 Port Priority 48만 설정한다. 구성 모드 전환을 포함한다.
- 확인: 0/1 Cost 8와 기본 Priority, 0/2 Priority 48와 자동 Cost.
- 포트 처리 순서 변경은 허용한다. 구성 모드 전환 구문의 유효성은 실제 CLI로 확인한다.

### TRANSFER_019 — 잘못된 Root Guard를 Loop Guard로 교체

- 대상: C Ethernet0/2. 사전 상태: 상위 B 방향 trunk에 Root Guard 설정.
- 전제: VLAN 130에서 실제 root-inconsistent인지 확인한다. 아니면 `blocked`이다.
- 문제: Root Guard를 제거한 다음 같은 포트에 Loop Guard를 설정한다. PortFast 추가, 포트 초기화와 재시작은 금지한다.
- 확인: Root Guard 제거와 Loop Guard 설정, root-inconsistent 해제, BPDU 수신과 포트 역할 안정화.

### TRANSFER_020 — 전역·포트 선택적 복원

- 대상: C. 사전 상태: VLAN 110 Priority 8192, VLAN 120 Priority 12288, Ethernet0/1 Cost 8와 Port Priority 48.
- 문제: VLAN 110 Priority와 Ethernet0/1 Cost만 제거한다.
- 확인: VLAN 110 기본 Priority와 0/1 자동 Cost, VLAN 120 Priority 12288와 0/1 Port Priority 48 보존.
- 포트 설정부터 처리하면 전역 설정으로 돌아오는 구성 모드 전환이 필요하다.

## 7. 공통 검증 기준

### 후보 적합성

- 모델 응답의 명령 추출 여부와 지정 노드·포트 준수 여부를 확인합니다.
- 관리 접속, 인증, 설정 저장, 재시작 또는 전체 초기화 등 요구 밖 위험 변경은 실행하지 않고 이유를 기록합니다.
- 원본 후보의 구문 오류, 불완전·모호한 명령, 거부와 값 범위 오류를 기록합니다.
- 사람이 수정한 후보의 성공을 원래 모델의 성공으로 기록하지 않습니다.
- **CLI 오류 없음은 목표 달성의 충분조건이 아닙니다.**

### 설정과 보존 조건

- 실제 구성과 STP 상태를 함께 확인합니다.
- 표시 Priority와 VLAN 확장 전 구성값을 구분합니다.
- 요구 대상 외 VLAN, 포트, 우선순위 및 관리 설정이 유지되는지 확인합니다.
- 대체 명령과 순서 차이는 문자열 일치가 아니라 실제 효과와 보존 조건으로 평가합니다.
- 루트 매크로와 정확한 숫자 Priority를 무조건 동등하게 취급하지 않습니다.
- 명시 설정 제거와 명시 비활성화는 전역 기본 적용 상태에 따라 효과가 다를 수 있습니다.

### 기능 검증

- 요구한 루트 브리지 및 루트·지정·대체·차단 포트 역할이 안정적으로 형성되는지 확인합니다.
- BPDU Guard: 승인된 시험 링크에서 BPDU 수신 후 오류 차단 상태와 원인 확인.
- Root Guard: superior BPDU 수신 후 루트 불일치 차단과 자극 제거 후 복구 확인.
- Loop Guard: 링크를 유지한 BPDU 소실 조건과 복구 확인. 단순 링크 종료는 기능 검증이 아닙니다.
- 기능 재현 방법이 없거나 시험하지 않았으면 `functional_status`는 `not_run`입니다.
- 추가 노드 변경과 장애 주입은 승인된 격리 랩에서만 수행하고 모두 원복합니다.

## 8. 판정과 기록

| 항목 | 검증 내용 |
|---|---|
| setup_status | 베이스라인, 사전 설정, 전제 조건 |
| cli_status | 원본 후보의 CLI 수락 |
| required_settings_status | 요구 값과 대상에 설정 적용 |
| preservation_status | 변경 금지 설정 유지 |
| functional_status | 실제 동작 및 복구 |
| rollback_status | 모든 변경 노드의 원복 |
| final_status | 해당 문항의 필수 검증 전체를 반영한 최종 판정 |

상태 값은 `not_run`, `pass`, `fail`, `blocked`, `not_applicable`입니다.

- 초기 상태, CLI, 필수 설정, 보존 조건과 원복이 모두 통과하면 설정 수준 성공입니다.
- 필수 기능 목표가 있는 문항은 실제 기능도 통과해야 최종 성공입니다. 기능 미실행이면 최종 `blocked`입니다.
- `configuration_only`와 `functional_verified`를 구분하고 기능 미검증 결과를 기능 성공률에 합산하지 않습니다.
- 환경 문제로 차단된 시험은 모델 정답률 분모에서 제외하되 제외 건수와 이유를 공개합니다.
- 미실행 시간과 점수는 빈 값으로 유지합니다. 리뷰하지 않았다면 리뷰 정보도 비워 둡니다.
- 원본 응답, 실제 명령, 적용 전·후와 원복 증거, 장비 이미지/버전, 시나리오 버전과 모델 식별 정보를 기록합니다.
- 비밀번호 등 민감정보가 포함된 원본 증거는 로컬에 보관합니다.

기존 [실장비 검증 스크립트](scripts/run_live_lab_validation_v2.py)는 신규 20문제의
모든 목표 상태와 보존 조건을 검증하지 않고 원복 실패 시 중단도 보장하지 않습니다.
그 스크립트의 CLI 오류 검사 결과만으로 최종 성공을 판정하지 않습니다.

### 빈 결과 양식

각 정답 후보 또는 모델 후보의 실제 시험마다 별도 기록을 남깁니다.
`candidate_kind`는 정답 후보의 경우 `reference`, 모델 후보의 경우 `model`로 구분합니다.
아래는 미실행 양식이며 실제 결과가 아닙니다.

```json
{
  "suite_id": "L2_TRANSFER_V1",
  "scenario_id": null,
  "run_id": null,
  "git_commit": null,
  "suite_sha256": null,
  "model_id": null,
  "adapter_sha256": null,
  "candidate_kind": null,
  "candidate_id": null,
  "raw_response": null,
  "commands": [],
  "target_node": null,
  "started_at": null,
  "elapsed_seconds": null,
  "environment": {"image": null, "logical_to_actual_nodes": {}, "port_speeds": {}},
  "setup_status": "not_run",
  "cli_status": "not_run",
  "required_settings_status": "not_run",
  "preservation_status": "not_run",
  "functional_status": "not_run",
  "rollback_status": "not_run",
  "final_status": "not_run",
  "reason": null,
  "evidence": {"before": [], "injection": [], "after": [], "rollback": []},
  "reviewer": null,
  "reviewed_at": null,
  "notes": null
}
```
