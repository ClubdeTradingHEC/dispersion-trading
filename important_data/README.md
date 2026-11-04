# Local-only inputs

Only this README belongs in Git/source exports. Keep licensed observations,
generated models and caches local. Do not upload or commit them.

Supply `sources/membership.csv` separately for DJIA: dated `index,permno,start,end`
intervals. The private working folder preserves the supplied CSV; Git exports do
not contain it. Automatic DJX-to-Compustat name discovery currently fails its
confidence check, so the CSV is a required separately supplied input for DJIA.

PROJECT_GUIDE documents WRDS acquisition and offline research. TEAM_WORKFLOWS
documents returns, event-calendar, VIX and execution-cost inputs. Environments
are installed locally; no generated observations are needed merely to run tests.
Historical vendor/publication timing remains uncertified.
