from core.utils import classify_temperature


def test_classify_ok_when_below_both_thresholds():
    assert classify_temperature(avg_temp=20.0, max_temp=25.0) == "ok"


def test_classify_warning_when_avg_temp_at_or_above_threshold():
    assert classify_temperature(avg_temp=28.0, max_temp=29.0) == "warning"


def test_classify_critical_when_max_temp_at_or_above_threshold():
    assert classify_temperature(avg_temp=20.0, max_temp=32.0) == "critical"


def test_critical_takes_priority_over_warning():
    assert classify_temperature(avg_temp=28.0, max_temp=32.0) == "critical"
