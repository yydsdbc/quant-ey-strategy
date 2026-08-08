#!/usr/bin/env python3
"""
Backtest runner for EY + Low-Vol Strategy.

Usage:
    python backtest.py

Output:
    - Console: key performance metrics
    - File: equity_curve.json (for plotting)
"""

import json
import math
import matplotlib.pyplot as plt
from pathlib import Path

from strategy_ey_lowvol import (
    load_stock_data, load_index, load_eps_history,
    run_strategy, calc_metrics,
    ALL_CODES
)


def main():
    print("Loading data...")
    common_dates, closes, opens, highs, lows = load_stock_data(ALL_CODES)
    idx_close_map = load_index()
    eps_hist = load_eps_history()

    print(f"  {len(common_dates)} trading days, {len(ALL_CODES)} stocks")
    print(f"  EPS data available for {len(eps_hist)} stocks")
    print()

    # Run with best-known parameters
    print("Running strategy (LB=160, PW=4.5, EP=0.5)...")
    eq, n_trades = run_strategy(
        common_dates, closes, opens, highs, lows,
        idx_close_map, eps_hist,
        lookback=160, weight_pow=4.5, ey_pow=0.5,
        ma_exposure=0.5
    )

    metrics = calc_metrics(eq, idx_close_map, common_dates)

    print()
    print("=" * 50)
    print("PERFORMANCE RESULTS")
    print("=" * 50)
    print(f"  Full Sharpe:      {metrics['full_sharpe']:.4f}")
    print(f"  Test Sharpe:      {metrics['test_sharpe']:.4f}")
    print(f"  Annual Return:    {metrics['annual_return']*100:.2f}%")
    print(f"  Full Ann:        {metrics['full_ann']*100:.2f}%")
    print(f"  Test Ann:        {metrics['test_ann']*100:.2f}%")
    print(f"  Max Drawdown:   {metrics['max_drawdown']*100:.2f}%")
    print(f"  Final Equity:    {metrics['final_equity']:,.0f}")
    print(f"  Rebalances:      {n_trades}")
    print("=" * 50)

    # Build benchmark equity curve (Buy & Hold HS300)
    bh_dates = [d for d in common_dates if d in idx_close_map]
    bh_prices = [idx_close_map[d] for d in bh_dates]
    bh_eq = [p / bh_prices[0] * 1_000_000 for p in bh_prices]

    # Save equity curves
    with open('equity_curve.json', 'w', encoding='utf-8') as f:
        json.dump({
            'strategy': {
                'dates': common_dates[-len(eq):],
                'equity': eq
            },
            'benchmark': {
                'dates': bh_dates[-len(eq):],
                'equity': bh_eq[-len(eq):]
            }
        }, f, ensure_ascii=False)

    # Plot
    strat_eq_norm = [e / eq[0] for e in eq]
    bh_eq_norm = [e / bh_eq[0] for e in bh_eq[-len(eq):]] if len(bh_eq) >= len(eq) else None

    plt.figure(figsize=(12, 6))
    plt.plot(common_dates[-len(eq):], strat_eq_norm, label='Strategy', linewidth=1.5)
    if bh_eq_norm:
        plt.plot(common_dates[-len(eq):], bh_eq_norm, label='Buy & Hold (HS300)', linewidth=1.5, alpha=0.7)
    plt.title('Strategy vs Buy & Hold (Normalized to 1.0)')
    plt.xlabel('Date')
    plt.ylabel('Normalized Value')
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('equity_curve.png', dpi=150)
    print()
    print("Saved: equity_curve.json, equity_curve.png")


if __name__ == '__main__':
    main()
