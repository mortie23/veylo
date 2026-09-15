import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Set test environment variables before importing app modules
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["VEYLO_CLOUD_RUN_API_KEY"] = "test-secret-api-key"
os.environ["GCP_PROJECT_ID"] = "test-gcp-project"

from config import get_settings
from database import get_db
from main import app
from models.orm import Base, DataContract, Entity, Attribute, CodeManagement, DataQuality
from services.contract_service import ContractService

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(autouse=True)
def setup_database():
    """Create in-memory SQLite tables before each test and drop them after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db_session():
    """Yields a test database session."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """FastAPI TestClient with overridden database dependency."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_customer_returns_contract(db_session) -> DataContract:
    """
    Creates a sample 'customer-returns' contract matching docs/DATA_VALIDATION_WAREHOUSE.md:
    Columns:
    - return_id (INT64, PK, non-null)
    - return_date (DATE, non-null)
    - country_code (STRING, code set: ISO_3166_COUNTRY)
    - customer_email (STRING, DQ REGEX email)
    - refund_amount (FLOAT64, DQ RANGE 0 to 10000)
    """
    contract = ContractService.create_contract(
        db=db_session,
        contract_name="customer-returns",
        contract_version="v2.1.0",
        data_steward_email="steward@acme.com",
    )
    entity = ContractService.add_entity(
        db=db_session,
        data_contract_id=contract.data_contract_id,
        src_entity_name="returns_detail",
        tgt_entity_name="returns_detail",
        tgt_dataset="veylo_bronze",
    )

    # return_id
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Return ID",
        tgt_field_name="return_id",
        tgt_data_type="INT64",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )

    # return_date
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Return Date",
        tgt_field_name="return_date",
        tgt_data_type="DATE",
        is_nullable=False,
        ordinal_position=1,
    )

    # country_code
    country_attr = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Country",
        tgt_field_name="country_code",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=2,
    )
    ContractService.add_code_management(
        db=db_session,
        attribute_id=country_attr.attribute_id,
        source_code="AUS",
        target_code="AU",
        code_system_name="ISO_3166_COUNTRY",
    )
    ContractService.add_code_management(
        db=db_session,
        attribute_id=country_attr.attribute_id,
        source_code="USA",
        target_code="US",
        code_system_name="ISO_3166_COUNTRY",
    )

    # customer_email
    email_attr = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Email",
        tgt_field_name="customer_email",
        tgt_data_type="STRING",
        is_nullable=True,
        ordinal_position=3,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=email_attr.attribute_id,
        rule_type="REGEX",
        rule_value=r"^[^@]+@[^@]+\.[^@]+$",
        error_message_template="Field {field} must be a valid email format.",
    )

    # refund_amount
    amount_attr = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="Amount",
        tgt_field_name="refund_amount",
        tgt_data_type="FLOAT64",
        is_nullable=True,
        ordinal_position=4,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=amount_attr.attribute_id,
        rule_type="RANGE",
        rule_value='{"min": 0, "max": 10000}',
        error_message_template="Field {field} value must be between 0 and 10000.",
    )

    return ContractService.get_active_contract(db_session, "customer-returns", "v2.1.0")


