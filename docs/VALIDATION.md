# Integrated-project verification

Checks executed 2026-11-03/04 on Windows, Python 3.12.15. The external clean
environment installs the integrated lock (39 packages). No supplied folder was
edited. Generated logs, licensed pilot observations and the environment are
outside this project, under the local team_integration verification directory.

| Check | Status | Actual scope |
|---|---|---|
| Mixed-folder baseline | FAIL | 133 passed, 27 failed: reverted imports, mapping/reporting and history integration |
| Integrated offline CLI | PASS | 187 tests, no failures/errors/skips; includes all 160 prior tests and 27 team arithmetic/timing/compatibility cases |
| Python syntax / name checks | PASS | All 104 delivered Python files compile; no unresolved function-global names; all five original script launchers accept --help without acquisition |
| Fresh source-only install / commands | PASS | 131-file source export, no Git/environment/data; separately installed all 39 locked packages; all 187 tests pass and dispersion-events help works |
| wrds.raw_sql + SQLAlchemy | PASS | Both SELECT 1 paths with pandas 2.1.4 / SQLAlchemy 1.4.54 |
| WRDS schema access | PASS | CRSP stocks/membership/links, OptionMetrics surfaces/forwards/rates/index returns, Compustat membership |
| Real package-IV / IC / RC arithmetic | PASS | Five stocks, two index packages, 21 return sessions; repricing max 4.34e-13; RC vs explicit pairs 1.34e-15; IC identity 2.23e-15 |
| New team option-cost workflow | PASS | One date, top three SPX stocks plus index, both methods: eight rows; quote/maturity/delta/vega/arithmetic QA passes |
| New team returns/weights workflow | PASS | Full one-day SPX export: 503 members, normalized weights and populated returns |
| Real team event workflow | PASS | Five-stock partial sample, 85 real sessions, 56 trailing RC dates; event tables and three basket charts |
| Old/new team basket parity | PASS | Executed the supplied original basket script on exactly the same real sample; max weighted/equal RC difference 5.56e-16 |
| Real public VIX workflow | PASS | Small FRED VIX CSV, 88 input rows, two full-period charts and overlay table; unavailable 2022/2025 panels correctly skipped |
| Kevin real MIV | PASS | One date, three explicit stocks, 36 completed-month history; weight × IV × stock-index-correlation sum and spread agree exactly; partial basket only |
| Supplied DJIA membership | PASS | All 3,774 configured entry sessions covered; 28–30 unique mapped members; no overlapping records; original CSV unchanged |
| Saved research reconstruction | PASS | Prepared features regenerated from existing local inputs: 3,665 rows, 3,414 eligible; all eight saved fits reconstruct, max prediction difference 2.23e-16; 15 annual real-arithmetic checks pass |
| File-map / source preservation | PASS | Every one of 131 source files inventoried; no source path deleted; research calculations unchanged; verification CLI checkout lookup corrected; all ten added team src/data files unchanged; supplied folders unchanged |
| Optional automatic DJIA name matching | FAIL | Existing confidence gate rejects DJX-to-Compustat match; supplied dated CSV route is the supported bypass |
| Non-editable installation | PASS | Reproduced site-packages test-discovery failure, corrected checkout discovery and reran all 187 tests |
| Original manual WRDS diagnostics | PASS | All seven executed at their historical scopes; approved Nasdaq schema-aware diagnostic no longer issues invalid-column queries; incompatible tables explicitly skipped |
| Fresh one-entry DJIA rebuild | PASS | All nine raw tables acquired; full-basket IC/future RC pass; IC, past RC and future RC exactly match the saved 2024-07-01 measurement |
| Original stress/hedge utilities | PASS | Unmodified fixed-path scripts with one-date 2024 data: four straddle rows, three valid stock quotes; independent stress/half-spread arithmetic agrees |
| Failure-path / legacy contracts | PASS | Missing whole sessions, mixed indices, invalid inputs, preserved failed publications, stale chart removal, legacy file/header chains and strict QA tested |
| FRED full release-calendar acquisition | NOT RUN | Requires each operator's FRED_API_KEY; configuration/holiday alignment/import boundaries checked offline |
| Full historical refit / team research rerun | NOT RUN | No large downloads/refits; earlier research engine and study definitions preserved |
| Independent Faria raw-data replication | NOT RUN | Still unfinished; precomputed-series comparison is not independent replication |
| Independent second scientific review | NOT RUN | No independent reviewer was invoked |
| GitHub hosted Linux CI | NOT RUN | Offline workflow configured; no push occurred |

An initial integrated test attempt had 25 setup errors because the sandbox's
default temporary directory was unwritable. Rerunning with an external writable
pytest base directory passed all tests; no code/test assertion was weakened.
WRDS emits four upstream SyntaxWarnings about escape sequences, not query failures.

Sources and inherited Git objects were checked against the known local password
without displaying it: no matches. Source literal-secret checks also found no
embedded key/password assignments. This is a scoped check, not proof that no
unknown credential could ever exist. Git identity is not treated as a WRDS password.
Licensed membership stays local and is removed from the integration index, not
deleted from disk. Upstream history is preserved rather than rewritten.

The saved eight OLS coefficient sets and 15 annual arithmetic examples were reconstructed
from the regenerated local features. Their saved predictions agree. Full acquisition,
bootstrap inference, all historical gap reports and full team studies were not rerun.
The original saved dataset was correctly rejected as stale because delivery line-ending
bytes changed source fingerprints; features were regenerated externally rather than
bypassing the guard or editing the old receipt. Earlier aggregate results remain historical.
Small real checks validate exercised interfaces/arithmetic, not every security/date,
event-calendar vintage, coefficient stability, executable trading or zero bias.
Event-study naive p-values remain descriptive under overlapping windows.
The retained vendor rate/pricing conventions were not tuned to make checks pass.

The final review added 16 regression cases after reproducing seven issues the
earlier 171-test suite missed. The strict cost command reuses the original
reporting calculation; the original script and all ten added team data modules
remain byte-for-byte preserved. The one protected manual diagnostic change was
specifically approved. Automatic DJIA name discovery is still FAIL; the fresh
successful DJIA rebuild used the supplied dated CSV, not a weakened matcher.

FRED release-calendar acquisition still lacks a live API key; network-error
redaction is tested without exposing one. No claim of full vendor-history,
independent scientific review or zero bias is made. The existing eight-model
reconstruction and unchanged financial definitions remain valid evidence.

Final same-input comparisons also preserve the original basket shock annotations, event-statistic tables and VIX overlay columns. Their maximum numerical differences are 5.56e-16, 2.99e-16 and 1.43e-14 respectively on the retained real sample.
