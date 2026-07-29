# -*- coding: utf-8 -*-
"""
대화 레이어 프롬프트 빌더 v0.1
- 판단 코어(judgment_core.py)와 표현(LLM)을 분리하는 원칙(모듈 독스트링 참조)에 따라,
  이 파일은 상태별 시스템 프롬프트를 '조립'만 한다. 판단 로직 자체는 여기 없다.
- 특히 PARALLEL 상태는 judgment_core.PARALLEL_EXIT_TRIGGERS(R20)를
  로그가 아니라 '대화'로 감지해야 하므로, 그 감지·반응 지침을 프롬프트에 명시적으로 태운다.

사용법:
    from dialogue_layer import build_system_prompt
    system_prompt = build_system_prompt(coach.state)
    # → 이 프롬프트 + 사용자 발화를 LLM에 그대로 넘긴다
"""
from judgment_core import (State, PersistenceCoach, PARALLEL_EXIT_TRIGGERS,
                           ConversationSignal, classify_parallel_trigger)


# ----------------------------------------------------------------------
# 골든 레퍼런스 (hyojin_approved) — R20/R21 전용
# 코퍼스 F절 G1~G3과 다른 패턴이라는 점이 핵심:
#   G1(DECLINING, 애매한 신호) → "그럴 때 있죠" 정상화가 먼저
#   G4/G5(PARALLEL, 명확한 신호) → 정상화 없이 즉시 행동 제안 (R15 vs R20 차이)
# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# 정본 텍스트 블록 — 코퍼스(coaching_corpus_v1.md)에서 옮겨온 것.
# 데모 HTML(persistence_coach_demo.html)은 이 값을 손으로 베끼지 말고
# build_demo.py로 생성해서 채운다 (3중 소스 동기화 문제 해결).
# ----------------------------------------------------------------------
RULES_TEXT = """[검증된 판단 규칙 — 출처: 20년차 리프터 효진 인터뷰 (hyojin_direct)]
R7 최소 유지 용량: 열정 저하기의 헬스는 '3대운동 또는 좋아하는 부위를 그날그날 로테이션'으로 결정 비용을 최소화해 유지한다. 목표는 진전이 아니라 끊기지 않음.
R8 페일오버는 최적화가 아니라 좋아함: 대체 운동은 크로스트레이닝 효율로 고르지 않는다. 사용자가 미리 등록한 '좋아하는 운동 풀'에서 고른다. 동호회 등 사람 요소가 열정의 연료.
R9 복귀는 맨몸부터: 복귀 시 옛 기록의 %가 아니라 맨몸운동에서 시작한다. '맨몸이 이렇게 힘들다니'라는 충격도 정상 과정으로 수용시킨다.
R10 한번 갔던 길: 재상승은 처음보다 빠르다. 복귀기를 재활이 아니라 '열정적이고 재밌는 구간'으로 리프레임한다.
핵심 철학: 이 코치의 SLO는 1RM이 아니라 uptime이다. 기록을 죽이는 유일한 변수는 그만두는 것."""

GUARDRAIL_TEXT = """[안전 가드레일 — 출처: 임상 표준 (reference)]
사용자 메시지에 통증 신호(허리/관절 통증, 저림, 뻐근함 등)가 나오면 즉시 코칭을 중단하고 통증 상담으로 전환한다.
다음 중 하나라도 해당하면 '지금 당장' 정형외과/신경외과 진료를 강력 권고: 엉덩이·다리·발가락 방사통(저림), 기침·재채기 시 허리 울림, 10분 이상 앉기 힘든 통증, 발가락 근력 약화·발끌림.
통증 원인 규명 전까지 해당 부위 고중량 운동 중단을 안내한다. 진단하지 말 것 — 가능성 언급과 병원 안내까지만."""


GOLDEN_PARALLEL_TRIGGERS = """
G4. 리스크 신호형 (risk_signal) — 예: "요즘 배드민턴 치는데 무릎이 좀 안 좋아진 것 같아요"
> 무릎 신호는 며칠 지켜볼 게 아니에요. 지금은 배드민턴 잠깐 쉬시는 게 나을 것 같아요.
> 대신 헬스장은 무릎에 부담 없는 쪽으로 채울 수 있어요 — 오늘 뭐 하나만 가볍게 해볼까요?

G5. 환경 제약형 (env_constraint) — 예: "요즘 비도 오고 너무 더워서 로드사이클을 통 못 타요"
> 지금은 로드사이클 타기 힘든 계절이네요. 이럴 때 헬스장이 딱이에요 — 날씨도 시간도 안 가리니까요.
> 이번 주에 가볍게 하나만 시작해볼까요?

주의: 통증이 RED_FLAGS(방사통·기침 시 허리 울림·10분 좌식 곤란·발가락 근력 약화) 수준이면
G4보다 안전 가드레일(G2)이 우선한다 — R20은 안전 절차를 대체하지 않는다.
""".strip()


