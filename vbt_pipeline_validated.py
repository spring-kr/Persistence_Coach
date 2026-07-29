# -*- coding: utf-8 -*-
"""
VBT 분석 파이프라인 — 합성 데이터 검증 완료 버전 (v4)
검증 결과 요약:
  - 렙 분할: 5/5, 3/3 (pause squat 1.5s 정지 오인 없음)
  - MCV 오차 ±5% 이내, velocity loss GT 44.9% vs est 46.4%
  - 스티킹 포인트 위치 오차 ±4%pt (그라인더 렙 포함)
알려진 한계:
  - peak_v는 노이즈로 +5~16% 과대추정 경향 → 세션 간 '상대 비교'로만 사용
  - 트래커 지터 요구 스펙: ≤1px (2px에서 VL p95 노이즈 ±10.7%)
입력: 트래커가 뽑은 바 중심 y좌표(px) 시퀀스 + fps + 캘리브레이션 계수
"""
import numpy as np
from scipy.signal import savgol_filter, find_peaks


def find_sticking(v_seg, disp_seg, prominence=0.05):
    """컨센트릭 속도 곡선에서 prominence 최대 계곡 = 스티킹 포인트.
    계곡이 없으면 None (스티킹 없는 깨끗한 렙)."""
    n = len(v_seg)
    lo, hi = int(0.10 * n), int(0.90 * n)   # 경계 10% 제외 (렙 시작/종료 아티팩트)
    valleys, props = find_peaks(-v_seg[lo:hi], prominence=prominence)
    if len(valleys) == 0:
        return None
    i_min = lo + valleys[np.argmax(props["prominences"])]
    return {
        "min_v": float(v_seg[i_min]),
        "sticking_pos_pct": float(disp_seg[i_min] / disp_seg[-1] * 100),
        "idx": int(i_min),
    }


def analyze_bar_path(y_px, fps, m_per_px,
                     sg_window=15, sg_poly=3,
                     v_start_thresh=0.05, min_con_dur=0.3, min_rom=0.2):
    """
    y_px: 바 중심 y좌표 (px, 화면 아래가 + 인 경우 호출 전에 부호 반전할 것)
    반환: (y_smooth, velocity, rep_bounds, per_rep_metrics, set_metrics)
    """
    y_m = np.asarray(y_px, dtype=float) * m_per_px
    y_s = savgol_filter(y_m, sg_window, sg_poly)
    v = savgol_filter(y_m, sg_window, sg_poly, deriv=1, delta=1.0 / fps)

    # --- 렙 분할: 양의 속도 지속 구간 + 최소 지속시간/ROM 필터 ---
    reps = []
    i, n = 0, len(v)
    while i < n:
        if v[i] > v_start_thresh:
            j = i
            while j < n and v[j] > 0:
                j += 1
            dur = (j - i) / fps
            rom = y_s[j - 1] - y_s[i]
            if dur >= min_con_dur and rom >= min_rom:
                reps.append((i, j))
            i = j
        else:
            i += 1

    # --- 렙별 지표 ---
    per_rep = []
    for (a, b) in reps:
        seg_v = v[a:b]
        disp = y_s[a:b] - y_s[a]
        peak = savgol_filter(seg_v, 9, 2).max() if len(seg_v) >= 9 else seg_v.max()
        per_rep.append({
            "mcv": float(seg_v.mean()),
            "peak_v": float(peak),
            "con_duration_s": (b - a) / fps,
            "rom_m": float(disp[-1]),
            "sticking": find_sticking(seg_v, disp),
        })

    # --- 세트 지표 ---
    set_metrics = {}
    if len(per_rep) >= 2:
        set_metrics["velocity_loss_pct"] = float(
            (1 - per_rep[-1]["mcv"] / per_rep[0]["mcv"]) * 100)
        # 노이즈 강건 대안: 렙별 MCV에 선형 회귀 → 기울기 기반 VL
        mcvs = np.array([r["mcv"] for r in per_rep])
        x = np.arange(len(mcvs))
        slope = np.polyfit(x, mcvs, 1)[0]
        set_metrics["velocity_loss_trend_pct"] = float(
            -slope * (len(mcvs) - 1) / mcvs[0] * 100)
    return y_s, v, reps, per_rep, set_metrics


def calibrate_from_plate(radius_px, plate_diameter_m=0.45):
    """원판 검출 반지름(px) → 미터/픽셀 변환계수"""
    return plate_diameter_m / (2 * radius_px)
