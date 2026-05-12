# 10 — Phase 6: Probabilistic Signal Engine

## Objective

Combine valuation, quality, balance-sheet, market and news features into a transparent probabilistic signal.

## Scope

Implement a rule-based probabilistic score for MVP. Add machine-learning calibration later when historical data is sufficient.

## Agent instructions

Do not claim the probabilities are statistically calibrated in MVP unless a backtest and calibration step has been implemented. Name the first model `signal_rule_v0`.

## Required modules

- `src/investment_app/scoring/rule_based.py`
- `src/investment_app/scoring/probabilistic.py`
- `src/investment_app/scoring/explanations.py`

## Feature families

Weights:

```text
valuation: 40%
quality: 25%
balance_sheet: 15%
news: 10%
market_regime: 10%
```

## Rule score

Convert each family to 0–100.

### Valuation score

Inputs:

- conservative margin of safety;
- price vs IV P25/P50/P75;
- uncertainty width.

Example:

- MOS >= 25%: 90
- MOS >= 15%: 75
- MOS >= 10%: 65
- MOS between 0 and 10%: 55
- MOS below 0: 40 or lower

Penalise high uncertainty.

### Quality score

Use `final_quality_score` from Phase 5.

### Balance-sheet score

Inputs:

- net debt / EBITDA;
- interest coverage;
- cash position;
- FCF consistency.

### News score

Inputs:

- news sentiment 7d;
- news volume;
- negative event tags.

### Market regime score

Inputs:

- momentum 60d and 250d;
- volatility;
- drawdown.

## Probability transformation

Use a logistic transform:

```text
prior = sigmoid((rule_score - 50) / 12)
```

Then apply uncertainty penalty:

```text
p_buy_adjusted = p_buy * (1 - min(0.35, uncertainty_width / 0.80))
```

## Sell probability

Sell probability should increase when:

- price is above IV P75;
- quality score deteriorates;
- red flags appear;
- leverage rises;
- negative news spikes;
- thesis deterioration is detected.

## Final signal rules

The final persisted signal must match the SQL schema exactly. Valid values are:

- `strong_buy`
- `buy`
- `hold`
- `sell`
- `strong_sell`
- `insufficient_data`

| Signal | Rule |
|---|---|
| strong_buy | `p_buy_adjusted >= 0.70` and `MOS_cons >= 0.15` and no hard red flags |
| buy | `p_buy_adjusted >= 0.60` and `MOS_cons >= 0.10` |
| hold | neutral range |
| strong_sell | `p_sell >= 0.60` or price > IV P75 with deterioration |
| sell | hard red flag or thesis break |
| insufficient_data | core valuation, qualitative, and factor inputs are too weak or missing to support a reliable signal |

## Explanations

Every signal must store:

- top feature contributors;
- red flags;
- freshness flag;
- short natural-language explanation.

Example:

```text
Signal changed to buy because conservative margin of safety rose to 18%, ROIC remains above WACC, and balance-sheet risk is low. The main penalty is high valuation uncertainty.
```

## Acceptance criteria

- `signal_runs` is populated.
- Every signal includes p_buy, p_buy_adjusted, p_sell and final_signal.
- Every signal includes an explanation and top contributors.
- Unit tests cover thresholds and red-flag behaviour.

## Suggested commit message

```text
feat: add rule-based probabilistic signal engine
```
