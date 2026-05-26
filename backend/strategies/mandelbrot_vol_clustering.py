"""
Mandelbrotian Vol Clustering Strategy
Conditions classical technical signals on fractal + tail-risk regime.
Symbols: GOOGL, TSLA, NVDA, AAPL, AMZN, META, MSFT (large-cap tech)
"""
import numpy as np
import pandas as pd

IS_ROTATION = False


# ──────────────────────────────────────────────
# Fractal helpers
# ──────────────────────────────────────────────

def _hurst_rs(arr: np.ndarray) -> float:
    """R/S multi-scale Hurst exponent, clamped to [0.1, 0.9]."""
    n = len(arr)
    if n < 16:
        return 0.5
    returns = np.diff(np.log(np.maximum(arr, 1e-8)))
    chunk_sizes, rs_vals = [], []
    size = 8
    while size <= n // 2:
        chunks = [returns[i:i + size] for i in range(0, len(returns) - size + 1, size)]
        rs_list = []
        for ch in chunks:
            mean = np.mean(ch)
            cum = np.cumsum(ch - mean)
            R = np.max(cum) - np.min(cum)
            S = np.std(ch, ddof=1)
            if S > 1e-10 and R > 0:
                rs_list.append(R / S)
        if rs_list:
            chunk_sizes.append(np.log(size))
            rs_vals.append(np.log(np.mean(rs_list)))
        size *= 2
    if len(chunk_sizes) < 2:
        return 0.5
    h, _ = np.polyfit(chunk_sizes, rs_vals, 1)
    return float(np.clip(h, 0.1, 0.9))


