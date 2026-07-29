# -*- coding: utf-8 -*-
"""
지속 코치 판단 코어 v0.2
- 출처: 효진 인터뷰 Q1~Q5 (provenance: hyojin_direct) + 2026-07 병행기 전이 세션(R20~R22)
- 설계 원칙: 상태 전이와 신호 감지는 100% 결정적. LLM은 여기 관여하지 않는다.

상태 기계:
  ACTIVE ─ 열정신호 열화 ─▶ DECLINING ─▶ PARALLEL ─▶ DORMANT ─▶ RETURNING ─▶ ACTIVE

핵심 신호 (효진 캐스케이드, Q2):
  1. 즐거움 감소 (측정 불가 — 대화로만 확인)
  2. 회피감 (측정 불가)
  3. 종목 단순화  ← 로그에서 측정 가능 (선행 지표)
  4. 세션 시간 감소 ← 로그에서 측정 가능 (선행 지표)
  5. 결석 (지연 지표 — 이게 뜨기 전에 잡는 것이 목표)

PARALLEL→ACTIVE 이탈 트리거 (R20/R21, hyojin_direct, 2026-07):
  로그 신호(다양성·시간 회복)만으로는 안 잡히는 정성적 트리거 2계열.
  운동 로그가 아니라 '대화'에서만 확인 가능하므로, 이 코어는 감지하지 않고
  PARALLEL_EXIT_TRIGGERS를 참조용 분류표로만 제공한다. 실제 감지·개입은
  대화 레이어(LLM)의 몫이며 100% 결정적 코어의 영역 밖이다.
    (1) risk_signal   — 병행종목에서 통증·과부하 언급 → 즉시 반응, 지켜보지 않음
    (2) env_constraint — 병행종목 수행이 물리적으로 불가능한 환경(계절·시간·날씨)
  R21: 웨이트는 '또 하나의 선택지'가 아니라 다른 운동이 다 막혔을 때 항상
       열려 있는 디폴트 베이스 — 두 트리거 모두 결국 웨이트 복귀로 수렴.

크로스트레이닝 되먹임 (R22, hyojin_direct, 2026-07):
  타 종목 경험이 본 종목(웨이트) 프로그램 자체를 개선시키는 순환 구조.
  판단 코어 상태 전이에는 관여하지 않지만, EFFECT_PROFILES에 참조 정보로 반영.
"""
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


class State(Enum):
    ACTIVE = "활성기"
    DECLINING = "열정저하기"
    PARALLEL = "병행기"
    DORMANT = "휴면기"
    RETURNING = "복귀기"


# ----------------------------------------------------------------------
# 참조용 분류표: PARALLEL 이탈 트리거 (R20)
# 로그로 감지하지 않음 — 대화 레이어가 사용자 발화를 이 두 범주로 분류하고,
# 감지되는 즉시 웨이트 복귀 옵션을 제시한다 (R21: 웨이트 = 디폴트 베이스).
# ----------------------------------------------------------------------
PARALLEL_EXIT_TRIGGERS = {
    "risk_signal": {
        "설명": "병행종목 수행 중 몸이 보내는 명확한 경고(통증·과부하)",
        "반응": "즉시 반응. 지켜보지 않는다 (R15의 모호한 신호와 다름 — 이건 명확한 신호)",
        "예시": "배드민턴 반복 점프 → 무릎 무리",
    },
    "env_constraint": {
        "설명": "병행종목 수행 자체가 물리적으로 불가능해지는 환경(계절·시간·날씨)",
        "반응": "환경이 막히는 즉시 웨이트로 자동 전환 제안",
        "예시": "로드사이클 — 우천·혹서·혹한, 계절·퇴근 후 시간 제약",
    },
}


@dataclass
class Session:
    """운동 세션 로그 한 건"""
    week: int
    day: int
    exercises: list          # 종목 리스트
    duration_min: float
    kind: str = "gym"        # gym | alt(대체운동) | none


@dataclass
class WeekSignals:
    week: int
    gym_sessions: int
    alt_sessions: int
    avg_duration: float      # 헬스 세션 평균 시간
    diversity: float         # 헬스 세션당 평균 종목 수
    total_exercises: set = field(default_factory=set)


def weekly_signals(sessions):
    """세션 로그 → 주 단위 신호 집계"""
    weeks = {}
    for s in sessions:
        w = weeks.setdefault(s.week, {"gym": [], "alt": 0})
        if s.kind == "gym":
            w["gym"].append(s)
        elif s.kind == "alt":
            w["alt"] += 1
    out = []
    all_weeks = range(min(weeks), max(weeks) + 1)
    for wk in all_weeks:
        if wk not in weeks:                      # 결석 주 = 명시적 0 신호
            out.append(WeekSignals(week=wk, gym_sessions=0, alt_sessions=0,
                                   avg_duration=0.0, diversity=0.0))
            continue
        g = weeks[wk]["gym"]
        out.append(WeekSignals(
            week=wk,
            gym_sessions=len(g),
            alt_sessions=weeks[wk]["alt"],
            avg_duration=float(np.mean([s.duration_min for s in g])) if g else 0.0,
            diversity=float(np.mean([len(s.exercises) for s in g])) if g else 0.0,
            total_exercises=set(e for s in g for e in s.exercises),
        ))
    return out


