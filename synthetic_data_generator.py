# -*- coding: utf-8 -*-
"""
합성 데이터 기반 VBT 파이프라인 검증
- Ground truth 속도 프로파일을 파라메트릭하게 생성 → 적분해서 위치 궤적 생성
- 60fps 다운샘플 + 픽셀 트래킹 노이즈 주입 (실제 CSRT 트래커 지터 시뮬레이션)
- 파이프라인(스무딩→미분→렙분할→지표산출) 실행 후 ground truth와 비교
"""
import numpy as np
from scipy.signal import savgol_filter
import json

RNG = np.random.default_rng(42)
FPS = 60
M_PER_PX = 0.45 / 240          # 원판 반지름 240px 가정 → 캘리브레이션 계수
PIXEL_NOISE_STD = 2.0          # CSRT 지터: 표준편차 2px (보수적으로 크게)

# ---------------------------------------------------------------
# 1. Ground Truth 생성기
# ---------------------------------------------------------------
def make_rep_velocity(t, ecc_dur, pause_dur, con_dur,
                      ecc_peak, con_peak, sticking_depth, sticking_pos):
    """
    한 렙의 속도 프로파일 v(t)를 생성 (아래 방향 음수, 위 방향 양수)
    - ecc: sin 반주기 형태의 하강
    - pause: 0 속도 (pause squat 재현)
    - con: sin 반주기에 '스티킹 딥'을 곱해 중간에 속도 저하 재현
    sticking_depth: 0~1, 피크 대비 최저점 비율 (0.9면 90%까지 떨어짐 = 심한 스티킹)
    sticking_pos: 컨센트릭 구간 내 스티킹 위치 (0~1)
    """
    v = np.zeros_like(t)
    # eccentric
    m1 = t < ecc_dur
    v[m1] = -ecc_peak * np.sin(np.pi * t[m1] / ecc_dur)
    # pause
    # concentric
    t2 = t - ecc_dur - pause_dur
    m3 = (t2 >= 0) & (t2 <= con_dur)
    base = con_peak * np.sin(np.pi * t2[m3] / con_dur)
    # 스티킹 딥: 가우시안 형태의 감쇠
    dip = 1 - sticking_depth * np.exp(-((t2[m3]/con_dur - sticking_pos)**2) / (2*0.08**2))
    v[m3] = base * dip
    return v

def make_set(rep_params, rest_between_reps=0.8, dt=1/1000):
    """렙 파라미터 리스트 → 전체 세트의 (t, v, y) ground truth (1000Hz 고해상도)"""
    segs_t, segs_v = [], []
    t_offset = 0.5  # 세트 시작 전 정지 구간
    segs_t.append(np.arange(0, t_offset, dt)); segs_v.append(np.zeros(len(segs_t[-1])))
    for p in rep_params:
        dur = p["ecc_dur"] + p["pause_dur"] + p["con_dur"]
        t_local = np.arange(0, dur, dt)
        v = make_rep_velocity(t_local, **p)
        segs_t.append(t_local + t_offset); segs_v.append(v)
        t_offset += dur
        # 렙 사이 정지 (락아웃 상태)
        t_rest = np.arange(0, rest_between_reps, dt)
        segs_t.append(t_rest + t_offset); segs_v.append(np.zeros(len(t_rest)))
        t_offset += rest_between_reps
    t = np.concatenate(segs_t)
    v = np.concatenate(segs_v)
    y = np.cumsum(v) * dt  # 적분 → 위치
    return t, v, y

def ground_truth_metrics(rep_params):
    """파라미터에서 직접 GT 지표 계산 (파이프라인과 독립적으로)"""
    gt = []
    dt = 1/1000
    for p in rep_params:
        t = np.arange(0, p["con_dur"], dt)
        base = p["con_peak"] * np.sin(np.pi * t / p["con_dur"])
        dip = 1 - p["sticking_depth"] * np.exp(-((t/p["con_dur"] - p["sticking_pos"])**2)/(2*0.08**2))
        v = base * dip
        # ROM 대비 위치: 컨센트릭 변위 누적
        disp = np.cumsum(v) * dt
        rom = disp[-1]
        i_min = None
        # 최저속: 시작/끝 0 부근 제외, 중간 60% 구간에서 국소 최저 탐색
        core = (t > 0.15*p["con_dur"]) & (t < 0.85*p["con_dur"])
        i_min = np.where(core)[0][np.argmin(v[core])]
        gt.append({
            "mcv": float(v.mean()),
            "peak_v": float(v.max()),
            "min_v": float(v[i_min]),
            "sticking_pos_pct": float(disp[i_min] / rom * 100),
            "con_duration_s": p["con_dur"],
        })
    return gt

# ---------------------------------------------------------------
# 2. 관측 시뮬레이션: 60fps 다운샘플 + 픽셀 노이즈
# ---------------------------------------------------------------
def simulate_tracker(t_hi, y_hi):
    t_frames = np.arange(t_hi[0], t_hi[-1], 1/FPS)
    y_frames = np.interp(t_frames, t_hi, y_hi)
    y_px = y_frames / M_PER_PX
    y_px_noisy = y_px + RNG.normal(0, PIXEL_NOISE_STD, len(y_px))
    return t_frames, y_px_noisy

