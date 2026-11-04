# Method and evidence sources

Current code/configuration define our experiment. Papers define attribution to
their authors, not certification of our adaptations. Historical planning PDFs
are not runtime dependencies.

- Driessen, Maenhout and Vilkov, correlation-risk evidence:
  https://www.netspar.nl/wp-content/uploads/061_Driessen.pdf
- Faria, Kosowski and Wang, implied correlation research:
  https://spiral.imperial.ac.uk/server/api/core/bitstreams/105509fb-ca86-4f87-958b-3df08bd67d1e/content
- Bollerslev, Li and Tang, Forecasting and Managing Correlation Risks:
  https://econ.duke.edu/~boller/Papers/Cov_ML.pdf
  Motivates multiscale/downside families; our daily scalar-index model does not
  replicate their high-frequency stock-pair forecasting panel.
- Statsmodels HAC reference:
  https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html
- Statsmodels ADF/KPSS interpretation:
  https://www.statsmodels.org/stable/examples/notebooks/generated/stationarity_detrending_adf_kpss.html

The retained public comparison series is important_data/sources/public_ic_rc.parquet.
Licensed shards and original source metadata remain with the local raw bundle.
The public precomputed-series approximation does not validate raw extraction.

Dated economic explanations were previously checked against Fed/BIS accounts.
They remain hypotheses, not identified causes:

- https://www.federalreserve.gov/monetarypolicy/mpr_20120229_part2.htm
- https://www.federalreserve.gov/monetarypolicy/2021-02-mpr-part1.htm
- https://www.bis.org/publ/arpdf/ar2017e2.htm
- https://www.federalreserve.gov/publications/files/financial-stability-report-20250425.pdf

Marshall/Nelken attribution and vendor conventions remain bounded by the inspected
project materials. No exact original-paper replication or new vendor-manual
verification was performed during cleanup.
