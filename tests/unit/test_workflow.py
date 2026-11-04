"""Configuration, provenance and publication checks; no licensed data or model training."""
import importlib
import json
from pathlib import Path

import pytest

from src.research.dataset import read_config, inputs
from src.research.workflow import check_models, model_code


def test_only_four_user_selected_equations_and_fixed_split():
    cfg = read_config()
    assert list(cfg['specifications']) == ['ic_only', 'baseline', 'expanded', 'requested']
    assert len(cfg['specifications']['expanded']) == 5
    assert cfg['training_end'] == '2022-12-31'
    assert cfg['evaluation_start'] == '2023-01-01'


@pytest.mark.parametrize('field,value,reason', [
    ('training_end', '2024-01-01', 'SPLIT'),
    ('downside_sessions', 300, 'HISTORY'),
    ('minimum_training_rows', 4, 'TRAINING'),
    ('specifications', {'ic_only': ['ic']}, 'EQUATIONS'),
])
def test_invalid_research_settings_fail_before_any_execution(tmp_path, field, value, reason):
    cfg = read_config()
    cfg[field] = value
    path = tmp_path / 'config.json'
    path.write_text(json.dumps(cfg))
    with pytest.raises(ValueError, match=reason):
        read_config(path)


def test_stale_features_are_rejected_before_reading_observations(tmp_path, monkeypatch):
    from src.research import dataset
    (tmp_path / 'dataset_manifest.json').write_text(json.dumps({'fingerprint': {'configuration': 'old'}}))
    monkeypatch.setattr(dataset, 'fingerprint', lambda cfg: {'configuration': 'new'})
    with pytest.raises(ValueError, match='STALE_PREPARED'):
        inputs({'output_root': str(tmp_path), 'dataset_root': str(tmp_path)})


def test_stale_models_cannot_be_reported_as_current(tmp_path):
    from src.research.inputs import sha256
    (tmp_path / 'models').mkdir()
    panel = tmp_path / 'dataset.parquet'
    panel.write_bytes(b'only a checksum fixture, not observations')
    cfg = {'output_root': str(tmp_path), 'dataset_root': str(tmp_path), 'training_end': '2022-12-31'}
    (tmp_path / 'models.json').write_text(json.dumps({'manifest': {'prepared_panel_sha256': sha256(panel), 'config': cfg, 'model_code': model_code()}}))
    check_models(cfg)
    panel.write_bytes(b'changed checksum fixture')
    with pytest.raises(ValueError, match='STALE_FITTED'):
        check_models(cfg)


def test_importing_research_modules_never_opens_WRDS(monkeypatch):
    import wrds
    def forbidden(*args, **kwargs):
        raise AssertionError('Unexpected live connection during import')
    monkeypatch.setattr(wrds, 'Connection', forbidden)
    for path in Path('src/research').glob('*.py'):
        importlib.import_module('src.research.' + path.stem)


def test_changed_prepared_panel_fails_before_parquet_read(tmp_path, monkeypatch):
    from src.research import dataset
    panel = tmp_path / 'dataset.parquet'
    panel.write_bytes(b'corrupted checksum fixture')
    (tmp_path / 'dataset_manifest.json').write_text(json.dumps({'fingerprint': {}, 'prepared_panel_sha256': 'old'}))
    monkeypatch.setattr(dataset, 'fingerprint', lambda cfg: {})
    with pytest.raises(ValueError, match='CHANGED_PREPARED'):
        inputs({'output_root': str(tmp_path), 'dataset_root': str(tmp_path)})


def test_failed_fit_preserves_the_previous_complete_model_set(tmp_path, monkeypatch):
    from src.research import workflow
    import pandas as pd
    cfg = {'output_root': str(tmp_path), 'dataset_root': str(tmp_path)}
    models = tmp_path / 'models'
    models.mkdir()
    existing = models / 'original.json'
    existing.write_text('previous complete model')
    monkeypatch.setattr(workflow, 'read_config', lambda path: cfg)
    monkeypatch.setattr(workflow, 'inputs', lambda settings: (pd.DataFrame(), pd.DatetimeIndex([])))
    def fail(frame, calendar, settings, target):
        target.mkdir()
        (target / 'partial.json').write_text('incomplete')
        raise ValueError('deliberate failure injection')
    monkeypatch.setattr(workflow, 'run_models', fail)
    with pytest.raises(ValueError, match='deliberate'):
        workflow.run('fit')
    assert existing.read_text() == 'previous complete model'
    assert not (models / 'partial.json').exists()
    records = list((tmp_path / 'runs').glob('*.json'))
    assert len(records) == 1 and json.loads(records[0].read_text())['status'] == 'FAIL'


def test_undersampled_report_correlations_are_unavailable_without_warnings():
    import numpy as np
    import pandas as pd
    import warnings
    from src.research.reporting import _correlation
    with warnings.catch_warnings():
        warnings.simplefilter('error')
        assert np.isnan(_correlation(pd.DataFrame({'x':[1.], 'y':[2.]}), 'x', 'y'))
        assert np.isnan(_correlation(pd.DataFrame({'x':[1.,1.], 'y':[2.,3.]}), 'x', 'y'))
        assert _correlation(pd.DataFrame({'x':[1.,2.], 'y':[2.,4.]}), 'x', 'y') == pytest.approx(1.)
