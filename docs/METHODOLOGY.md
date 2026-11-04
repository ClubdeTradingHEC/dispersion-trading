# Methodology

The active experiment is DJIA/DJX at 30 calendar days. The measurement engine
also supports declared 60/91-day horizons and configured SPX inputs. Their
availability and economic conventions must be validated separately.

## 4. Financial definitions that must never be conflated

For entry date `t`, horizon `H` in **30, 60, or 91 calendar days**, and explicitly declared point-in-time basket/weights:

**Package (near-ATM) IV:** For index and constituents, obtain OptionMetrics standardized +50-delta **call** and -50-delta **put**, each with its own strike and *vendor theoretical surface premium*, plus the applicable forward, continuously compounded zero rate, and `T=H/365` (unless authoritative provider evidence requires an explicit revision). Solve for **one common Black-model volatility** whose **call-plus-put premium** equals the sum of the two theoretical premiums. **Add premiums, never IVs.** The arithmetic and optional vega-weighted averages are diagnostics, not the primary IV. This is a near-ATM two-leg *package*, not guaranteed to be a listed same-strike, executable straddle. Validate strike/forward proximity, repricing residuals and vendor quality fields.

**Kevin/Marshall-style MIV:**

`MIV(t,H) = sum_i w_i(t) * sigma_i_package(t,H) * rho_i,index_past(t)`.

The `rho_i,index_past` term is the **historical stock-index return correlation**, ordinarily based on **36 completed monthly returns**. Changing option tenor to 30/60/91 days does **not** automatically change the 36-month historical correlation lookback. The corresponding volatility spread is `sigma_index_package(t,H) - MIV(t,H)`; it has **volatility units**, not correlation units. Do not claim this is an exact replication of Marshall's original paper without checking its specification.

**Pairwise implied correlation (IC):** With `a_i=w_i*sigma_i_package`, `D=(sum_i a_i)^2-sum_i a_i^2`, compute

`IC(t,H) = [sigma_index_package(t,H)^2 - sum_i a_i^2] / D`.

This is a **scalar, package-IV-based weighted-average stock-stock implied-correlation proxy**, not a matrix of individual implied pair correlations or model-free variance-swap correlation. Check denominator conditioning and out-of-range raw estimates; do not silently clamp results.

**Future realized correlation (RC):** Use **underlying constituent daily returns**, form common-date **stock-stock Pearson pair correlations** on the declared *future* window, and aggregate using entry-date pair weights `q_ij = a_i*a_j / sum_{k<l}(a_k*a_l)`. Freeze entry membership, weights and IV inputs. With complete data, `RC_future(t,H)=sum_{i<j}q_ij(t,H)*rho_ij_future(t,H)` and the fast pair identity is exact.