def _policy_block(state: State) -> str:
    p = PersistenceCoach.POLICY[state]
    return (
        f"[현재 상태: {state.value}]\n"
        f"자세: {p['stance']}\n"
        f"할 것: {p['do']}\n"
        f"하지 말 것: {p['never']}"
    )


def _parallel_trigger_block() -> str:
    lines = ["[PARALLEL 이탈 트리거 감지 지침 — 출처: hyojin_direct, 2026-07 병행기 전이 세션]",
             "현재 상태가 병행기(PARALLEL)일 때만 적용. 사용자 발화에서 아래 두 신호를 감지하라 — 로그로는 안 잡히므로 대화가 유일한 감지 수단이다."]
    for key, info in PARALLEL_EXIT_TRIGGERS.items():
        lines.append(f"- {key}: {info['설명']} → {info['반응']} (예: {info['예시']})")
    lines.append(
        "감지되면 지켜보자고 미루지 말고 즉시 반응한다 (R15의 모호한 신호와 달리 이건 명확한 신호). "
        "웨이트는 다른 운동이 막혔을 때 항상 열려 있는 디폴트 베이스임을 상기시키고(R21), "
        "실행 직전 구체 옵션까지 제시한다(R12)."
    )
    lines.append(
        "출력 형식: 응답 맨 앞에 [[TRIGGER:risk_signal]] / [[TRIGGER:env_constraint]] / [[TRIGGER:none]] "
        "중 하나를 반드시 붙인다 (사용자에게는 안 보이고 시스템이 로그/피드백 루프용으로 분리한다). "
        "그 다음 줄부터 실제 사용자에게 보일 답변을 쓴다."
    )
    lines.append("")
    lines.append(GOLDEN_PARALLEL_TRIGGERS)
    return "\n".join(lines)


def build_system_prompt(state: State) -> str:
    """상태에 맞는 시스템 프롬프트 조립. PARALLEL은 트리거 감지 지침을 추가로 붙인다."""
    blocks = [
        "당신은 '지속 코치'다. 목표 지표는 1RM이 아니라 끊기지 않음이다.",
        "대화 레지스터(R11): 일상어로 말한다. uptime, SLO 같은 엔지니어링 프레임은 쓰지 않는다.",
        _policy_block(state),
    ]
    if state == State.PARALLEL:
        blocks.append(_parallel_trigger_block())
    return "\n\n".join(blocks)


# build_demo.py 등 외부에서 이 세 블록만 콕 집어 쓸 수 있게 공개 별칭.
parallel_triggers_text = _parallel_trigger_block


# ----------------------------------------------------------------------
# 로깅용 태깅 컨벤션 (analytics — FSM 전이 자체는 여전히 로그 기반으로만 결정)
# LLM 응답 앞에 아래 형식의 숨김 태그를 붙이게 하고, 사용자에게 보이기 전에 벗겨서
# 트리거 발생 빈도를 기록한다. 이건 상태 전이를 강제하지 않는다 — 참고 신호일 뿐이다.
#   [[TRIGGER:risk_signal]] / [[TRIGGER:env_constraint]] / [[TRIGGER:none]]
# ----------------------------------------------------------------------
def strip_trigger_tag(raw_response: str):
    """LLM 원응답에서 태그를 분리. 반환: (사용자에게 보일 텍스트, 태그값 또는 None)"""
    if raw_response.startswith("[[TRIGGER:"):
        end = raw_response.find("]]")
        tag = raw_response[10:end]
        visible = raw_response[end + 2:].lstrip()
        return visible, tag
    return raw_response, None


def build_conv_signal(user_utterance: str, raw_llm_response: str) -> ConversationSignal:
    """R20/R21 피드백 루프의 입구 — coach.step(conv=...)에 넘길 신호를 만든다.
    우선순위: ① LLM이 [[TRIGGER:...]] 태그를 달았으면 그걸 신뢰 (source="llm")
             ② 태그가 없거나 'none'이면 결정적 키워드 폴백으로 한 번 더 확인
                (LLM이 태그를 빠뜨렸을 때의 안전망 — 코어 단독 폴백과 같은 사상)
    """
    _, tag = strip_trigger_tag(raw_llm_response)
    if tag in ("risk_signal", "env_constraint"):
        return ConversationSignal(trigger=tag, source="llm")
    return classify_parallel_trigger(user_utterance)


if __name__ == "__main__":
    print(build_system_prompt(State.PARALLEL))
