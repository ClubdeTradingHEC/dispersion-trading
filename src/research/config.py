from dataclasses import dataclass, field, asdict
from pathlib import Path
import json
import pandas as pd
import math
# Declare index identifiers, weighting and return conventions.

@dataclass
class IndexSpec:
    """Declare index identifiers, weighting and return conventions."""
    name: str
    benchmark: str
    weighting: str
    secid: int | None = None
    enabled: bool = True
    membership_csv: str | None = None
    return_column: str = 'dlyret'
    # Kevin baseline: total stock vs vendor index return
    return_convention: str = 'Kevin_baseline_total_stock_vendor_index'
# Validate financial settings and configurable observation/information bounds.

@dataclass
class Config:
    """Validate financial settings and configurable observation/information bounds."""
    query_batch_ids: int = 200
    query_batch_days: int = 93
    entry_start: str = '2000-01-01'
    entry_end: str = '2025-05-30'
    observation_end: str | None = None
    horizons: list[int] = field(default_factory=lambda: [30, 60, 91])
    indices: list[dict] = field(default_factory=lambda: [
        asdict(IndexSpec('SPX', 'SPX', 'market_cap', 108105)),
        asdict(IndexSpec('DJIA', 'DJX', 'price', enabled=False))
    ])
    rate_unit: str = 'kevin'
    rate_compounding: str = 'continuous'
    rate_convention_confirmed: bool = False
    rate_confirmation_source: str = ''
    day_count: int = 365
    history_months: int = 36
    repricing_abs_tol: float = 0.01
    repricing_rel_tol: float = 0.01
    max_dispersion: float | None = None
    quarantine_repricing: bool = False
    min_sessions: int = 10
    bootstrap_repetitions: int = 1999
    seed: int = 20261008
    calibration_end: str = '2015-12-31'
    basket_fractions: list[float] = field(default_factory=lambda: [0.1, 0.25, 0.5, 0.75, 1.0])
    basket_counts: list[int] = field(default_factory=list)
    basket_weight_thresholds: list[float] = field(default_factory=lambda: [0.5, 0.75, 0.9, 0.95])
    basket_min_dates: int = 100
    basket_min_coverage: float = 0.8
    basket_tolerances: dict = field(default_factory=lambda: {
        'ic': 0.02,
        'rc_future': 0.02,
        'gap': 0.02,
        'miv': 0.005,
        'spread': 0.005,
        'mic': 0.02,
        'mic_rc_future': 0.02
    })
    basket_tolerances_confirmed: bool = False
    basket_reference: str = 'full'
    information_lag_sessions: int = 1
    mic_equivalence_margin: float = 0.02
    exclusions: dict = field(default_factory=lambda: {
        'exclude_gfc': [['2007-07-01', '2009-06-30']],
        'exclude_covid': [['2020-02-01', '2020-06-30']]
    })

    def validate(self):
        """Validate input fields and invariants before financial calculations."""
        if any((not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in (self.query_batch_ids, self.query_batch_days))):
            raise ValueError('positive integer query batch limits required')
        if not self.specs():
            raise ValueError('at least one enabled index required')
        if len(set(self.horizons)) != len(self.horizons):
            raise ValueError('duplicate horizons')
        if len({i['name'] for i in self.indices}) != len(self.indices):
            raise ValueError('duplicate index names')
        tolerances = [
            self.repricing_abs_tol,
            self.repricing_rel_tol,
            self.mic_equivalence_margin,
            *self.basket_tolerances.values()
        ]
        if not self.basket_tolerances or any((not math.isfinite(x) or x <= 0 for x in tolerances)):
            raise ValueError('finite positive tolerances required')
        if self.max_dispersion is not None and (not math.isfinite(self.max_dispersion) or self.max_dispersion < 0):
            raise ValueError('invalid dispersion threshold')
        if self.basket_min_dates < 3 or (not 0 < self.basket_min_coverage <= 1):
            raise ValueError('invalid sample-count/coverage requirements')
        if pd.Timestamp(self.entry_start) > pd.Timestamp(self.entry_end):
            raise ValueError('entry bounds reversed')
        for name in (
            'entry_start',
            'entry_end',
            'observation_end'
        ):
            value = getattr(self, name)
            if value is not None and (pd.isna(pd.Timestamp(value)) or pd.Timestamp(value) != pd.Timestamp(value).normalize()):
                raise ValueError('research bounds must be valid calendar dates')
        if self.observation_end is not None and pd.Timestamp(self.observation_end) < pd.Timestamp(self.entry_start):
            raise ValueError('observation cutoff precedes first entry')
        if not self.horizons or any((h not in (30, 60, 91) for h in self.horizons)):
            raise ValueError('supported tenors: 30/60/91')
        if self.rate_unit not in ('percent', 'decimal', 'kevin'):
            raise ValueError('explicit rate_unit required')
        if self.rate_compounding != 'continuous' or self.day_count != 365:
            raise ValueError('baseline requires continuous ACT/365')
        if self.history_months != 36:
            raise ValueError('baseline MIV requires 36 completed months')
        if self.bootstrap_repetitions < 99 or self.min_sessions < 3:
            raise ValueError('insufficient inference/session settings')
        if not all((0 < f <= 1 for f in self.basket_fractions + self.basket_weight_thresholds)):
            raise ValueError('invalid basket fraction')
        if self.basket_reference not in ('full', 'reference_option_feasible'):
            raise ValueError('unsupported basket reference')
        if self.information_lag_sessions < 1:
            raise ValueError('invalid timing settings')
        for i in self.indices:
            s = IndexSpec(**i)
            if s.secid is not None and (not isinstance(s.secid, int) or isinstance(s.secid, bool) or s.secid <= 0):
                raise ValueError('SECID must be a positive integer')
            if s.weighting not in ('market_cap', 'price', 'equal'):
                raise ValueError('unsupported weighting')
            if s.return_column not in ('dlyret', 'dlyretx'):
                raise ValueError('unsupported stock return column')
        return self

    def require_rate_certification(self):
        """Gate certified rate conversion on documented provider conventions."""
        from .errors import DataError
        if self.rate_unit == 'kevin':
            return
        # User explicitly selected Kevin's original normalization rule.
        if not self.rate_convention_confirmed or not self.rate_confirmation_source.strip():
            raise DataError(
                'RATE_CONVENTION_UNCERTIFIED',
                'Document vendor units and continuous ACT/365 convention in config.'
            )

    @classmethod
    def read(cls, path):
        """Load serialized configuration or inputs through their declared schema."""
        return cls(**json.loads(Path(path).read_text())).validate()


    def specs(self):
        """Return enabled index specifications only."""
        return [IndexSpec(**i) for i in self.indices if i.get('enabled', True)]

    def entry_grid(self, calendar):
        """Select entry sessions within the configured observation bounds."""
        dates = pd.DatetimeIndex(calendar)
        end = min(pd.Timestamp(self.entry_end), pd.Timestamp(self.observation_end)) if self.observation_end else pd.Timestamp(self.entry_end)
        return dates[(dates >= pd.Timestamp(self.entry_start)) & (dates <= end)]
