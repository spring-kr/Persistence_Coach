# -*- coding: utf-8 -*-
"""
검증: 효진 스토리를 재현한 합성 24주 로그
  1-6주  활성기 (주4회, 다양한 종목, 80분)
  7-11주 서서히 열화 (종목 단순화, 시간 감소)   ← 여기서 조기경보가 떠야 함
  12-14주 결석 시작 → 완전 결석
  15-18주 휴면
  19주   헬스 재등장 (맨몸 위주 복귀)
  19-24주 점진 회복

합격선: 조기경보(DECLINING 진입)가 첫 결석(12주)보다 몇 주 앞서는가 (리드타임 ≥ 2주)
"""
import numpy as np
from judgment_core import (Session, weekly_signals, detect_passion_decay,
                           PersistenceCoach, State, WeekSignals, Detection)

RNG = np.random.default_rng(7)
POOL = ["스쿼트", "벤치", "데드", "OHP", "로우", "풀업", "레그프레스", "컬"]

def make_log():
    sessions = []
    for wk in range(1, 25):
        if wk <= 6:      n, div, dur = 4, (4, 6), (70, 90)
        elif wk <= 8:    n, div, dur = 4, (3, 4), (60, 75)
        elif wk <= 10:   n, div, dur = 3, (2, 3), (45, 60)
        elif wk == 11:   n, div, dur = 2, (1, 2), (35, 45)
        elif wk == 12:   n, div, dur = 1, (1, 2), (30, 40)
        elif wk <= 18:   n, div, dur = 0, (0, 0), (0, 0)
        elif wk == 19:   n, div, dur = 2, (2, 3), (40, 50)   # 복귀: 맨몸/가볍게
        elif wk <= 21:   n, div, dur = 3, (3, 4), (50, 65)
        else:            n, div, dur = 4, (4, 6), (65, 85)
        for d in range(n):
            k = RNG.integers(div[0], div[1] + 1)
            sessions.append(Session(
                week=wk, day=d,
                exercises=list(RNG.choice(POOL, size=max(k, 1), replace=False)),
                duration_min=float(RNG.uniform(*dur)) if dur[1] > 0 else 0.0,
                kind="gym"))
        # 13주부터 대체운동(수영) 시작한 세계선도 함께 검증하려면 kind="alt" 추가 가능
    return sessions

def run(label, sessions):
    sig = weekly_signals(sessions)
    det = detect_passion_decay(sig)
    coach = PersistenceCoach()
    print(f"\n=== {label} ===")
    print(f"{'주':>3} {'헬스':>4} {'종목':>5} {'시간':>6} {'상태':<8} 경보사유")
    first_alert = first_absent = None
    for w, d in zip(sig, det):
        st = coach.step(w, d)
        if d.passion_decay and first_alert is None and "결석" not in " ".join(d.reasons):
            first_alert = w.week
        if w.gym_sessions == 0 and first_absent is None:
            first_absent = w.week
        mark = " ⚠" if d.passion_decay else ""
        print(f"{w.week:>3} {w.gym_sessions:>4} {w.diversity:>5.1f} {w.avg_duration:>6.0f} {st.value:<8}{mark} {'; '.join(d.reasons)}")
    print("\n[전이 이력]")
    for t in coach.history:
        print(f"  {t.week}주: {t.from_state.value} → {t.to_state.value} | {t.trigger}")
    if first_alert and first_absent:
        print(f"\n조기경보 리드타임: 첫 경보 {first_alert}주 vs 첫 결석 {first_absent}주 → {first_absent - first_alert}주 선행")
    return coach

if __name__ == "__main__":
    run("효진 스토리 재현 (24주)", make_log())

def make_log_failover():
    """세계선 B: 10주차에 수영(대체운동) 시작 → 병행기 경로 검증"""
    sessions = make_log()
    # 13~18주 완전결석 구간을 병행기로 대체: 헬스 주1회 최소유지 + 수영 주2회
    sessions = [s for s in sessions]
    for wk in range(10, 19):
        for d in range(2):
            sessions.append(Session(week=wk, day=10+d, exercises=["수영"],
                                    duration_min=60, kind="alt"))
        if 13 <= wk <= 18:
            k = int(RNG.integers(1, 3))
            sessions.append(Session(week=wk, day=5,
                                    exercises=list(RNG.choice(POOL, size=k, replace=False)),
                                    duration_min=float(RNG.uniform(30, 45)), kind="gym"))
    return sessions

