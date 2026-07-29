# -*- coding: utf-8 -*-
"""
실데이터 연결 어댑터 v0.1

문제: judgment_core.py는 week/day 정수 기반 Session만 받는다 (합성 로그·테스트엔
편하지만 실제 기록은 달력 날짜로 쌓인다). 그리고 대화 로그(리스크/환경 트리거)는
운동 로그와 아예 다른 소스에서 온다 — 이 둘을 한 파이프라인으로 합치는 게 이 파일의 일.

설계 원칙 (기존 아키텍처와 동일):
  - 이 파일은 '변환'만 한다. 판단 로직은 여전히 judgment_core.py가 갖는다.
  - 어댑터는 여러 개일 수 있다 (CSVAdapter가 1호). 공통 인터페이스만 지키면
    나중에 실제로 쓰는 앱(네이버 블로그 API, 스레드 DM 등)에 맞춘 어댑터를 더 붙이면 된다.

CSV 스키마 (최소):
  date,kind,exercises,duration_min
  2026-01-05,gym,스쿼트;벤치;데드,75
  2026-01-06,alt,수영,60
  2026-01-08,gym,OHP;로우,50

대화 로그 스키마 (최소, JSONL 한 줄에 한 발화):
  {"date": "2026-01-10", "text": "요즘 배드민턴 치는데 무릎이 좀 안 좋아진 것 같아요"}
"""
import csv
import json
from dataclasses import dataclass
from datetime import date as Date, datetime
from judgment_core import Session, ConversationSignal, classify_parallel_trigger


def week_of(d: Date, start: Date) -> int:
    """달력 날짜를 judgment_core 기준 '몇 주차'로 변환. start = 트래킹 시작일(1주차 월요일 등)."""
    if d < start:
        raise ValueError(f"{d}가 시작일({start})보다 이릅니다 — start를 확인하세요")
    return (d - start).days // 7 + 1


def _parse_date(s: str) -> Date:
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


class CSVAdapter:
    """가장 흔한 실데이터 형태: 운동 앱/스프레드시트에서 내보낸 CSV.
    date,kind,exercises,duration_min 4개 컬럼만 있으면 된다."""

    REQUIRED_COLUMNS = {"date", "kind", "exercises", "duration_min"}

    def load(self, path: str, start_date: Date) -> list[Session]:
        sessions = []
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            missing = self.REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"CSV에 필수 컬럼 누락: {missing}")
            day_counter = {}  # week -> 그 주 몇 번째 세션인지 (Session.day 채우기용)
            for row in reader:
                d = _parse_date(row["date"])
                wk = week_of(d, start_date)
                day_counter[wk] = day_counter.get(wk, -1) + 1
                exercises = [e.strip() for e in row["exercises"].split(";") if e.strip()]
                sessions.append(Session(
                    week=wk,
                    day=day_counter[wk],
                    exercises=exercises,
                    duration_min=float(row["duration_min"]),
                    kind=row["kind"].strip() or "gym",
                ))
        return sessions


class ConversationLogAdapter:
    """대화 로그(JSONL) → (week, ConversationSignal) 리스트.
    R20/R21 피드백 루프에 넣을 conv_trigger를 실제 대화 기록에서 뽑아낸다.
    LLM 태그가 없는 과거 로그(순수 텍스트)를 다루는 상황을 가정 — 키워드 폴백 분류기를 쓴다.
    LLM이 실시간으로 [[TRIGGER:...]]를 남긴 최신 로그가 있다면
    dialogue_layer.build_conv_signal()을 우선 쓰는 게 더 정확하다."""

    def load(self, path: str, start_date: Date) -> dict[int, ConversationSignal]:
        """주(week) → 그 주에 감지된 트리거(가장 강한 신호 하나). 여러 발화 중
        risk_signal이 있으면 risk_signal을 우선한다(더 즉각 대응이 필요한 신호이므로)."""
        by_week: dict[int, ConversationSignal] = {}
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                d = _parse_date(rec["date"])
                wk = week_of(d, start_date)
                sig = classify_parallel_trigger(rec["text"])
                if sig.trigger is None:
                    continue
                prev = by_week.get(wk)
                if prev is None or (prev.trigger != "risk_signal" and sig.trigger == "risk_signal"):
                    by_week[wk] = sig
        return by_week


def make_example_csv(path: str = "example_log.csv"):
    """빈손으로 시작하는 사람을 위한 예시 CSV 생성 (형식 확인용)."""
    rows = [
        ("2026-01-05", "gym", "스쿼트;벤치;데드", "75"),
        ("2026-01-07", "gym", "OHP;로우;풀업", "70"),
        ("2026-01-12", "alt", "수영", "60"),
        ("2026-01-14", "gym", "스쿼트;벤치", "45"),
    ]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date", "kind", "exercises", "duration_min"])
        w.writerows(rows)
    return path


def run_pipeline(csv_path: str, start_date: Date, conv_log_path: str | None = None):
    """실데이터 엔드투엔드: CSV(+대화로그) → judgment_core 전체 판단 결과.
    합성 로그 대신 이 함수를 쓰면 validate_core.py의 run()과 동일한 판단 파이프라인을
    실제 기록에 그대로 적용할 수 있다."""
    from judgment_core import weekly_signals, detect_passion_decay, PersistenceCoach

    sessions = CSVAdapter().load(csv_path, start_date)
    conv_by_week = ConversationLogAdapter().load(conv_log_path, start_date) if conv_log_path else {}

    sig = weekly_signals(sessions)
    det = detect_passion_decay(sig)
    coach = PersistenceCoach()
    for w, d in zip(sig, det):
        coach.step(w, d, conv=conv_by_week.get(w.week))
    return coach, sig, det


if __name__ == "__main__":
    p = make_example_csv()
    sessions = CSVAdapter().load(p, start_date=Date(2026, 1, 5))
    print(f"예시 CSV → Session {len(sessions)}건 로드:")
    for s in sessions:
        print(f"  주{s.week} day{s.day}: {s.exercises} ({s.duration_min}분, {s.kind})")

    coach, sig, det = run_pipeline(p, start_date=Date(2026, 1, 5))
    print(f"\n엔드투엔드 파이프라인 결과: 최종 상태 = {coach.state.value}")
    for t in coach.history:
        print(f"  {t.week}주: {t.from_state.value} → {t.to_state.value} | {t.trigger}")
