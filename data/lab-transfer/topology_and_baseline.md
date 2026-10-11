# L2_TRANSFER_V1 배선 및 초기 상태

미검증 초안입니다. 운영망에 적용하지 마세요. 인증/관리 설정은 변경하지 않습니다.
논리 노드는 기존 랩의 `lab1-sw1=A`, `lab1-sw2=B`, `lab1-sw3=C`로 매핑합니다.
다른 랩을 쓰면 실제 배선과 매핑을 먼저 기록하세요. 테스트 중 다른 작업을 하지 않습니다.

## 배선

기존 `labs/iol-all-in-one.clab.yml`의 Lab 1 연결:

| A/B/C 포트 | 상대 |
|---|---|
| A Ethernet0/1 | B Ethernet0/1 |
| A Ethernet0/2 | B Ethernet0/2 |
| A Ethernet0/3 | C Ethernet0/1 |
| B Ethernet0/3 | C Ethernet0/2 |
| A Ethernet1/0 | 단말 시험용, 기본은 미연결 |
| B Ethernet1/0 | 단말 시험용, 기본은 미연결 |
| C Ethernet0/3 | 단말 시험용, 기본은 미연결 |

**A/B Ethernet0/3은 스위치 링크입니다. 여기에 단말용 PortFast를 적용하지 마세요.**
Ethernet0/0은 관리 포트이며 이번 시험의 변경 대상이 아닙니다.
단말 링크가 미연결이면 PortFast 설정만 확인할 수 있으며 포워딩 기능 시험은 not_run입니다.

## 베이스라인 만들기

이 절차는 인증/SSH가 이미 구성된 전용 격리 랩에서 수행합니다.
기존 실험 설정, VLAN별 Cost/Priority, EtherChannel, Guard 등이 없는 깨끗한 상태를
먼저 확인하세요. 아래는 임의 기존 설정을 모두 청소하는 스크립트가 아닙니다.
기존 인증이 들어 있는 원본 startup-config를 별도 로컬 백업한 뒤 시작하세요.

1. 모든 노드 전역 구성 모드에서:

```text
spanning-tree mode rapid-pvst
spanning-tree extend system-id
spanning-tree pathcost method short
no spanning-tree portfast default
no spanning-tree portfast bpduguard default
no spanning-tree loopguard default
vlan 110,120,130
exit
```

2. A/B의 Ethernet0/1, Ethernet0/2, Ethernet0/3에 각각 아래를 적용:

```text
interface Ethernet0/1
switchport trunk encapsulation dot1q
switchport mode trunk
switchport trunk allowed vlan 110,120,130
no shutdown
exit
```

위 블록의 인터페이스 이름만 바꾸어 세 포트를 설정합니다.
C는 Ethernet0/1, Ethernet0/2에만 적용합니다.
이미지에 encapsulation 명령이 없으면 오류를 기록하고 dot1q 고정 지원 여부를
확인한 뒤 승인된 베이스라인 변형으로 기록하세요. 후보 명령을 조용히 교정하지 마세요.

3. A/B의 Ethernet1/0, C의 Ethernet0/3을 각각 단말용으로 설정:

```text
interface Ethernet1/0
switchport mode access
switchport access vlan 110
no shutdown
exit
```

C에서는 인터페이스 이름을 Ethernet0/3으로 바꿉니다.

4. A: `spanning-tree vlan 110,120,130 priority 16384`
   B/C: `spanning-tree vlan 110,120,130 priority 32768`

5. 모든 노드에서 `show running-config`, `show interfaces trunk`,
   `show spanning-tree summary`, 각 VLAN의 `show spanning-tree vlan 110` 등으로 확인.
   Guard/PortFast/BPDU Guard 및 수동 포트 Cost/Priority 설정이 없는지 확인합니다.
   링크 속도/대역폭, 실제 이미지 버전과 포트 상태도 기록합니다.
6. 정상화 후 모든 노드에서 `write memory`로 **suite baseline**을 저장합니다.
   이때 기존 startup-config를 덮어쓴다는 것을 사전에 인지해야 합니다.
   suite 시작 이후에는 setup/후보를 startup-config로 저장하지 않습니다.

## 문항별 초기화

1. A/B/C 모두 EXEC에서 `configure replace nvram:startup-config force`.
2. 오류, rollback 실패, 관리 연결 상실 여부 확인. 실패하면 해당 문항은 blocked로 중단.
3. 각 노드 running-config가 저장한 suite baseline과 같은지 확인.
4. 시나리오 JSON의 `setup`을 지정된 각 노드 전역 구성 모드에 적용.
5. setup CLI 오류와 실제 값/포트 역할을 확인. `preconditions`가 다르면 blocked.
6. 후보 주입 직전 모든 노드의 설정/상태를 `before` 증거로 저장.

공통 베이스라인은 A가 낮은 Priority를 가지므로 C의 B 방향 포트는 상위
BPDU를 받습니다. 010은 C의 A 방향 Cost 4, B 방향 Cost 100을 준비하되
alternate 상태는 반드시 실제 확인합니다. 019는 Root Guard를 설정한 뒤
root-inconsistent가 실제 생겼는지 확인하고, 없으면 문제 전제를 만족하지 않는 것으로 처리합니다.

후보별 실행 후에도 **세 노드를 모두** 원복하고 결과를 확인합니다.
연결 실패 시 콘솔 등 승인된 복구 수단으로 원복하고, 복구가 확인될 때까지 다음 후보를 실행하지 않습니다.