run("세계선 B: 페일오버 성공 (수영 병행)", make_log_failover())


# ----------------------------------------------------------------------
# 회귀 테스트: R20/R21 (병행기 이탈 트리거) — hyojin_direct, 2026-07
# LLM 호출 없이 결정적으로 검증 가능한 범위만 다룬다:
#   1) 세계선 B가 실제로 PARALLEL 상태를 거치는가 (데모에 병행기 주차가 있어야 함)
#   2) judgment_core.PARALLEL_EXIT_TRIGGERS에 두 트리거 키가 정확히 존재하는가
#   3) dialogue_layer.build_system_prompt(PARALLEL)에 R20/R21/골든(G4,G5) 핵심 문구가
#      빠짐없이 들어가는가 (코퍼스·코드가 어긋나면 여기서 즉시 실패해야 함)
# 실제 대화 반응이 골든과 얼마나 가까운지는 LLM 채점이 필요해 이 회귀 테스트 범위 밖.
# ----------------------------------------------------------------------
def test_r20_r21():
    from dialogue_layer import build_system_prompt, PARALLEL_EXIT_TRIGGERS as DL_TRIGGERS
    from judgment_core import PARALLEL_EXIT_TRIGGERS as CORE_TRIGGERS

    print("\n=== 회귀 테스트: R20/R21 ===")
    failures = []

    # 1) 세계선 B에 PARALLEL 상태가 실제로 등장하는지
    sig_b = weekly_signals(make_log_failover())
    det_b = detect_passion_decay(sig_b)
    coach_b = PersistenceCoach()
    states_b = [coach_b.step(w, d) for w, d in zip(sig_b, det_b)]
    if State.PARALLEL not in states_b:
        failures.append("세계선 B에서 PARALLEL 상태가 한 번도 등장하지 않음 (데모용 병행기 주차 없음)")
    else:
        print(f"  OK: 세계선 B는 {states_b.count(State.PARALLEL)}주 동안 PARALLEL 상태를 거침")

    # 2) 코어의 트리거 참조표 키 확인 (dialogue_layer가 같은 표를 가져다 쓰므로 여기 없으면 임포트부터 깨짐)
    expected_keys = {"risk_signal", "env_constraint"}
    if set(CORE_TRIGGERS.keys()) != expected_keys:
        failures.append(f"PARALLEL_EXIT_TRIGGERS 키 불일치: {set(CORE_TRIGGERS.keys())}")
    else:
        print("  OK: PARALLEL_EXIT_TRIGGERS 키 = risk_signal, env_constraint")

    # 3) PARALLEL 프롬프트에 필수 문구가 빠짐없이 포함되는지
    prompt = build_system_prompt(State.PARALLEL)
    must_contain = [
        "risk_signal", "env_constraint",           # 트리거 분류
        "R20", "R21",                              # 규칙 번호
        "지켜보자고 미루지 말고",                    # R20 vs R15 구분 핵심
        "디폴트 베이스",                             # R21 핵심
        "G4", "G5",                                 # 골든 레퍼런스 인용 여부
        "무릎",                                      # G4 원문 근거
        "로드사이클",                                # G5 원문 근거
    ]
    missing = [kw for kw in must_contain if kw not in prompt]
    if missing:
        failures.append(f"PARALLEL 프롬프트에 누락된 필수 문구: {missing}")
    else:
        print(f"  OK: PARALLEL 프롬프트에 필수 문구 {len(must_contain)}개 모두 포함")

    # 4) ACTIVE 등 다른 상태에는 R20/R21 블록이 섞여 들어가지 않는지 (상태별 분리 확인)
    other_prompt = build_system_prompt(State.ACTIVE)
    if "risk_signal" in other_prompt or "env_constraint" in other_prompt:
        failures.append("ACTIVE 프롬프트에 PARALLEL 전용 트리거 지침이 새어 들어감")
    else:
        print("  OK: ACTIVE 프롬프트에는 PARALLEL 트리거 지침이 섞이지 않음")

    print()
    if failures:
        print("  ✗ 실패:")
        for f in failures:
            print(f"    - {f}")
        raise AssertionError(f"{len(failures)}건 실패")
    print("  ✓ 전체 통과")


test_r20_r21()