@pytest.fixture
def sample_nfl_teams_contract(db_session) -> DataContract:
    """Creates a sample 'nfl-teams' contract matching team_lookup.csv."""
    contract = ContractService.create_contract(
        db=db_session,
        contract_name="nfl-teams",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
    )
    entity = ContractService.add_entity(
        db=db_session,
        data_contract_id=contract.data_contract_id,
        src_entity_name="team_lookup",
        tgt_entity_name="nfl_team_lookup",
        tgt_dataset="veylo_bronze",
    )

    # 1. TEAM_ID
    a_id = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="TEAM_ID",
        tgt_field_name="team_id",
        tgt_data_type="INT64",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_id.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 1, "max": 32}',
        error_message_template="Team ID must be between 1 and 32.",
    )

    # 2. TEAM_LONG
    a_name = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="TEAM_LONG",
        tgt_field_name="team_name",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=1,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_name.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 2, "max": 50}',
        error_message_template="Team name must be between 2 and 50 characters.",
    )

    # 3. TEAM_SHORT
    a_abbr = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="TEAM_SHORT",
        tgt_field_name="team_abbr",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=2,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_abbr.attribute_id,
        rule_type="REGEX",
        severity="ERROR",
        rule_value=r"^[A-Z]{2,3}$",
        error_message_template="Team abbreviation must be 2-3 uppercase letters.",
    )

    # 4. CONFERENCE
    a_conf = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="CONFERENCE",
        tgt_field_name="conference_code",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=3,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_conf.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["AFC", "NFC"]',
        error_message_template="Conference must be either AFC or NFC.",
    )
    ContractService.add_code_management(
        db=db_session,
        attribute_id=a_conf.attribute_id,
        source_code="AFC",
        target_code="AFC",
        code_system_name="NFL_CONFERENCE",
        target_description="American Football Conference",
    )
    ContractService.add_code_management(
        db=db_session,
        attribute_id=a_conf.attribute_id,
        source_code="NFC",
        target_code="NFC",
        code_system_name="NFL_CONFERENCE",
        target_description="National Football Conference",
    )

    # 5. DIVISION (Standardized mapping)
    a_div = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="DIVISION",
        tgt_field_name="division_code",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=4,
    )
    for src, tgt, desc in [
        ("NFC West", "NFC_WEST", "NFC West Division"),
        ("NFC East", "NFC_EAST", "NFC East Division"),
        ("NFC South", "NFC_SOUTH", "NFC South Division"),
        ("NFC North", "NFC_NORTH", "NFC North Division"),
        ("AFC West", "AFC_WEST", "AFC West Division"),
        ("AFC East", "AFC_EAST", "AFC East Division"),
        ("AFC South", "AFC_SOUTH", "AFC South Division"),
        ("AFC North", "AFC_NORTH", "AFC North Division"),
    ]:
        ContractService.add_code_management(
            db=db_session,
            attribute_id=a_div.attribute_id,
            source_code=src,
            target_code=tgt,
            code_system_name="NFL_DIVISION",
            target_description=desc,
        )

    # 6. CREATE_DATE
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="CREATE_DATE",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        is_nullable=True,
        ordinal_position=5,
    )

    # 7. CREATE_USER
    a_user = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="CREATE_USER",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=6,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_user.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 1, "max": 50}',
        error_message_template="Create user must not be blank.",
    )

    return ContractService.get_active_contract(db_session, "nfl-teams", "v1.0.0")


@pytest.fixture
def sample_nfl_venues_contract(db_session) -> DataContract:
    """Creates a sample 'nfl-venues' contract matching venue.csv."""
    contract = ContractService.create_contract(
        db=db_session,
        contract_name="nfl-venues",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
    )
    entity = ContractService.add_entity(
        db=db_session,
        data_contract_id=contract.data_contract_id,
        src_entity_name="venue",
        tgt_entity_name="nfl_venues",
        tgt_dataset="veylo_bronze",
    )

    # venue_id
    a_id = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="venue_id",
        tgt_field_name="venue_id",
        tgt_data_type="INT64",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_id.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 1, "max": 1000}',
        error_message_template="Venue ID must be positive integer.",
    )

    # venue_name
    a_name = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="venue_name",
        tgt_field_name="venue_name",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=1,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_name.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 3, "max": 100}',
        error_message_template="Venue name must be between 3 and 100 characters.",
    )

    # capacity
    a_cap = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="capacity",
        tgt_field_name="capacity",
        tgt_data_type="INT64",
        is_nullable=False,
        ordinal_position=2,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_cap.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 10000, "max": 150000}',
        error_message_template="Stadium capacity must be between 10,000 and 150,000.",
    )

    # surface
    a_surf = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="surface",
        tgt_field_name="surface_type",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=3,
    )
    for src, tgt, desc in [
        ("artificial", "ARTIFICIAL", "Artificial Turf"),
        ("turf", "TURF", "Natural / Hybrid Turf"),
        ("grass", "GRASS", "Natural Grass"),
    ]:
        ContractService.add_code_management(
            db=db_session,
            attribute_id=a_surf.attribute_id,
            source_code=src,
            target_code=tgt,
            code_system_name="VENUE_SURFACE",
            target_description=desc,
        )

    # venue_type
    a_type = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="venue_type",
        tgt_field_name="venue_type",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=4,
    )
    for src, tgt, desc in [
        ("outdoor", "OUTDOOR", "Open Air Stadium"),
        ("dome", "DOME", "Enclosed Fixed Dome"),
        ("retractable_dome", "RETRACTABLE_DOME", "Retractable Roof Stadium"),
    ]:
        ContractService.add_code_management(
            db=db_session,
            attribute_id=a_type.attribute_id,
            source_code=src,
            target_code=tgt,
            code_system_name="VENUE_TYPE",
            target_description=desc,
        )

    # created_date
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="created_date",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        is_nullable=True,
        ordinal_position=5,
    )

    # create_user
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="create_user",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=6,
    )

    return ContractService.get_active_contract(db_session, "nfl-venues", "v1.0.0")


