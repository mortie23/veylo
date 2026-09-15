import os
from pathlib import Path
import pandas as pd
import pytest

from services.validation_service import ValidationEngine

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "nfl"


def test_validate_nfl_teams_real_csv(sample_nfl_teams_contract):
    """Tests that all 32 rows from team_lookup.csv validate and transform cleanly."""
    csv_path = FIXTURES_DIR / "team_lookup.csv"
    assert csv_path.exists(), f"Missing fixture file: {csv_path}"

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, skipinitialspace=True)
    assert len(df) == 32

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_teams_contract)

    assert result.is_valid is True
    assert result.status == "Processed"
    assert result.total_rows == 32
    assert result.failed_rows_count == 0
    assert len(result.errors) == 0
    assert transformed_df is not None

    # Check renamed columns
    expected_cols = [
        "team_id",
        "team_name",
        "team_abbr",
        "conference_code",
        "division_code",
        "created_at",
        "created_by",
    ]
    for col in expected_cols:
        assert col in transformed_df.columns

    # Verify division code management remapping
    divisions = set(transformed_df["division_code"])
    assert "NFC_WEST" in divisions
    assert "AFC_EAST" in divisions
    assert "NFC_NORTH" in divisions
    assert "AFC_SOUTH" in divisions
    assert len(divisions) == 8

    # Verify team_id type casting
    assert str(transformed_df["team_id"].dtype) == "Int64"
    assert transformed_df["team_id"].min() == 1
    assert transformed_df["team_id"].max() == 32


def test_validate_nfl_teams_invalid_division(sample_nfl_teams_contract):
    """Tests that a non-standard division (e.g. 'NFC Central') triggers CODE_NOT_FOUND."""
    df = pd.DataFrame([
        {
            "TEAM_ID": "1",
            "TEAM_LONG": "Seahawks",
            "TEAM_SHORT": "SEA",
            "CONFERENCE": "NFC",
            "DIVISION": "NFC Central",  # Historical/Invalid in modern schema
            "CREATE_DATE": "2020-09-11 13:30",
            "CREATE_USER": "mortimer",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_teams_contract)

    assert result.is_valid is False
    assert result.status == "Failed"
    assert transformed_df is None
    assert any(e.error_code == "CODE_NOT_FOUND" for e in result.errors)
    assert any("NFC Central" in e.error_message for e in result.errors)


def test_validate_nfl_teams_invalid_abbr_regex(sample_nfl_teams_contract):
    """Tests that lowercase or long team abbreviations fail the REGEX rule."""
    df = pd.DataFrame([
        {
            "TEAM_ID": "1",
            "TEAM_LONG": "Seahawks",
            "TEAM_SHORT": "SEATTLE",  # > 3 chars
            "CONFERENCE": "NFC",
            "DIVISION": "NFC West",
            "CREATE_DATE": "2020-09-11 13:30",
            "CREATE_USER": "mortimer",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_teams_contract)

    assert result.is_valid is False
    assert transformed_df is None
    assert any(e.error_code == "DQ_RULE_FAILED" for e in result.errors)
    assert any("2-3 uppercase letters" in e.error_message for e in result.errors)


def test_validate_nfl_teams_out_of_range_id(sample_nfl_teams_contract):
    """Tests that team_id outside 1..32 fails the RANGE rule."""
    df = pd.DataFrame([
        {
            "TEAM_ID": "99",  # Outside 1..32
            "TEAM_LONG": "Seahawks",
            "TEAM_SHORT": "SEA",
            "CONFERENCE": "NFC",
            "DIVISION": "NFC West",
            "CREATE_DATE": "2020-09-11 13:30",
            "CREATE_USER": "mortimer",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_teams_contract)

    assert result.is_valid is False
    assert transformed_df is None
    assert any(e.error_code == "DQ_RULE_FAILED" for e in result.errors)
    assert any("between 1 and 32" in e.error_message for e in result.errors)


def test_validate_nfl_venues_real_csv(sample_nfl_venues_contract):
    """Tests that all 32 venues from venue.csv validate and transform cleanly."""
    csv_path = FIXTURES_DIR / "venue.csv"
    assert csv_path.exists(), f"Missing fixture file: {csv_path}"

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, skipinitialspace=True)
    df.columns = [c.strip('"') for c in df.columns]
    assert len(df) == 32

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_venues_contract)

    assert result.is_valid is True
    assert result.status == "Processed"
    assert result.total_rows == 32
    assert transformed_df is not None

    # Check surface code mapping
    surfaces = set(transformed_df["surface_type"])
    assert surfaces.issubset({"ARTIFICIAL", "TURF", "GRASS"})

    # Check venue type code mapping
    venue_types = set(transformed_df["venue_type"])
    assert venue_types.issubset({"OUTDOOR", "DOME", "RETRACTABLE_DOME"})


def test_validate_nfl_venues_capacity_out_of_range(sample_nfl_venues_contract):
    """Tests that stadium capacity < 10000 fails RANGE validation."""
    df = pd.DataFrame([
        {
            "venue_id": "1",
            "venue_name": "High School Field",
            "capacity": "500",  # Below min 10000
            "surface": "turf",
            "venue_type": "outdoor",
            "created_date": "2018-10-15 07:04:20",
            "create_user": "mortimer",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_venues_contract)

    assert result.is_valid is False
    assert any(e.error_code == "DQ_RULE_FAILED" for e in result.errors)
    assert any("10,000" in e.error_message for e in result.errors)


def test_validate_nfl_weather_real_csv(sample_nfl_weather_contract):
    """Tests that all 116 weather records from weather.csv validate cleanly."""
    csv_path = FIXTURES_DIR / "weather.csv"
    assert csv_path.exists(), f"Missing fixture file: {csv_path}"

    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, skipinitialspace=True)
    assert len(df) == 116

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_weather_contract)

    assert result.is_valid is True
    assert result.status == "Processed"
    assert result.total_rows == 116
    assert transformed_df is not None
    assert str(transformed_df["temperature_f"].dtype) == "Int64"
    assert str(transformed_df["humidity_pct"].dtype) == "Int64"


def test_validate_nfl_weather_invalid_temp(sample_nfl_weather_contract):
    """Tests that temperature outside -30..130 fails RANGE validation."""
    df = pd.DataFrame([
        {
            "weather_game_id": "1",
            "game_id": "61",
            "TEMPERATURE": "250",  # Unrealistic temp
            "WEATHER_CONDITION": "Sunny",
            "WIND_SPEED": "10",
            "HUMIDITY": "50",
            "WIND_DIRECTION": "NE",
            "created_date": "2018-10-15 07:05:52",
            "create_user": "mortimer",
        }
    ])

    engine = ValidationEngine()
    result, transformed_df = engine.validate(df, sample_nfl_weather_contract)

    assert result.is_valid is False
    assert any(e.error_code == "DQ_RULE_FAILED" for e in result.errors)
    assert any("-30" in e.error_message for e in result.errors)