def _tail_index(returns: np.ndarray, k_frac: float = 0.10) -> float:
    """Hill estimator for Pareto tail index alpha (lower = fatter tails)."""
    n = len(returns)
    if n < 20:
        return 3.0
    abs_r = np.sort(np.abs(returns))[::-1]
    k = max(3, int(n * k_frac))
    if k >= n:
        return 3.0
    thresh = abs_r[k]
    if thresh < 1e-10:
        return 3.0
    log_ratios = np.log(np.maximum(abs_r[:k] / thresh, 1e-10))
    total = np.sum(log_ratios)
    return float(np.clip(k / total if total > 1e-10 else 3.0, 0.5, 10.0))


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(com=period - 1, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(com=period - 1, min_periods=period).mean()
    rs = gain / loss.replace(0, 1e-8)
    return 100 - 100 / (1 + rs)


# ──────────────────────────────────────────────
# Feature computation
# ──────────────────────────────────────────────

def _compute_features(ohlcv: pd.DataFrame, params: dict, i: int) -> dict | None:
    rsi_p  = int(params.get('rsi_period', 14))
    bb_p   = int(params.get('bb_period', 20))
    bb_std = float(params.get('bb_std', 2.0))
    mf     = int(params.get('macd_fast', 12))
    ms     = int(params.get('macd_slow', 26))
    msig   = int(params.get('macd_signal', 9))
    sma_p  = int(params.get('sma_period', 50))
    vol_lb = int(params.get('vol_lookback', 20))
    h_s    = int(params.get('hurst_short', 20))
    h_m    = int(params.get('hurst_med', 60))
    h_l    = int(params.get('hurst_long', 120))
    tail_lb = int(params.get('tail_lookback', 100))

    min_req = max(ms + msig, sma_p, h_l, 52)
    start = max(0, i + 1 - min_req - 10)
    seg = ohlcv.iloc[start:i + 1]
    if len(seg) < min_req:
        return None

    close = seg['close']
    high  = seg['high']
    low   = seg['low']
    volume = seg['volume']
    c = close.values
    n = len(c)

    returns = np.diff(np.log(np.maximum(c, 1e-8)))

    # ── Hurst at 3 scales
    h_short = _hurst_rs(c[-h_s:]) if n >= h_s else 0.5
    h_med   = _hurst_rs(c[-h_m:]) if n >= h_m else 0.5
    h_long  = _hurst_rs(c[-h_l:]) if n >= h_l else 0.5
    mf_width = float(np.std([h_short, h_med, h_long]))

    # ── Tail index
    tail_n = min(tail_lb, len(returns))
    tail_idx = _tail_index(returns[-tail_n:]) if tail_n >= 20 else 3.0

    # ── Realized vol
    rv = float(np.std(returns[-vol_lb:]) * np.sqrt(252)) if len(returns) >= vol_lb else 0.2
    bv = float(np.std(returns) * np.sqrt(252)) if len(returns) >= 10 else 0.2

    # ── Danger score: fat-tail + vol spike
    danger_tail = max(0.0, (3.0 - tail_idx) / 2.5)
    danger_vol  = max(0.0, (rv / (bv + 1e-8) - 1.5) / 2.0)
    danger = float(np.clip(danger_tail * 0.6 + danger_vol * 0.4, 0.0, 1.0))

    # ── Technical indicators
    s = pd.Series(c)
    rsi_val = float(_rsi(s, rsi_p).iloc[-1])
    if np.isnan(rsi_val):
        rsi_val = 50.0

    bb_mean = s.rolling(bb_p).mean()
    bb_band = s.rolling(bb_p).std()
    bb_up   = bb_mean + bb_std * bb_band
    bb_lo   = bb_mean - bb_std * bb_band
    bb_pctb = float(((s - bb_lo) / (bb_up - bb_lo + 1e-8)).iloc[-1])
    if np.isnan(bb_pctb):
        bb_pctb = 0.5

    ema_f  = s.ewm(span=mf, adjust=False).mean()
    ema_sl = s.ewm(span=ms, adjust=False).mean()
    macd_line = ema_f - ema_sl
    macd_sig_line = macd_line.ewm(span=msig, adjust=False).mean()
    macd_hist = float((macd_line - macd_sig_line).iloc[-1])

    sma = s.rolling(sma_p).mean()
    above_sma = int(c[-1] > sma.iloc[-1]) if not np.isnan(sma.iloc[-1]) else 0
    sma_trend = int(len(sma.dropna()) >= 2 and sma.iloc[-1] > sma.iloc[-2])

    # ── Volume ratio
    v = pd.Series(volume.values)
    v_sma = v.rolling(vol_lb).mean()
    vol_ratio = float(v.iloc[-1] / v_sma.iloc[-1]) if v_sma.iloc[-1] > 0 else 1.0

    return {
        'close': float(c[-1]),
        'rsi': rsi_val, 'bb_pctb': bb_pctb, 'macd_hist': macd_hist,
        'above_sma50': above_sma, 'sma_trend': sma_trend,
        'realized_vol': rv, 'baseline_vol': bv, 'vol_ratio': vol_ratio,
        'hurst_short': h_short, 'hurst_med': h_med, 'hurst_long': h_long,
        'hurst_divergence': h_short - h_long, 'mf_width': mf_width,
        'tail_index': tail_idx, 'danger_score': danger,
    }


# ──────────────────────────────────────────────
# Regime classification
# ──────────────────────────────────────────────

def _classify_regime(feat: dict) -> tuple[int, float]:
    """
    0 trending-up  1 trending-down  2 mean-reverting
    3 elevated-risk  4 crisis
    """
    h_long  = feat['hurst_long']
    tail    = feat['tail_index']
    danger  = feat['danger_score']
    above   = feat['above_sma50']
    s_trend = feat['sma_trend']
    rv, bv  = feat['realized_vol'], feat['baseline_vol']

    if (tail < 1.5 and danger > 0.65) or danger > 0.80:
        return 4, danger
    if tail < 2.0 or (bv > 0 and rv > bv * 2.0):
        return 3, danger
    if h_long > 0.58:
        if above and s_trend:
            return 0, danger
        if not above and not s_trend:
            return 1, danger
    if h_long < 0.45:
        return 2, danger
    return 2, danger


# ──────────────────────────────────────────────
# Signal generation
# ──────────────────────────────────────────────

def _generate_signal(feat: dict, regime: int, danger: float, params: dict) -> dict:
    rsi_os    = float(params.get('rsi_oversold', 40))
    rsi_ob    = float(params.get('rsi_overbought', 60))
    mr_os     = float(params.get('rsi_mr_oversold', 35))
    mr_ob     = float(params.get('rsi_mr_overbought', 65))
    min_str   = float(params.get('min_signal_strength', 0.30))

    rsi, bb, mh = feat['rsi'], feat['bb_pctb'], feat['macd_hist']
    h_short, h_long = feat['hurst_short'], feat['hurst_long']
    tail = feat['tail_index']

    h_conf      = abs(h_long - 0.5) * 2.0
    vol_misprice = max(0.0, (4.0 - tail) / 3.5)

    direction, strength, reason = 0, 0.0, "none"

    if regime == 4:
        pass
    elif regime == 0:  # trending up: pullback or continuation
        if rsi < rsi_os and mh > 0:
            direction = 1
            strength = (rsi_os - rsi) / rsi_os * 0.5 + h_conf * 0.3 + vol_misprice * 0.2
            reason = "trend_pullback_long"
        elif rsi > 45 and mh > 0 and bb > 0.5:
            direction = 1
            strength = (bb - 0.5) * 0.6 + h_conf * 0.4
            reason = "trend_continuation_long"
    elif regime == 1:  # trending down
        if rsi > rsi_ob and mh < 0:
            direction = -1
            strength = (rsi - rsi_ob) / (100 - rsi_ob) * 0.5 + h_conf * 0.3 + vol_misprice * 0.2
            reason = "trend_down_short"
        elif rsi < 55 and mh < 0 and bb < 0.5:
            direction = -1
            strength = (0.5 - bb) * 0.6 + h_conf * 0.4
            reason = "trend_continuation_short"
    elif regime == 2:  # mean reverting
        if bb < 0.15 and rsi < mr_os:
            direction = 1
            strength = (0.2 - bb) * 1.5 + (mr_os - rsi) / mr_os * 0.5
            reason = "mr_oversold_long"
        elif bb > 0.85 and rsi > mr_ob:
            direction = -1
            strength = (bb - 0.8) * 1.5 + (rsi - mr_ob) / (100 - mr_ob) * 0.5
            reason = "mr_overbought_short"
    elif regime == 3 and bb < 0.10 and rsi < mr_os - 5 and h_short < 0.45:
        direction = 1
        strength = 0.30
        reason = "elevated_risk_mr_long"

    if direction != 0:
        strength = float(np.clip(strength * (0.7 + h_conf * 0.3), 0.0, 1.0))
        if strength < min_str:
            direction, strength, reason = 0, 0.0, "below_min_strength"

    return {'direction': direction, 'strength': strength, 'reason': reason,
            'regime': regime, 'danger_score': danger}


# ──────────────────────────────────────────────
# Backtest entry point
# ──────────────────────────────────────────────

def generate_signals(ohlcv: pd.DataFrame, params: dict) -> pd.Series:
    signals = pd.Series(0, index=ohlcv.index, dtype=int)

    stop_loss  = float(params.get('stop_loss_pct', 0.08))
    take_profit = float(params.get('take_profit_pct', 0.25))
    holding_p  = int(params.get('holding_period', 20))

    min_bars = max(
        int(params.get('macd_slow', 26)) + int(params.get('macd_signal', 9)),
        int(params.get('sma_period', 50)),
        int(params.get('hurst_long', 120)),
        52,
    )

    in_pos = False
    entry_price = 0.0
    entry_bar = 0
    pos_dir = 0

    for i in range(min_bars, len(ohlcv)):
        close = ohlcv['close'].iloc[i]

        if in_pos:
            pnl = (close - entry_price) / entry_price * pos_dir
            held = i - entry_bar
            if pnl < -stop_loss or pnl > take_profit or held >= holding_p:
                signals.iloc[i] = -pos_dir
                in_pos = False
                pos_dir = 0
                continue
            continue  # stay in position, no new entry

        feat = _compute_features(ohlcv, params, i)
        if feat is None:
            continue
        regime, danger = _classify_regime(feat)
        sig = _generate_signal(feat, regime, danger, params)

        if sig['direction'] != 0:
            signals.iloc[i] = sig['direction']
            in_pos = True
            entry_price = close
            entry_bar = i
            pos_dir = sig['direction']

    return signals