@pytest.fixture
def sample_nfl_weather_contract(db_session) -> DataContract:
    """Creates a sample 'nfl-weather' contract matching weather.csv."""
    contract = ContractService.create_contract(
        db=db_session,
        contract_name="nfl-weather",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
    )
    entity = ContractService.add_entity(
        db=db_session,
        data_contract_id=contract.data_contract_id,
        src_entity_name="weather",
        tgt_entity_name="nfl_game_weather",
        tgt_dataset="veylo_bronze",
    )

    # weather_game_id
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="weather_game_id",
        tgt_field_name="weather_game_id",
        tgt_data_type="INT64",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )

    # game_id
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="game_id",
        tgt_field_name="game_id",
        tgt_data_type="INT64",
        is_nullable=False,
        ordinal_position=1,
    )

    # TEMPERATURE
    a_temp = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="TEMPERATURE",
        tgt_field_name="temperature_f",
        tgt_data_type="INT64",
        is_nullable=False,
        ordinal_position=2,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_temp.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": -30, "max": 130}',
        error_message_template="Game temperature must be between -30°F and 130°F.",
    )

    # WEATHER_CONDITION
    a_cond = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="WEATHER_CONDITION",
        tgt_field_name="weather_condition",
        tgt_data_type="STRING",
        is_nullable=True,
        ordinal_position=3,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_cond.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["Partly Cloudy", "Overcast", "Sunny", "Clear", "Mist", "Light rain", "Rain", "Snow", "Fog"]',
        error_message_template="Weather condition '{value}' is not recognized.",
    )

    # WIND_SPEED
    a_wind = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="WIND_SPEED",
        tgt_field_name="wind_speed_mph",
        tgt_data_type="INT64",
        is_nullable=True,
        ordinal_position=4,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_wind.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 0, "max": 100}',
        error_message_template="Wind speed must be between 0 and 100 mph.",
    )

    # HUMIDITY
    a_hum = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="HUMIDITY",
        tgt_field_name="humidity_pct",
        tgt_data_type="INT64",
        is_nullable=True,
        ordinal_position=5,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_hum.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 0, "max": 100}',
        error_message_template="Humidity percentage must be between 0 and 100.",
    )

    # WIND_DIRECTION
    a_dir = ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="WIND_DIRECTION",
        tgt_field_name="wind_direction",
        tgt_data_type="STRING",
        is_nullable=True,
        ordinal_position=6,
    )
    ContractService.add_data_quality_rule(
        db=db_session,
        attribute_id=a_dir.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]',
        error_message_template="Wind direction '{value}' must be a valid compass direction.",
    )

    # created_date
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="created_date",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        is_nullable=True,
        ordinal_position=7,
    )

    # create_user
    ContractService.add_attribute(
        db=db_session,
        entity_id=entity.entity_id,
        src_field_name="create_user",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        is_nullable=False,
        ordinal_position=8,
    )

    return ContractService.get_active_contract(db_session, "nfl-weather", "v1.0.0")

