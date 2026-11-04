# DJIA 30-day research results

Four retained equations, each fitted as A (all eligible training) and B (fixed crash exclusions).

Training information: 2011-01-01 through 2022-12-31. Final comparison: 2023-01-01 through 2025-08-29. This period was inspected in earlier rounds; it is not fresh confirmation.

Prepared rows: 3,665; common eligible rows: 3,414. Baselines and expanded equations use identical training-feature eligibility within each A/B design. Missing data are not zero-filled; early partial baskets remain labelled.

| Equation | A RMSE | B RMSE | A MAE | B MAE |
|---|---:|---:|---:|---:|
| ic_only | 10.841 | 10.773 | 8.044 | 7.702 |
| baseline | 10.845 | 10.795 | 8.041 | 7.701 |
| expanded | 10.832 | 10.840 | 8.098 | 7.823 |
| requested | 10.851 | 10.803 | 8.029 | 7.711 |

Errors are correlation percentage points. Lower is better. Coefficient significance, paired-loss HAC/bootstrap intervals and yearly/non-overlap scores can be regenerated in `data/research/models/`. All four equations remain saved; there is no automatic winner selection.

## Fitted equations

- A/ic_only: `RC_hat = 0.047792 + (0.751710)*ic`; training rows 2726.
- A/baseline: `RC_hat = 0.047816 + (0.754231)*ic + (-0.002974)*rc_past`; training rows 2726.
- A/expanded: `RC_hat = 0.054815 + (0.753798)*ic + (0.007583)*rc_past + (-0.080698)*vol20 + (-0.212134)*return20 + (0.014974)*index_iv`; training rows 2726.
- A/requested: `RC_hat = 0.018380 + (0.784522)*ic + (0.008939)*rc_past + (-0.190493)*slow_rc + (0.166115)*downside_rc`; training rows 2726.
- B/ic_only: `RC_hat = 0.036267 + (0.721319)*ic`; training rows 2424.
- B/baseline: `RC_hat = 0.036569 + (0.733117)*ic + (-0.014472)*rc_past`; training rows 2424.
- B/expanded: `RC_hat = 0.066384 + (0.783031)*ic + (-0.028930)*rc_past + (0.024667)*vol20 + (-0.510063)*return20 + (-0.298595)*index_iv`; training rows 2424.
- B/requested: `RC_hat = 0.038546 + (0.739941)*ic + (-0.011004)*rc_past + (-0.011813)*slow_rc + (-0.002824)*downside_rc`; training rows 2424.

Signals are `IC - predicted future RC`, saved as decimals and correlation percentage points. They are not investment returns.

## Historical actual gaps

| Years | Mean gap (points) | HAC 95% interval (points) |
|---|---:|---|
| 15 | 5.963 | [4.115, 7.811] |
| 10 | 5.354 | [3.061, 7.648] |
| 7 | 4.900 | [2.183, 7.617] |
| 5 | 5.038 | [2.168, 7.908] |

Nested windows are dependent. Positive average gaps are not proof of mispricing or tradable profit. The public Faria-style approximation remains about 4.63 points; it uses shifted precomputed series rather than Fariaâ€™s original option data. Its calculation does not validate the raw-return calculator; explicit real-pair checks do.

## Actual-gap exploration and limitations

Actual IC minus subsequent RC quintiles/deciles and dated episodes can be regenerated in `data/research/analysis/`. No predicted thresholds enter these groups. Full-history exploration is descriptive and never selects model inputs. Larger positive gaps accompany lower future market volatility on average; event explanations are hypotheses, not causal identification.

Overlapping outcomes create daily error dependence. HAC (15/30/60), block bootstrap and disjoint-window sensitivities accommodate it without pretending errors become independent. Calibration, variance, stationarity, collinearity, influence and coefficient stability diagnostics remain visible. B estimates a selected crash-free training sample. Source publication/vintage timing and early full-index equivalence remain uncertified. No independent scientific signoff or trading P&L is claimed.

The previous five-variable model used broader history eligibility. Its exact original sample is checked in the retained verification receipt; this report uses a common sample for fair comparisons. Prior important aggregates are summarized in `docs/RESULTS.md`.

Reusable dataset, models and verification can be generated locally under `important_data/`; they are not bundled in this source checkout. Detailed phase outputs under `data/research/` are disposable and can be regenerated.

Measurement revision: available_inputs_v1. Valid duration-flagged returns are retained; genuinely missing observations use explicitly reported available-pair estimates. The Faria public-series comparison is unchanged. Original coefficient references remain historical rather than rewritten to match the changed measurement target.

## S&P 500 after the missing-input correction

| Years | Usable / grid dates | Mean gap (points) | HAC 95% interval | Two-sided p |
|---|---:|---:|---|---:|
| 5 | 1256 / 1256 | 0.343 | [-2.102, 2.788] | 0.783 |
| 7 | 1743 / 1760 | -0.126 | [-2.487, 2.236] | 0.917 |

Neither SPX proxy mean is statistically significant. Both requested four-column exports are regenerated under important_data/spx_30d/. The duration/whole-window rejection is removed. Missing entry weighting inputs are omitted and counted; future correlations use available observed-session pairs, with original pair-weight coverage reported. Missing returns are never filled with zero.

The 17 remaining seven-year omissions are 2020-07-27 through 2020-08-18: both index option legs have unavailable IV and negative sentinel strike/premium inputs. Five-year coverage is complete. Some entry caps are unavailable, so full-membership cap coverage is explicitly unknown on those dates.

DJIA five/seven-year full-basket eligibility is unchanged (three entries lack constituent options); the removed duration rule recovers 22 earlier DJIA labels. All four approved A/B equations were refreshed with the same split dates and crash exclusions. Kevin-derived files, source observations and vendor conventions are unchanged.
