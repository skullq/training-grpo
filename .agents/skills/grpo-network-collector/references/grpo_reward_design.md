# GRPO Network Training & Reward Design Reference

## 1. DeepSeek GRPO (Group Relative Policy Optimization) 수학적 원리

전통적인 PPO(Proximal Policy Optimization)는 Value Network(Critic)를 별도로 훈련하여 상태 가치 $V(s)$를 추정하고 Advantage $A_t = R_t - V(s)$를 계산합니다. 이는 모델 파라미터 메모리 소모가 크고 네트워크 상태 추정에 비효율적입니다.

**GRPO**는 별도의 Critic 모델 없이, 동일한 질문/프롬프트 $q$에 대해 $G$개의 롤아웃(Completions) $\{o_1, o_2, \dots, o_G\}$을 샘플링한 후, 그룹 내부의 통계량을 사용하여 Advantage를 직접 계산합니다:

$$A_i = \frac{r_i - \frac{1}{G}\sum_{j=1}^G r_j}{\sqrt{\frac{1}{G}\sum_{j=1}^G (r_j - \bar{r})^2} + \epsilon}$$

### 중요한 엣지 케이스 처리
1. **모든 후보가 실패($r_i = -1.0$)하거나 모두 성공($r_i = 1.0$)한 경우**:
   - $\sigma = 0$ 이 되므로 분모가 $\epsilon$만 남아 Advantage가 비정상적으로 과장될 수 있습니다.
   - 따라서 구현체([src/advantage.py](file:///d:/my-code/training-GRPO/src/advantage.py))에서는 $\sigma < \epsilon$일 때 모든 $A_i$를 `0.0`으로 클램핑합니다.
   - 이는 모델에게 "어느 쪽도 상대적 우위가 없음"을 명확히 전달합니다.

---

## 2. Containerlab 병렬 랩 구성 전략

4~8개의 독립 가상 랩 환경을 유지하기 위한 두 가지 접근 방식:

### 접근 방식 A: 독립된 Containerlab 인스턴스 (권장)
- 각 후보 액션마다 독립된 토폴로지 인스턴스 실행:
  - `clab-grpo-lab1` (포트 2201)
  - `clab-grpo-lab2` (포트 2202)
  - `clab-grpo-lab3` (포트 2203)
  - `clab-grpo-lab4` (포트 2204)
  - `clab-grpo-lab5` (포트 2205)
- **장점**: 병렬 주입 시 상호 간섭이 완전히 차단되며, 테스트 후 초기 컨피그 복구가 단순함 (`configure replace nvram:startup-config` 또는 컨테이너 재기동).

### 접근 방식 B: 순차 주입 및 롤백 (단일 랩)
- 단일 랩에서 Checkpoint 저장 -> Candidate 1 주입 -> 검증 -> Rollback -> Candidate 2 주입.
- 단점: 총 소요 시간이 $N$배로 증가하므로 비동기 병렬화의 이점을 누릴 수 없음.

---

## 3. 네트워크 장비 비동기 핸들링 팁 (Scrapli)

1. **Transport 엔진**:
   - Scrapli의 비동기 드라이버는 `asyncssh` 기반의 `AsyncScrapli`를 사용하는 것이 가장 빠르고 안정적입니다.
2. **프롬프트 감지 (`prompt_regex`)**:
   - `conf t` 진입 시 `(config)#`, `(config-if)#` 등으로 프롬프트가 변경되므로 Scrapli의 자동 프롬프트 감지가 안정적으로 작동하도록 장비 hostname을 통일하는 것이 좋습니다.
3. **타임아웃 설정**:
   - 설정 주입: 15초
   - 수렴 대기: `asyncio.sleep(3)`
   - 검증 조회: 10초
