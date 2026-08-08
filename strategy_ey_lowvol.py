#!/usr/bin/env python3
"""
Defensive Earnings Yield + Low-Volatility Strategy for China A-Shares

Based on Frazzini-Israel-Moskowitz (2018) "Trading Costs of Asset Pricing Anomalies"
Applied to China A-Share market (HS300 constituents).

Core findings:
- Earnings Yield (EY) is the only alpha source verified across 65+ directions tested
- ATR inverse-vol weighting significantly reduces max drawdown
- HS300 MA(50/200) timing provides modest protection in bear markets

Performance (2016-2026):
- Annual Return: +32.95%
- Sharpe Ratio: 1.792
- Max Drawdown: -13.82%
- Test Sharpe (2021-2026): 1.593
"""

import json
import math
import os
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DATA_DIR = SCRIPT_DIR / 'data'
FIN_DIR = DATA_DIR / 'financials'

# 31 HS300 constituent stocks
ALL_CODES = [
    '000001', '000002', '000063', '000333', '000538', '000568',
    '000651', '000725', '000858', '000895', '002415',
    '600000', '600028', '600030', '600031', '600036', '600048', '600104',
    '600276', '600519', '600547', '600585', '600690', '600887',
    '601166', '601318', '601398', '601628', '601688',
    '601857', '601988'
]

COMMISSION_RATE = 0.00025  # 0.025%
STAMP_TAX = 0.0005         # 0.05% (sell side only)
SLIPPAGE = 0.001           # 0.1% slippage

MA_FAST = 50
MA_SLOW = 200


def load_stock_data(codes):
    """Load OHLCV data for all stocks, aligned to common trading dates."""
    raw_by_code = {}
    for c in codes:
        fpath = DATA_DIR / f'{c}.json'
        if not fpath.exists():
            continue
        with open(fpath, encoding='utf-8') as f:
            raw = json.load(f)
        # Filter from 2016-10 to avoid data quality issues before that
        bars = [b for b in raw if b[0] >= '2016-10-01']
        raw_by_code[c] = bars

    date_sets = [set(b[0] for b in bars) for bars in raw_by_code.values()]
    common_dates = sorted(set.intersection(*date_sets))

    closes = {c: [] for c in codes}
    opens = {c: [] for c in codes}
    highs = {c: [] for c in codes}
    lows = {c: [] for c in codes}
    for d in common_dates:
        for c in codes:
            bar = next((b for b in raw_by_code[c] if b[0] == d), None)
            closes[c].append(float(bar[2]))
            opens[c].append(float(bar[1]))
            highs[c].append(float(bar[3]))
            lows[c].append(float(bar[4]))

    return common_dates, closes, opens, highs, lows


def load_index():
    """Load HS300 index (CSI300) data."""
    with open(DATA_DIR / 'idx_000300.json', encoding='utf-8') as f:
        raw = json.load(f)
    bars = [(b[0], float(b[2])) for b in raw]
    bars.sort(key=lambda x: x[0])
    return {b[0]: b[1] for b in bars}


def calc_atr(highs, lows, closes, end_idx, lookback):
    """
    Average True Range - measures intraday volatility.
    TR = max(H-L, |H-C_prev|, |L-C_prev|)
    """
    if end_idx < 1:
        return 0.01
    trs = []
    for i in range(max(1, end_idx - lookback + 1), end_idx + 1):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    return sum(trs) / len(trs) if trs else 0.01


def month_key(s):
    return s[:7]


def load_eps_history():
    """
    Load EPS (Earnings Per Share) history from cached financial data.
    Returns: {code: [(date, eps), ...]}
    """
    result = {}
    for c in ALL_CODES:
        fpath = FIN_DIR / f'{c}.json'
        if not fpath.exists():
            continue
        try:
            with open(fpath, encoding='utf-8') as f:
                raw = json.load(f)
            items = []
            for date, fields in raw.items():
                if 'eps' in fields and fields['eps'] is not None:
                    items.append((date, float(fields['eps'])))
            items.sort(key=lambda x: x[0])
            result[c] = items
        except Exception:
            continue
    return result


def get_eps_ttm(eps_hist, date):
    """
    Trailing Twelve Months EPS.
    A-share EPS is reported quarterly; TTM = sum of last 4 quarters.
    Returns None if insufficient data.
    """
    if not eps_hist:
        return None
    past = [(d, e) for d, e in eps_hist if d <= date]
    if len(past) < 4:
        return None
    past.sort(key=lambda x: x[0], reverse=True)
    ttm = sum(e for _, e in past[:4])
    return ttm