**Available-input policy (Rafael's explicit correction):** Follow Kevin's skip-and-report approach. Missing entry weighting inputs omit that constituent before normalizing available weights; missing entry options use the existing option-feasible proxy. Keep finite valid daily returns, including CRSP `DD` delisting returns; duration flags alone do not invalidate them. For a genuinely missing return, each pair uses its common observed sessions (minimum ten). Omit only pairs without enough observations or nonzero variance. The available-pair proxy is `sum_available(q_ij*rho_ij) / sum_available(q_ij)`; record pair count, covered original pair-weight mass, missing-observation count and minimum overlap. No missing return becomes zero, no new constituent replaces an entry member, and partial results are not called the complete official index. A missing market cap also leaves original full-membership cap coverage unknown, rather than falsely reporting 100%. Complete-column pairs retain the fast identity; other pairs use direct Pearson calculations. This explicitly disclosed proxy replaces the former blanket whole-window rejection. Complete-grid diagnostic bounds remain separate from this estimate.

**Direct IC–RC test:** `gap(t,H)=IC(t,H)-RC_future(t,H)`. It is an *ex-post observed difference*, not an OLS forecast and not trading P&L. A positive mean alone does not prove mispricing, causality, or executable profit.

**MIC / modified-Markowitz proxy:** Investigate `MIC(t,H)=sigma_index_package(t,H)/sum_i[w_i(t)*sigma_i_package(t,H)]` only against a **definitionally matched future stock-index dependence measure** and under stated basket/return assumptions. **MIC is not automatically the same object as pairwise RC.** `MIV/sum_i(w_i*sigma_i)` is an IV-weighted average of **historical stock-index** correlations, not an option-implied stock-stock correlation. Test empirical closeness/equivalence with predeclared tolerances; never assert equality or a tradable signal merely because two numbers are similar.


## Retained forecasting specifications

All equations include an intercept and predict future 30-day pairwise RC.

| ID | Predictors |
|---|---|
| `ic_only` | current IC |
| `baseline` | current IC, previous 30-calendar-day RC |
| `expanded` | IC, past RC, 20-session realized market volatility, 20-session compounded market return, index package IV |
| `requested` | IC, past RC, slow RC, downside co-movement |

All variables are decimals. Market volatility is annualized with sqrt(252).
Slow RC is weighted Pearson correlation over 252 sessions through entry close,
with time weights proportional to 2^(-age/60). Negative-return co-movement uses
120 sessions and min(return,0), without demeaning, normalized by each stock's
negative-return norm. It requires at least ten negative observations per member.
Both use frozen entry weight-times-package-IV pair weights. Positive returns
become zero only in the downside definition; missing returns never become zero.

All four equations share complete-feature eligibility, including 252-session
history for every entry member. Availability reasons remain in the dataset.
The earlier five-variable fit had broader eligibility. Its original coefficients
remain a historical reference. After the authorized missing-input correction,
verification records differences as CHANGED_MEASUREMENT_POLICY; it does not
overwrite those references or claim old-target coefficient parity. Current fits
are independently reconstructed and checked against statsmodels.

## Timing and Model B

Training entries begin 2011-01-01. Both signals and outcome availability must be
no later than 2022-12-31. Development forecasts run annually during 2015–2022
using only information available by the previous year-end. Final coefficients
freeze for 2023-01-01 through feasible 2025-08-29 entries. The global observation
ceiling remains 2026-12-31; a ceiling does not establish data availability.
The 2023–2025 period was already inspected and is retrospective comparison.

A uses all eligible training rows. B removes training entries on each of the
33 predefined crash dates and entries whose next 30 calendar days include one.
These dates are fixed in configs/djia_crash_days.json. B's historical predictors
still contain actual crash returns; source returns are never deleted. Both use
identical final dates, including stress episodes. B is a selected training sample,
not an unconditional unbiased model or a crash-prediction system.

Entry features assume same-close observations. Future labels become usable only
after their declared availability. Historical vendor delivery/revision times are
not certified. Early mapped baskets can have 28–29 members; mapped normalization
is not proof of a full official-index decomposition.

## Inference and interpretation

Overlapping 30-day outcomes create serial dependence. Calendar-grid HAC at
15/30/60 sessions, stationary block bootstrap, and disjoint-window sensitivities
account for it in inference. They do not force raw residuals to be independent.
Coefficient tests use asymptotic robust t-ratios and joint Wald tests with Holm
adjustments. Diagnostics cover stationarity, collinearity, calibration, influence,
variance, specification and historical coefficient breaks. Non-rejection does
not prove correct specification or no omitted-variable bias.

Actual-gap quintiles/deciles sort IC minus subsequently realized RC. They are
retrospective descriptions, independent of regression forecasts or thresholds.
Future conditions may explain an outcome ex post but cannot enter predictors.
The public Faria-style comparison shifts precomputed published series; it is
not a reconstruction of Faria's original option data or an RC arithmetic check.

## Preserved vendor conventions

Kevin's approved rate rule, original weights, history handling and partial MIV
summation remain unchanged. Repricing quarantine is off by default. Missing
historical identifiers return the available list and a missing-count report.
Strict documented rate modes remain gated by provider evidence; cleanup does
not change rates, introduce an American solver or certify vendor conventions.
