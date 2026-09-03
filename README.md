# 지속 코치 (Persistence Coach) — Deterministic Core for Human Persistence

> **SLO: Uptime, not 1RM.**  
> 20년 지속한 사람의 기질(신호 감지·즉시 행동)을 유한 상태 기계(FSM)와 결정적 규칙 코어로 절차화한 AI 코칭 에이전트 시스템입니다.
<a href="https://spring-kr.github.io/Persistence_Coach/" target="_blank"></a>

## 1. 아키텍처 개요 (Deterministic Core + LLM Separation)

기존 AI 코칭의 가장 큰 결함은 LLM이 '판단'과 '위로'를 동시에 시도하다가 상태 맥락 없이 위험한 잔소리나 임의의 조언(환각)을 생성한다는 점입니다. 
본 시스템은 **판단(Decision)과 표현(Expression)을 완전히 분리**합니다.

<img width="418" height="349" alt="image" src="https://github.com/user-attachments/assets/a4d288ce-7f47-4c61-9de4-8a0405483399" />



## 2. 핵심 기능

- **5상태 유한 상태 기계 (5-State FSM):** `ACTIVE`(활성기), `DECLINING`(열정저하기), `PARALLEL`(병행기), `DORMANT`(휴면기), `RETURNING`(복귀기) 간 전이를 엄격한 데이터 임계값으로 통제합니다.
- **Rule R15 조기 경보 엔진 (5주 선행 감지):** '결석(출석률 0%)'은 이미 늦은 지연 지표입니다. 세션당 종목 수 감소(`div_slope ≤ -0.3`)와 평균 시간 급감(`dur_slope ≤ -6분`)을 감지해 슬럼프를 사전에 방어합니다.
- **Failover 정책 (Rules R7, R8, R20, R21):** 환경 제약(날씨, 야근)이나 관절 과부하 신호 감지 시, 훈련을 강행하거나 포기하지 않고 즉시 '최소 유지' 또는 '대체 운동 풀'로 시스템을 우회시킵니다.
- **Provenance 원칙 (데이터 무결성):** 코퍼스의 모든 판단 규칙은 실전 검증 정본(`hyojin_direct`)만을 승인하며, AI 생성 답변의 코어 혼입을 원천 차단합니다.

## 3. 파일 구조

- `judgment_core.py`: 5-State FSM 및 신호 감지 코어 로직
- `validate_core.py`: 24주 합성 데이터 기반 회귀 테스트 슈트
- `persistence_coach_demo.html`: 서버 없이 브라우저 로컬 스토리지로 100% 오프라인 구동되는 실시간 대시보드 및 코칭 데모

## 4. 라이선스
MIT License