# ----------------------------------------------------------------------
# 신호 감지기: 최근 N주 추세로 열정 열화 판정
# ----------------------------------------------------------------------
@dataclass
class Detection:
    week: int
    passion_decay: bool
    reasons: list
    trend_diversity: float   # 주당 변화율
    trend_duration: float


def detect_passion_decay(signals, window=4,
                         div_drop_thresh=-0.25,   # 종목수 주당 -0.25개 이상 감소
                         dur_drop_thresh=-6.0,    # 시간 주당 -6분 이상 감소
                         min_baseline_weeks=3):
    """
    최근 window주의 선형 추세로 판정.
    규칙 (hyojin_direct, Q2): '종목 단순화'와 '시간 감소'가 결석보다 먼저 온다.
    둘 중 하나라도 지속 추세면 조기 경보. 둘 다면 강한 경보.
    """
    detections = []
    for i in range(len(signals)):
        if i + 1 < max(window, min_baseline_weeks):
            detections.append(Detection(signals[i].week, False, [], 0, 0))
            continue
        win = signals[i + 1 - window:i + 1]
        x = np.arange(window)
        div = np.array([w.diversity for w in win])
        dur = np.array([w.avg_duration for w in win])
        # 결석 주(세션 0)는 추세 계산에서 결측 처리
        mask = np.array([w.gym_sessions > 0 for w in win])
        reasons = []
        t_div = t_dur = 0.0
        if mask.sum() >= 3:
            t_div = float(np.polyfit(x[mask], div[mask], 1)[0])
            t_dur = float(np.polyfit(x[mask], dur[mask], 1)[0])
            if t_div <= div_drop_thresh:
                reasons.append(f"종목 단순화 추세 ({t_div:+.2f}개/주)")
            if t_dur <= dur_drop_thresh:
                reasons.append(f"세션 시간 감소 추세 ({t_dur:+.1f}분/주)")
        # 결석 자체는 지연 지표로 별도 표기
        if signals[i].gym_sessions == 0:
            reasons.append("결석 발생 (지연 지표)")
        detections.append(Detection(signals[i].week, len(reasons) > 0, reasons, t_div, t_dur))
    return detections


# ----------------------------------------------------------------------
# 상태 기계: 전이 규칙 (hyojin_direct)
# ----------------------------------------------------------------------
@dataclass
class Transition:
    week: int
    from_state: State
    to_state: State
    trigger: str


