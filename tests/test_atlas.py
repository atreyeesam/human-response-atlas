import pandas as pd
import pytest
from atlas import gaps, validate

def test_demo_gap_labels():
    df = pd.read_csv('data/demo_evidence.csv')
    result = gaps(df)
    assert result.loc[result.record_id.eq('DEMO-003'), 'coverage'].iloc[0] == 'No records in loaded dataset'
    assert result.loc[result.record_id.eq('DEMO-002'), 'coverage'].iloc[0] == 'Sparse in loaded dataset'
    assert result.loc[result.record_id.eq('DEMO-001'), 'coverage'].iloc[0] == 'Records present in loaded dataset'

def test_reject_negative_counts():
    df = pd.read_csv('data/demo_evidence.csv')
    df.loc[0, 'study_count'] = -1
    with pytest.raises(ValueError):
        validate(df)
