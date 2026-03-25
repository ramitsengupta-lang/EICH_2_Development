from __future__ import annotations

from m8_report_builder.report_builder import build_outcome_strength


def test_outcome_fallback_parses_salary_with_currency_and_commas() -> None:
    result = build_outcome_strength({
        "average_salary": "INR 1,200,000 per annum",
        "placement_rate": 85,
    })

    assert result["average_salary_lpa"] == 12.0
    assert result["placement_rate"] == 85.0
    assert result["salary_inferred"] is False


def test_outcome_fallback_normalizes_fractional_placement_and_infers_salary_once() -> None:
    result = build_outcome_strength({
        "placement": 0.82,
        "average_salary": None,
    })

    assert result["placement_rate"] == 82.0
    assert result["average_salary_lpa"] == 8.2
    assert result["salary_inferred"] is True


def test_outcome_fallback_preserves_existing_lpa_and_rejects_invalid_values() -> None:
    already_lpa = build_outcome_strength({
        "average_salary_lpa": "12 LPA",
        "placement_rate": "92%",
    })
    invalid_negative_salary = build_outcome_strength({
        "average_salary": "-500000",
        "placement_rate": 75,
    })
    invalid_placement = build_outcome_strength({
        "average_salary": None,
        "placement_rate": 140,
    })

    assert already_lpa["average_salary_lpa"] == 12.0
    assert already_lpa["placement_rate"] == 92.0
    assert already_lpa["salary_inferred"] is False

    assert invalid_negative_salary["average_salary_lpa"] == 7.5
    assert invalid_negative_salary["salary_inferred"] is True

    assert invalid_placement["placement_rate"] is None
    assert invalid_placement["average_salary_lpa"] is None
    assert invalid_placement["salary_inferred"] is False
