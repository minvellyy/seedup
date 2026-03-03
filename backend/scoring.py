# scoring.py

def compute(answer):
    """
    answer: dict (key: q1~q10, value: int or list)
    Returns: (total_score, base_type, final_type)
    """
    # 점수 계산 규칙
    # 1~10번 점수 합산, 총점 45점
    # 3번(투자경험), 9번(투자예정기간)은 복수선택 가능, 최고점 1개만 반영
    score = 0
    for i in range(1, 11):
        key = f"q{i}"
        val = answer.get(key)
        if i in [3, 9]:
            # 복수선택: 최고점 1개만 반영
            if isinstance(val, list):
                score += max(val) if val else 0
            else:
                score += int(val) if val else 0
        else:
            score += int(val) if val else 0

    # base_type 결정
    if score >= 30:
        base_type = "공격투자형"
    elif score >= 25:
        base_type = "적극투자형"
    elif score >= 20:
        base_type = "위험중립형"
    elif score >= 15:
        base_type = "안전추구형"
    else:
        base_type = "안정형"

    # final_type 매트릭스
    q9 = answer.get("q9")
    if isinstance(q9, list):
        q9_score = max(q9) if q9 else 1
    else:
        q9_score = int(q9) if q9 else 1
    q9_score = max(1, min(5, q9_score))
    matrix = {
        "공격투자형": {1: "위험중립", 2: "공격", 3: "공격", 4: "공격", 5: "공격"},
        "적극투자형": {1: "위험중립", 2: "적극", 3: "적극", 4: "공격", 5: "공격"},
        "위험중립형": {1: "안전추구", 2: "위험중립", 3: "적극", 4: "적극", 5: "공격"},
        "안전추구형": {1: "안전추구", 2: "안전추구", 3: "위험중립", 4: "위험중립", 5: "위험중립"},
        "안정형": {1: "안정", 2: "안전추구", 3: "안전추구", 4: "위험중립", 5: "위험중립"},
    }
    final_type = matrix[base_type][q9_score]
    return score, base_type, final_type