class PersistenceCoach:
    """
    전이 규칙 요약:
      ACTIVE→DECLINING  : 열정 열화 신호 2주 연속 (조기 경보)
      DECLINING→PARALLEL: 대체운동 세션 등장 or 에이전트 개입 수락
      DECLINING→DORMANT : 개입 없이 결석 2주 연속
      PARALLEL→ACTIVE   : 헬스 신호 회복 (다양성·시간 기준선 80% 복귀)
      PARALLEL→DORMANT  : 헬스 세션 3주 연속 0 (병행마저 끊김)
      DORMANT→RETURNING : 헬스 세션 재등장 ('그리움' 신호는 대화 레이어가 감지)
      RETURNING→ACTIVE  : 4주 유지 + 기준선 80% 회복
    """
    def __init__(self):
        self.state = State.ACTIVE
        self.history = []
        self.decay_streak = 0
        self.absent_streak = 0
        self.return_weeks = 0
        self.baseline = None  # (diversity, duration) 활성기 기준선

    def _update_baseline(self, w: WeekSignals):
        if w.gym_sessions > 0:
            if self.baseline is None:
                self.baseline = [w.diversity, w.avg_duration]
            else:  # 지수이동평균
                self.baseline[0] = 0.8 * self.baseline[0] + 0.2 * w.diversity
                self.baseline[1] = 0.8 * self.baseline[1] + 0.2 * w.avg_duration

    def step(self, w: WeekSignals, det: Detection):
        prev = self.state
        trigger = None

        self.absent_streak = self.absent_streak + 1 if w.gym_sessions == 0 else 0
        self.decay_streak = self.decay_streak + 1 if det.passion_decay else 0
        recovered = (self.baseline is not None and w.gym_sessions > 0 and
                     w.diversity >= 0.8 * self.baseline[0] and
                     w.avg_duration >= 0.8 * self.baseline[1])

        if self.state == State.ACTIVE:
            self._update_baseline(w)
            if self.decay_streak >= 2:
                self.state, trigger = State.DECLINING, f"열화 신호 2주 연속: {det.reasons}"

        elif self.state == State.DECLINING:
            if w.alt_sessions > 0:
                self.state, trigger = State.PARALLEL, "대체운동 시작 → 페일오버 성공"
            elif self.absent_streak >= 2:
                self.state, trigger = State.DORMANT, "개입 없이 결석 지속"
            elif recovered and not det.passion_decay:
                self.state, trigger = State.ACTIVE, "자연 회복"

        elif self.state == State.PARALLEL:
            if recovered:
                self.state, trigger = State.ACTIVE, "헬스 열정 복귀 (기준선 80%)"
            elif w.gym_sessions == 0 and self.absent_streak >= 3:
                self.state, trigger = State.DORMANT, "병행 유지 실패 (헬스 3주 0회)"

        elif self.state == State.DORMANT:
            if w.gym_sessions > 0:
                self.state, trigger = State.RETURNING, "헬스 재등장 (그리움 신호)"
                self.return_weeks = 0

        elif self.state == State.RETURNING:
            self.return_weeks += 1
            if self.return_weeks >= 4 and recovered:
                self.state, trigger = State.ACTIVE, "복귀 완료 — '한번 갔던 길'"
            elif self.absent_streak >= 2:
                self.state, trigger = State.DORMANT, "복귀 중단"

        if trigger:
            self.history.append(Transition(w.week, prev, self.state, trigger))
        return self.state

    # ------ 상태별 개입 정책 (대화 레이어에 넘길 지시서) ------
    POLICY = {
        State.ACTIVE:    {"stance": "관찰 + 효과 저널링 (R13)",
                          "do": "모니터링 기본. 단, 가끔 '몸이 단단해진 느낌' 같은 효과 체감을 묻고 기록한다 — 이 기억이 미래 휴면기의 복귀 스프링이 된다.",
                          "never": "불필요한 조언으로 마찰 만들기"},
        State.DECLINING: {"stance": "조기 개입",
                          "do": "'좋아하는 운동 풀'에서 페일오버 제안 (R8). 사람 요소(동호회) 언급 (Q2). 헬스 축소를 실패가 아닌 전략으로 프레임.",
                          "never": "더 열심히 하라고 압박 / 죄책감 유발"},
        State.PARALLEL:  {"stance": "최소 유지 지원 + 이탈 트리거 감청",
                          "do": "헬스는 최소 유지 용량으로: 3대 또는 좋아하는 부위, 그날그날 로테이션 (R7). 목표는 진전이 아니라 끊김 방지임을 명시. 대화 중 PARALLEL_EXIT_TRIGGERS(리스크 신호/환경 제약)가 감지되면 지켜보지 말고 즉시 웨이트 복귀 옵션 제시 — 웨이트는 항상 열려 있는 디폴트 베이스다 (R20/R21).",
                          "never": "프로그레션 요구 / 볼륨 증가 제안 / 명확한 이탈 신호를 몇 주 지켜보자며 미루기"},
        State.DORMANT:   {"stance": "침묵 대기 + 효과결핍 감청 (R13)",
                          "do": "푸시 금지. 사용자가 먼저 말 걸면 죄책감 없이 응대. '쉼은 장애가 아니라 상태'. 대화에서 효과 결핍 언어('몸이 물렁해진 듯', '예전엔 단단했는데')가 나오면 복귀 스프링 작동 신호 → 활성기에 기록한 효과 체감을 상기시키며 RETURNING 제안 가능.",
                          "never": "'돌아오세요' 류 리텐션 메시지 (이탈 가속 요인)"},
        State.RETURNING: {"stance": "복귀 프로토콜",
                          "do": "맨몸운동부터, 옛 기록 앵커링 금지 (R9). '한번 갔던 길은 생각보다 쉽다' 리프레임 (R10). 이 구간의 높은 열정을 인정하고 활용.",
                          "never": "쉬기 전 중량과 비교 / 하락률 언급"},
    }


# ----------------------------------------------------------------------
# 안전 가드레일 (provenance: reference — 임상 표준, 시나리오7 승인 대기)
# ----------------------------------------------------------------------
RED_FLAGS = [
    "방사통(엉덩이·다리·발가락 저림)", "기침/재채기 시 허리 울림",
    "10분 이상 앉기 힘든 지속 통증", "발가락 근력 약화·발끌림",
]


# ----------------------------------------------------------------------
# 페일오버 풀: 효과 프로파일 (provenance: hyojin_direct, Q8)
# 페일오버 제안 = 사용자의 '좋아함' 풀 ∩ 필요한 효과 축
# ----------------------------------------------------------------------
EFFECT_PROFILES = {
    "수영":       {"효과": ["전신 유연성", "유산소 최상급"],
                  "비고": "회복·저충격 축. 크로스트레이닝 되먹임(R22): 지속적 힘(지구력) 체감이 웨이트의 결핍(지구력·유연성)을 드러내 → 스트레칭 상시 편입"},
    "로드사이클": {"효과": ["하체 근력·단단함", "상체 근력(비직관)", "코어 안정", "지속성"],
                  "비고": "핵심은 상체 — 중심 유지가 지속의 열쇠 (8년 경험지)"},
    "배드민턴":   {"효과": ["민첩성", "단시간 고칼로리", "체중 감량(실증)"],
                  "비고": "사람 요소(동호회) 결합 용이"},
}