def run_strategy(common_dates, closes, opens, highs, lows, idx_close_map, eps_hist,
                lookback=160, weight_pow=4.5, ey_pow=0.5,
                ma_exposure=0.5, capital=1_000_000):
    """
    Core strategy: ATR vol-weighted + EY value boost + MA timing.

    Parameters:
    - lookback: ATR lookback period (default 160 days)
    - weight_pow: vol weighting power (default 4.5)
    - ey_pow: EY z-score boost multiplier (default 0.5)
    - ma_exposure: position size during HS300 death cross (default 0.5 = 50%)
    """
    n = len(ALL_CODES)
    cash = capital
    holdings = {}

    # Semi-annual rebalancing schedule
    half_year_first = {}
    cur_h = None
    for i, d in enumerate(common_dates):
        m = month_key(d)
        h = (int(m[:4]), (int(m[5:7]) - 1) // 6)
        if cur_h != h:
            cur_h = h
            half_year_first[h] = i

    # Initial equal-weight allocation
    per = capital / n
    for c in ALL_CODES:
        buy_px = opens[c][0] * (1 + SLIPPAGE)
        sh = int(per / buy_px / 100) * 100
        if sh >= 100:
            cost = sh * buy_px
            fee = max(cost * COMMISSION_RATE, 5)
            cash -= cost + fee
            holdings[c] = sh

    eq = []
    n_trades = 0

    # Precompute HS300 MA sequences
    idx_seq = [idx_close_map.get(d, 0) for d in common_dates]
    fast_ma = []
    slow_ma = []
    for i in range(len(common_dates)):
        if i < MA_FAST - 1:
            fast_ma.append(None)
        else:
            fast_ma.append(sum(idx_seq[i - MA_FAST + 1:i + 1]) / MA_FAST)
        if i < MA_SLOW - 1:
            slow_ma.append(None)
        else:
            slow_ma.append(sum(idx_seq[i - MA_SLOW + 1:i + 1]) / MA_SLOW)

    for i, d in enumerate(common_dates):
        do_rebal = any(i == h_idx for h_idx in half_year_first.values())

        if do_rebal and i >= lookback:
            # Current portfolio value
            eq_now = cash + sum(shares * closes[c][i] for c, shares in holdings.items())

            # HS300 MA timing: full vs reduced exposure
            if fast_ma[i] is not None and slow_ma[i] is not None and slow_ma[i] > 0:
                if fast_ma[i] > slow_ma[i]:
                    target_pct = 1.0      # Golden cross: full position
                else:
                    target_pct = ma_exposure  # Death cross: reduced position
            else:
                target_pct = 1.0

            # Step 1: ATR-based volatility weights
            atrs = {c: calc_atr(highs[c], lows[c], closes[c], i, lookback)
                    for c in ALL_CODES}
            vol_weights = {c: 1.0 / (atrs[c] ** weight_pow) if atrs[c] > 0 else 0
                           for c in ALL_CODES}

            # Step 2: Earnings Yield (EY) boost
            # EY = TTM EPS / Price (higher = cheaper = more attractive)
            ey_map = {}
            for c in ALL_CODES:
                ttm = get_eps_ttm(eps_hist.get(c, []), d)
                if ttm is not None and ttm > 0 and closes[c][i] > 0:
                    ey_map[c] = ttm / closes[c][i]
                else:
                    ey_map[c] = None

            valid_ey = [v for v in ey_map.values() if v is not None]
            if len(valid_ey) >= 5:
                mean_ey = sum(valid_ey) / len(valid_ey)
                std_ey = math.sqrt(
                    sum((v - mean_ey) ** 2 for v in valid_ey)
                    / max(1, len(valid_ey) - 1)
                )
            else:
                mean_ey = 0
                std_ey = 1

            final_weights = {}
            for c in ALL_CODES:
                vw = vol_weights[c]
                if vw <= 0:
                    final_weights[c] = 0
                    continue

                ey = ey_map[c]
                if ey is None:
                    final_weights[c] = vw  # No EY data: pure vol weight
                else:
                    ey_z = (ey - mean_ey) / std_ey if std_ey > 0 else 0
                    # High EY -> positive boost; low EY -> negative penalty
                    penalty = 1.0 + ey_pow * ey_z
                    penalty = max(0.1, penalty)  # Clamp to avoid extreme values
                    final_weights[c] = vw * penalty

            # Normalize to sum to 1
            total_w = sum(final_weights.values())
            if total_w > 0:
                final_weights = {c: w / total_w for c, w in final_weights.items()}

            # Execute rebalancing
            eq_open = cash + sum(shares * opens[c][i] for c, shares in holdings.items())
            new_holdings = {}
            new_cash = cash

            # Sell existing positions
            for c, shares in holdings.items():
                sell_px = opens[c][i] * (1 - SLIPPAGE)
                gross = shares * sell_px
                fee = max(gross * COMMISSION_RATE + gross * STAMP_TAX, 5)
                new_cash += gross - fee

            # Buy new positions
            for c in ALL_CODES:
                target_v = eq_open * final_weights[c] * target_pct
                buy_px = opens[c][i] * (1 + SLIPPAGE)
                sh = int(target_v / buy_px / 100) * 100
                if sh >= 100:
                    cost = sh * buy_px
                    fee = max(cost * COMMISSION_RATE, 5)
                    if cost + fee <= new_cash:
                        new_holdings[c] = sh
                        new_cash -= cost + fee
                        n_trades += 1

            holdings = new_holdings
            cash = new_cash

        # Record daily equity
        eq_now = cash + sum(shares * closes[c][i] for c, shares in holdings.items())
        eq.append(eq_now)

    return eq, n_trades


def calc_metrics(eq, idx_map, common_dates):
    """Calculate performance metrics."""
    if not eq or len(eq) < 2:
        return {}

    rets = [eq[t] / eq[t - 1] - 1 for t in range(1, len(eq))]
    ann_ret = (eq[-1] / eq[0]) ** (252.0 / len(eq)) - 1
    std = math.sqrt(252) * math.sqrt(sum(r ** 2 for r in rets) / len(rets))
    sharpe = ann_ret / std if std > 0 else 0

    # Max drawdown
    peak = eq[0]
    max_dd = 0
    for e in eq:
        peak = max(peak, e)
        dd = e / peak - 1
        max_dd = min(max_dd, dd)

    # Train / Test split (60 / 40)
    split = int(len(rets) * 0.60)
    if split > 0:
        f_rets = rets[:split]
        t_rets = rets[split:]
        f_ann = (eq[split] / eq[0]) ** (252.0 / split) - 1
        t_ann = (eq[-1] / eq[split]) ** (252.0 / len(t_rets)) - 1
        f_std = math.sqrt(252) * math.sqrt(sum(r ** 2 for r in f_rets) / len(f_rets))
        t_std = math.sqrt(252) * math.sqrt(sum(r ** 2 for r in t_rets) / len(t_rets))
        f_sh = f_ann / f_std if f_std > 0 else 0
        t_sh = t_ann / t_std if t_std > 0 else 0
    else:
        f_sh = sharpe
        t_sh = sharpe
        f_ann = ann_ret
        t_ann = ann_ret

    return {
        'annual_return': ann_ret,
        'sharpe': sharpe,
        'full_sharpe': f_sh,
        'test_sharpe': t_sh,
        'full_ann': f_ann,
        'test_ann': t_ann,
        'max_drawdown': max_dd,
        'final_equity': eq[-1],
        'n_days': len(eq),
    }


def main():
    print("=" * 60)
    print("Defensive Earnings Yield + Low-Vol Strategy")
    print("=" * 60)

    # Load data
    common_dates, closes, opens, highs, lows = load_stock_data(ALL_CODES)
    idx_close_map = load_index()
    eps_hist = load_eps_history()

    print(f"Data: {len(common_dates)} trading days, {len(ALL_CODES)} stocks")
    print(f"EPS history available for {len(eps_hist)} stocks")
    print()

    # Run strategy
    eq, n_trades = run_strategy(
        common_dates, closes, opens, highs, lows,
        idx_close_map, eps_hist,
        lookback=160, weight_pow=4.5, ey_pow=0.5,
        ma_exposure=0.5
    )

    metrics = calc_metrics(eq, idx_close_map, common_dates)

    print(f"Results:")
    print(f"  Full Sharpe:     {metrics.get('full_sharpe', 0):.4f}")
    print(f"  Test Sharpe:     {metrics.get('test_sharpe', 0):.4f}")
    print(f"  Annual Return:   {metrics.get('annual_return', 0)*100:.2f}%")
    print(f"  Max Drawdown:   {metrics.get('max_drawdown', 0)*100:.2f}%")
    print(f"  Final Equity:    {metrics.get('final_equity', 0):,.0f}")
    print(f"  Rebalances:      {n_trades}")

    # Save equity curve
    with open('equity_curve.json', 'w') as f:
        json.dump({'dates': common_dates[-len(eq):], 'equity': eq}, f)
    print()
    print("Equity curve saved to equity_curve.json")


if __name__ == '__main__':
    main()