# ----------------------------------------------------------------------
# 회귀 테스트: 대화 트리거 → 코어 피드백 루프 (R20/R21 조기 인정 경로)
# 검증할 것:
#   1) 말만으로는 상태가 안 바뀐다 (gym_sessions==0인데 trigger만 있는 경우)
#   2) trigger + 이번 주 헬스 활동이 함께 있으면 기준선 미달이어도 조기 ACTIVE 전환
#   3) source가 "log+conversation"으로 정확히 기록되는지
#   4) 키워드 폴백 분류기가 G4/G5 원문 계열 발화를 올바르게 분류하는지
#   5) LLM 태그 우선 / 태그 없으면 키워드 폴백으로 떨어지는지 (build_conv_signal)
# ----------------------------------------------------------------------
def test_conversation_feedback_loop():
    from judgment_core import ConversationSignal, classify_parallel_trigger
    from dialogue_layer import build_conv_signal

    print("\n=== 회귀 테스트: 대화 트리거 피드백 루프 (R20/R21) ===")
    failures = []

    # 준비: PARALLEL 상태까지 진입시킨 코치를 하나 만든다
    def make_parallel_coach():
        sig = weekly_signals(make_log_failover())
        det = detect_passion_decay(sig)
        coach = PersistenceCoach()
        i = 0
        for w, d in zip(sig, det):
            coach.step(w, d)
            i += 1
            if coach.state == State.PARALLEL:
                break
        return coach, sig, det, i  # i = 다음에 넣을 주차 인덱스

    # 1) 말만 있고 이번 주 헬스 활동이 0이면 상태 유지되어야 함
    coach, sig, det, i = make_parallel_coach()
    fake_week = WeekSignals(week=sig[i].week, gym_sessions=0, alt_sessions=1,
                            avg_duration=0.0, diversity=0.0)
    fake_det = Detection(week=fake_week.week, passion_decay=False, reasons=[],
                         trend_diversity=0, trend_duration=0)
    conv = ConversationSignal(trigger="risk_signal", source="llm")
    st = coach.step(fake_week, fake_det, conv=conv)
    if st != State.PARALLEL:
        failures.append(f"말만으로 상태가 바뀜(안 되어야 함): {st}")
    else:
        print("  OK: gym_sessions=0이면 트리거만으론 전이 안 됨 (말만으론 안 바뀜)")

    # 2) trigger + 이번 주 헬스 활동(최소 1회) → 기준선 미달이어도 조기 ACTIVE
    coach, sig, det, i = make_parallel_coach()
    fake_week = WeekSignals(week=sig[i].week, gym_sessions=1, alt_sessions=0,
                            avg_duration=20.0, diversity=1.0)  # 기준선(80%)엔 한참 못 미침
    fake_det = Detection(week=fake_week.week, passion_decay=False, reasons=[],
                         trend_diversity=0, trend_duration=0)
    conv = ConversationSignal(trigger="env_constraint", source="llm")
    st = coach.step(fake_week, fake_det, conv=conv)
    if st != State.ACTIVE:
        failures.append(f"trigger+헬스활동인데 조기 전환 안 됨: {st}")
    else:
        last = coach.history[-1]
        if last.source != "log+conversation":
            failures.append(f"조기 전환 source 표기 오류: {last.source}")
        else:
            print("  OK: trigger + 헬스 활동 1회 → 기준선 미달이어도 조기 ACTIVE, source='log+conversation'")

    # 3) 키워드 폴백 분류기 — G4/G5 원문 계열
    cases = [
        ("요즘 배드민턴 치는데 무릎이 좀 안 좋아진 것 같아요", "risk_signal"),
        ("요즘 비도 오고 너무 더워서 로드사이클을 통 못 타요", "env_constraint"),
        ("오늘 저녁 뭐 먹지", None),
    ]
    for text, expected in cases:
        result = classify_parallel_trigger(text).trigger
        if result != expected:
            failures.append(f"키워드 폴백 오분류: '{text}' → {result} (기대: {expected})")
    if not any("키워드 폴백 오분류" in f for f in failures):
        print(f"  OK: 키워드 폴백 분류기 {len(cases)}개 케이스 모두 정확")

    # 4) build_conv_signal — LLM 태그 우선, 없으면 키워드 폴백
    sig1 = build_conv_signal("아무 발화", "[[TRIGGER:risk_signal]]\n무리하지 마세요.")
    sig2 = build_conv_signal("무릎이 아파요", "[[TRIGGER:none]]\n그렇군요.")  # 태그 실패 케이스
    if sig1.trigger != "risk_signal" or sig1.source != "llm":
        failures.append(f"LLM 태그 우선 처리 실패: {sig1}")
    if sig2.trigger != "risk_signal" or sig2.source != "keyword_fallback":
        failures.append(f"LLM 태그 실패 시 키워드 폴백 미작동: {sig2}")
    if sig1.trigger == "risk_signal" and sig2.source == "keyword_fallback":
        print("  OK: build_conv_signal — LLM 태그 우선, 실패 시 키워드 폴백으로 안전하게 하강")

    print()
    if failures:
        print("  ✗ 실패:")
        for f in failures:
            print(f"    - {f}")
        raise AssertionError(f"{len(failures)}건 실패")
    print("  ✓ 전체 통과")


