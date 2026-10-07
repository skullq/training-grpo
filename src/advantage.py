import numpy as np
from typing import List


def calculate_grpo_advantages(rewards: List[float], eps: float = 1e-8) -> List[float]:
    """
    GRPO (Group Relative Policy Optimization) 상대적 이점(Advantage) 계산
    
    공식:
        A_i = (R_i - mean(R)) / (std(R) + eps)
        
    특이 케이스 처리:
        - 집단(Group) 내 모든 보상이 동일한 경우(std == 0):
          상대적 우위가 존재하지 않으므로 모든 샘플의 Advantage를 0.0으로 설정.
    """
    if not rewards:
        return []

    r_array = np.array(rewards, dtype=np.float64)
    n = len(r_array)

    if n == 1:
        # 단일 샘플인 경우 상대 비교 불가
        return [0.0]

    mean_r = np.mean(r_array)
    std_r = np.std(r_array)

    if std_r < eps:
        # 모든 보상이 같아 우열을 가릴 수 없는 경우
        advantages = np.zeros(n, dtype=np.float64)
    else:
        advantages = (r_array - mean_r) / (std_r + eps)

    return [float(a) for a in advantages]
