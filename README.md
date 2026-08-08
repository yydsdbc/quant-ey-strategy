# A-Share Low-Vol Value Strategy

Quantitative strategy for China A-Shares (HS300 constituents), combining **volatility-weighted portfolio** with **Earnings Yield (EY) factor** and **HS300 MA timing**.

> Backtest period: 2016-10 to 2026-07 (~10 years)
> Sharpe: 1.792 | Annual Return: +32.95% | Max Drawdown: -13.82%


## Strategy Logic (3 Layers)

**Layer 1 — Volatility Weighting**
```
weight_i = 1 / ATR_i^4.5
```
Low-vol stocks get higher weight. Uses ATR (Average True Range) instead of return volatility — more robust to A-share limit-up/limit-down gaps.

**Layer 2 — Earnings Yield Boost**
```
EY_i = TTM_EPS_i / Price_i
weight_i = vol_weight_i × (1 + 0.5 × EY_z_i)
```
Stocks with higher earnings yield (cheaper by earnings) receive additional weight boost. TTM EPS = sum of last 4 quarterly reports.

**Layer 3 — HS300 MA(50/200) Timing**
- Golden cross (MA50 > MA200) -> full position
- Death cross (MA50 < MA200) -> 50% position

Semi-annual rebalancing (January and July).


## Performance

| Metric | Buy & Hold (HS300) | This Strategy |
|--------|--------------------|--------------------|
| Annual Return | +23.03% | **+32.95%** |
| Sharpe Ratio | 0.816 | **1.792** |
| Max Drawdown | -45.60% | **-13.82%** |
| Test Sharpe (2021-2026) | -- | **1.593** |

Test Sharpe is only 11% lower than full-sample Sharpe, indicating genuine alpha rather than overfitting.


## Why It Works

Most technical factors (RSI, Bollinger Bands, 52w High, volume surges) fail in A-shares because 80%+ of trading volume comes from retail investors — short-term signals are dominated by noise and sentiment.

EY + vol_weighting works because:
- EY reflects fundamentals, not short-term sentiment
- Volatility weighting captures the cross-sectional risk premium (low-vol anomaly is a documented, market-neutral effect)
- HS300 MA timing provides crude bear-market protection without whipsawing


## Installation

```bash
pip install -r requirements.txt
```


## Usage

```bash
# Prepare your data in data/*.json (see data/README.md)
python backtest.py
```

For a Jupyter notebook demo, open `notebooks/backtest_demo.ipynb`.


## Data Format

Each stock: `data/{code}.json`

```json
[
  ["2024-01-02", 10.5, 10.8, 10.3, 10.7, 1234567],
  ["2024-01-03", 10.7, 11.0, 10.6, 10.9, 2345678],
  ...
]
<!-- date, open, high, low, close, volume -->
```

Index: `data/idx_000300.json` (HS300 close prices)

For data acquisition, see `data/README.md`. Free sources include baostock and tushare.


## Key Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| lookback | 160 | ATR lookback period (days) |
| weight_pow | 4.5 | Vol weighting exponent |
| ey_pow | 0.5 | EY z-score boost multiplier |
| ma_exposure | 0.5 | Position size during death cross |


## Research Context

Tested 65+ factor directions across 10,000+ parameter combinations. All failed to beat EY + vol_weighting:

- BB Squeeze, RSI, 52w High, Volume Surge (all failed)
- Hurst Exponent, Copula Tail Risk, Beta Hedge (all failed)
- Amihud Illiquidity, ADX Trend Strength, Industry Momentum (all failed)
- Copula regime switching, IRM risk management (all failed)

EY is the only alpha source that survived rigorous out-of-sample testing.


## Disclaimer

For research only. Past performance does not guarantee future results. Author is not responsible for any investment losses.


## License

MIT