test_conversation_feedback_loop()


# ----------------------------------------------------------------------
# 회귀 테스트: 실데이터 어댑터 (data_adapter.py)
# 검증할 것:
#   1) 날짜→주차 변환이 정확한가 (7일 = 1주, 시작일 기준)
#   2) CSV의 kind별(gym/alt) 세션이 올바르게 Session으로 변환되는가
#   3) 같은 주에 risk_signal과 env_constraint가 섞이면 risk_signal이 우선되는가
#   4) 어댑터로 읽은 데이터가 실제로 judgment_core 파이프라인을 끝까지 통과하는가
# ----------------------------------------------------------------------
def test_data_adapter():
    import json
    from datetime import date as Date
    from data_adapter import week_of, CSVAdapter, ConversationLogAdapter, run_pipeline

    print("\n=== 회귀 테스트: 실데이터 어댑터 ===")
    failures = []

    start = Date(2026, 1, 5)  # 월요일이라 가정

    # 1) 날짜 → 주차
    cases = [(Date(2026, 1, 5), 1), (Date(2026, 1, 11), 1), (Date(2026, 1, 12), 2),
             (Date(2026, 1, 19), 3)]
    for d, expected in cases:
        got = week_of(d, start)
        if got != expected:
            failures.append(f"week_of({d}) = {got}, 기대값 {expected}")
    if not any("week_of" in f for f in failures):
        print(f"  OK: 날짜→주차 변환 {len(cases)}개 케이스 모두 정확")

    # 2) CSV 라운드트립
    import tempfile, os
    csv_content = "date,kind,exercises,duration_min\n2026-01-05,gym,스쿼트;벤치,60\n2026-01-12,alt,수영,50\n"
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, encoding="utf-8")
    tmp.write(csv_content); tmp.close()
    sessions = CSVAdapter().load(tmp.name, start_date=start)
    os.unlink(tmp.name)
    if len(sessions) != 2 or sessions[0].kind != "gym" or sessions[1].kind != "alt":
        failures.append(f"CSV 라운드트립 실패: {sessions}")
    else:
        print("  OK: CSV → Session 라운드트립 (kind별 정확히 구분)")

    # 3) 같은 주 risk_signal / env_constraint 충돌 시 risk_signal 우선
    jsonl = (
        '{"date": "2026-01-06", "text": "요즘 비도 오고 너무 더워서 로드사이클을 통 못 타요"}\n'
        '{"date": "2026-01-07", "text": "요즘 배드민턴 치는데 무릎이 좀 안 좋아진 것 같아요"}\n'
    )
    tmp2 = tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False, encoding="utf-8")
    tmp2.write(jsonl); tmp2.close()
    conv = ConversationLogAdapter().load(tmp2.name, start_date=start)
    os.unlink(tmp2.name)
    if conv.get(1) is None or conv[1].trigger != "risk_signal":
        failures.append(f"같은 주 충돌 시 risk_signal 우선 규칙 실패: {conv}")
    else:
        print("  OK: 같은 주 두 트리거 충돌 시 risk_signal이 env_constraint보다 우선")

    # 4) 엔드투엔드: CSV만으로 파이프라인이 끝까지 도는가 (예외 없이)
    p = "example_log.csv"
    from data_adapter import make_example_csv
    make_example_csv(p)
    try:
        coach, sig, det = run_pipeline(p, start_date=start)
        print(f"  OK: 엔드투엔드 파이프라인 정상 실행 (최종 상태: {coach.state.value})")
    except Exception as e:
        failures.append(f"엔드투엔드 파이프라인 실패: {e}")
    finally:
        os.unlink(p)

    print()
    if failures:
        print("  ✗ 실패:")
        for f in failures:
            print(f"    - {f}")
        raise AssertionError(f"{len(failures)}건 실패")
    print("  ✓ 전체 통과")


test_data_adapter()