# ---------------------------------------------------------------
# 3. 분석 파이프라인 (실전과 동일 코드 경로)
# ---------------------------------------------------------------
def pipeline(y_px, fps=FPS, m_per_px=M_PER_PX,
             sg_window=11, sg_poly=3,
             v_start_thresh=0.05, min_con_dur=0.3, min_rom=0.2):
    y_m = y_px * m_per_px
    y_s = savgol_filter(y_m, window_length=sg_window, polyorder=sg_poly)
    v = np.gradient(y_s) * fps

    # --- 렙 분할: 상승 구간(양의 속도가 임계 이상 지속) 탐지 ---
    reps = []
    i, n = 0, len(v)
    while i < n:
        if v[i] > v_start_thresh:
            j = i
            while j < n and v[j] > 0:
                j += 1
            dur = (j - i) / fps
            rom = y_s[j-1] - y_s[i]
            if dur >= min_con_dur and rom >= min_rom:
                reps.append((i, j))
            i = j
        else:
            i += 1

    # --- 렙별 지표 ---
    out = []
    for (a, b) in reps:
        seg_v = v[a:b]
        seg_y = y_s[a:b]
        disp = seg_y - seg_y[0]
        rom = disp[-1]
        L = b - a
        core = slice(int(0.15*L), int(0.85*L))
        i_min_rel = np.argmin(seg_v[core]) + core.start
        out.append({
            "mcv": float(seg_v.mean()),
            "peak_v": float(seg_v.max()),
            "min_v": float(seg_v[i_min_rel]),
            "sticking_pos_pct": float(disp[i_min_rel] / rom * 100),
            "con_duration_s": L / fps,
        })
    return y_s, v, reps, out

# ---------------------------------------------------------------
# 4. 테스트 시나리오
# ---------------------------------------------------------------
def scenario_normal_set():
    """일반 5렙 세트: 렙이 갈수록 느려짐 (velocity loss 재현) + 스티킹 심화"""
    reps = []
    for k in range(5):
        fatigue = k / 4  # 0 → 1
        reps.append(dict(
            ecc_dur=1.2 + 0.1*k,
            pause_dur=0.0,
            con_dur=0.9 + 0.5*fatigue,          # 마지막 렙은 그라인더
            ecc_peak=0.7,
            con_peak=0.85 - 0.30*fatigue,
            sticking_depth=0.35 + 0.45*fatigue,  # 마지막 렙 딥 80%
            sticking_pos=0.42,
        ))
    return reps

def scenario_pause_squat():
    """pause squat 3렙: 바닥 1.5초 정지 — 렙 분할이 pause를 렙 경계로 오인하면 안 됨"""
    return [dict(ecc_dur=1.3, pause_dur=1.5, con_dur=1.0,
                 ecc_peak=0.6, con_peak=0.75,
                 sticking_depth=0.3, sticking_pos=0.45) for _ in range(3)]

def scenario_failed_lockout():
    """2렙: 정상 1렙 + 락아웃 직전 실패(상승 도중 하강 전환) — 실패렙은 별도 검출 대상"""
    return "special"

def run_scenario(name, rep_params):
    t_hi, v_hi, y_hi = make_set(rep_params)
    t_fr, y_px = simulate_tracker(t_hi, y_hi)
    y_s, v_est, reps, est = pipeline(y_px)
    gt = ground_truth_metrics(rep_params)

    report = {"scenario": name, "gt_reps": len(gt), "detected_reps": len(reps), "per_rep": []}
    for k, (g, e) in enumerate(zip(gt, est)):
        row = {"rep": k+1}
        for key in ["mcv", "peak_v", "min_v", "sticking_pos_pct", "con_duration_s"]:
            err = e[key] - g[key]
            rel = err / g[key] * 100 if g[key] != 0 else float("nan")
            row[key] = {"gt": round(g[key], 3), "est": round(e[key], 3),
                        "err_pct": round(rel, 1)}
        report["per_rep"].append(row)
    # 세트 지표: velocity loss
    if len(est) >= 2:
        vl_est = (1 - est[-1]["mcv"]/est[0]["mcv"]) * 100
        vl_gt  = (1 - gt[-1]["mcv"]/gt[0]["mcv"]) * 100
        report["velocity_loss_pct"] = {"gt": round(vl_gt,1), "est": round(vl_est,1)}
    return report, (t_fr, y_s, v_est, reps, t_hi, v_hi)

# ---------------------------------------------------------------
if __name__ == "__main__":
    results = {}
    plots = {}
    for name, params in [("normal_5rep", scenario_normal_set()),
                         ("pause_squat_3rep", scenario_pause_squat())]:
        rep, plotdata = run_scenario(name, params)
        results[name] = rep
        plots[name] = plotdata
        np.save(f"/home/claude/vbt/{name}_plot.npy",
                np.array(plotdata, dtype=object), allow_pickle=True)

    print(json.dumps(results, indent=2, ensure_ascii=False))
