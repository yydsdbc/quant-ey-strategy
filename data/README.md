# Data Format

JSON format, one file per stock:

```
data/{code}.json
```

Example: `data/000001.json`

Index: `data/idx_000300.json` (HS300 close price series)

Each JSON file contains bars as arrays:
```
[date, open, high, low, close, volume]
```


## Getting Data

Free data sources:

### baostock (recommended)
```python
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus("sh.600000",
    "date,open,high,low,close,volume",
    start_date='2016-01-01', end_date='2026-12-31',
    frequency="d", adjustflag="2")
# Convert to JSON and save
```


## Notes

- Use adjusted prices (qfq) for backtesting
- Index data (idx_000300) should use the same date range as stock data
- All dates should be trading days only (exclude weekends/holidays)
