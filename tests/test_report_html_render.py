from __future__ import annotations

from contracts.score_data import ScoreData
from contracts.validated_data import RecordState, ValidatedEntityRecord
from m8_report_builder.report_builder import build_report, render_html


def _minimal_entity() -> ValidatedEntityRecord:
    return ValidatedEntityRecord(
        entity_id="T1",
        entity_name="Test University",
        entity_type="UNIVERSITY",
        jurisdiction="IN",
        state=RecordState.VALIDATED,
        pipeline_run_id="run-html-test",
        city="Mumbai",
        year_of_establishment=1985,
        regulatory_body="UGC",
        naac_grade="A",
    )


def _minimal_score() -> ScoreData:
    return ScoreData(
        pipeline_run_id="run-html-test",
        entity_id="T1",
        final_score=75.0,
        financial_strength_score=80.0,
        outcome_strength_score=65.0,
        rating="B",
        gatekeeper_status="AA",
        score_explanation=["Financial data available", "Outcome data partial"],
        contributing_fields={"financial_strength_score": "kmp_list[].compensation[].compensation_value"},
    )


def _full_entity() -> ValidatedEntityRecord:
    return ValidatedEntityRecord(
        entity_id="T2",
        entity_name="Grand Institute of Technology",
        entity_type="UNIVERSITY",
        jurisdiction="IN",
        state=RecordState.VALIDATED,
        pipeline_run_id="run-html-full",
        city="Chennai",
        year_of_establishment=1972,
        regulatory_body="AICTE",
        naac_grade="A++",
        sanctioned_intake=1200,
        main_programs=["B.Tech CSE", "MBA", "M.Tech"],
        registered_address="123 College Road, Chennai - 600001",
        governing_body_name="Grand Education Trust",
        governing_body_type="Trust",
        governing_body_year_established=1970,
        governed_institutions=["Grand Institute of Technology", "Grand Polytechnic"],
        governing_body_trustees=[
            {"name": "Dr. R. Sharma", "role": "Chairman"},
            {"name": "Mrs. P. Iyer", "role": "Secretary"},
        ],
        placement_rate=87.5,
        median_salary_lpa=9.2,
        higher_studies="15% pursue higher studies",
        top_recruiters=["TCS", "Infosys", "Wipro", "Cognizant"],
        banking_opportunities=[
            {
                "indicator_type": "Salary Disbursement",
                "description": "Salary accounts for placed students",
                "potential_value": "High",
            }
        ],
        associated_entities=[
            {
                "name": "Grand Polytechnic",
                "entity_type": "Polytechnic",
                "confidence": 0.8,
                "relationship": "Sister Institution",
                "evidence": "Common trust governance confirmed.",
            }
        ],
        relationship_map=[
            {"source": "Grand Institute of Technology", "relationship": "is affiliated with", "target": "Anna University"},
        ],
        institution_network=[
            {"name": "Anna University", "type": "University", "relationship": "Affiliation"},
        ],
        report_accuracy_overall=88.5,
        report_accuracy_sections={
            "Governing Body": 100.0,
            "Institution Profile": 90.0,
            "EICH Score Summary": 85.0,
            "Outcome Strength": 80.0,
        },
    )


def _full_score() -> ScoreData:
    return ScoreData(
        pipeline_run_id="run-html-full",
        entity_id="T2",
        final_score=88.5,
        financial_strength_score=90.0,
        outcome_strength_score=84.0,
        rating="A",
        gatekeeper_status="AA",
        financial_model_used="Proxy Financial Model",
        accreditation_multiplier=1.05,
        vintage_multiplier=1.0,
        city_multiplier=1.0,
        score_explanation=[
            "Top-tier NAAC accreditation (A++)",
            "Strong financial strength indicators",
            "Strong outcome performance indicators",
        ],
        contributing_fields={"financial_strength_score": "kmp_list[].compensation[].compensation_value"},
    )


def test_render_html_returns_string_with_entity_name() -> None:
    report_dict = build_report(_minimal_entity(), _minimal_score())
    html = render_html(report_dict)

    assert isinstance(html, str)
    assert "Test University" in html


def test_render_html_includes_score() -> None:
    report_dict = build_report(_minimal_entity(), _minimal_score())
    html = render_html(report_dict)

    assert "75.0" in html


def test_render_html_includes_all_major_sections() -> None:
    report_dict = build_report(_full_entity(), _full_score())
    html = render_html(report_dict)

    required_sections = [
        "Governing Body",
        "EICH Score Summary",
        "Key Managerial Persons",
        "Associated Entities",
        "Relationship Map",
        "Institution Profile",
        "Outcome Strength",
        "Banking Opportunity Indicators",
        "Institution Network",
        "Report Accuracy",
    ]
    for section in required_sections:
        assert section in html, f"Missing section in rendered HTML: {section}"
