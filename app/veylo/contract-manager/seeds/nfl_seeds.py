"""
NFL Reference Data Contracts Seeder for Veylo.
Provides data contract specifications for:
1. nfl-teams (team_lookup.csv)
2. nfl-venues (venue.csv)
3. nfl-weather (weather.csv)
"""
import logging
from sqlalchemy.orm import Session
from models.orm import Attribute, CodeManagement, DataContract, DataQuality, Entity

logger = logging.getLogger(__name__)


def seed_nfl_teams_contract(db: Session, force: bool = False) -> DataContract:
    """Seeds the nfl-teams data contract specification based on team_lookup.csv."""
    existing = db.query(DataContract).filter_by(
        contract_name="nfl-teams",
        contract_version="v1.0.0",
    ).first()
    if existing:
        if not force:
            logger.info("[Seed] Contract 'nfl-teams' (v1.0.0) already exists. Skipping.")
            return existing
        db.delete(existing)
        db.flush()

    logger.info("[Seed] Creating 'nfl-teams' (v1.0.0) contract...")
    contract = DataContract(
        contract_name="nfl-teams",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
        is_active=True,
    )
    db.add(contract)
    db.flush()

    entity = Entity(
        data_contract_id=contract.data_contract_id,
        src_entity_name="team_lookup",
        tgt_entity_name="nfl_team_lookup",
        tgt_dataset="veylo_bronze",
    )
    db.add(entity)
    db.flush()

    # 1. TEAM_ID (PK, 1-32 range)
    a_id = Attribute(
        entity_id=entity.entity_id,
        src_field_name="TEAM_ID",
        tgt_field_name="team_id",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )
    db.add(a_id)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_id.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 1, "max": 32}',
        error_message_template="Team ID must be between 1 and 32",
    ))

    # 2. TEAM_LONG (Team name)
    a_name = Attribute(
        entity_id=entity.entity_id,
        src_field_name="TEAM_LONG",
        tgt_field_name="team_name",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=1,
    )
    db.add(a_name)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_name.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 2, "max": 50}',
        error_message_template="Team name must be between 2 and 50 characters",
    ))

    # 3. TEAM_SHORT (2-3 letter abbreviation)
    a_abbr = Attribute(
        entity_id=entity.entity_id,
        src_field_name="TEAM_SHORT",
        tgt_field_name="team_abbr",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=2,
    )
    db.add(a_abbr)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_abbr.attribute_id,
        rule_type="REGEX",
        severity="ERROR",
        rule_value=r"^[A-Z]{2,3}$",
        error_message_template="Team abbreviation must be 2 to 3 uppercase letters (e.g. SEA, GB, NO)",
    ))

    # 4. CONFERENCE (AFC / NFC)
    a_conf = Attribute(
        entity_id=entity.entity_id,
        src_field_name="CONFERENCE",
        tgt_field_name="conference_code",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=3,
    )
    db.add(a_conf)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_conf.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["AFC", "NFC"]',
        error_message_template="Conference must be either AFC or NFC",
    ))
    for src, desc in [
        ("AFC", "American Football Conference"),
        ("NFC", "National Football Conference"),
    ]:
        db.add(CodeManagement(
            attribute_id=a_conf.attribute_id,
            code_system_name="NFL_CONFERENCE",
            source_code=src,
            target_code=src,
            target_description=desc,
        ))

    # 5. DIVISION (8 NFL Divisions mapped to standardized codes)
    a_div = Attribute(
        entity_id=entity.entity_id,
        src_field_name="DIVISION",
        tgt_field_name="division_code",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=4,
    )
    db.add(a_div)
    db.flush()
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
        db.add(CodeManagement(
            attribute_id=a_div.attribute_id,
            code_system_name="NFL_DIVISION",
            source_code=src,
            target_code=tgt,
            target_description=desc,
        ))

    # 6. CREATE_DATE (Timestamp)
    a_date = Attribute(
        entity_id=entity.entity_id,
        src_field_name="CREATE_DATE",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        src_data_type="timestamp",
        is_pk=False,
        is_nullable=True,
        ordinal_position=5,
    )
    db.add(a_date)

    # 7. CREATE_USER
    a_user = Attribute(
        entity_id=entity.entity_id,
        src_field_name="CREATE_USER",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=6,
    )
    db.add(a_user)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_user.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 1, "max": 50}',
        error_message_template="Create user must not be blank",
    ))

    return contract


def seed_nfl_venues_contract(db: Session, force: bool = False) -> DataContract:
    """Seeds the nfl-venues data contract specification based on venue.csv."""
    existing = db.query(DataContract).filter_by(
        contract_name="nfl-venues",
        contract_version="v1.0.0",
    ).first()
    if existing:
        if not force:
            logger.info("[Seed] Contract 'nfl-venues' (v1.0.0) already exists. Skipping.")
            return existing
        db.delete(existing)
        db.flush()

    logger.info("[Seed] Creating 'nfl-venues' (v1.0.0) contract...")
    contract = DataContract(
        contract_name="nfl-venues",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
        is_active=True,
    )
    db.add(contract)
    db.flush()

    entity = Entity(
        data_contract_id=contract.data_contract_id,
        src_entity_name="venue",
        tgt_entity_name="nfl_venues",
        tgt_dataset="veylo_bronze",
    )
    db.add(entity)
    db.flush()

    # venue_id
    a_id = Attribute(
        entity_id=entity.entity_id,
        src_field_name="venue_id",
        tgt_field_name="venue_id",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )
    db.add(a_id)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_id.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 1, "max": 1000}',
        error_message_template="Venue ID must be a positive integer",
    ))

    # venue_name
    a_name = Attribute(
        entity_id=entity.entity_id,
        src_field_name="venue_name",
        tgt_field_name="venue_name",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=1,
    )
    db.add(a_name)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_name.attribute_id,
        rule_type="LENGTH",
        severity="ERROR",
        rule_value='{"min": 3, "max": 100}',
        error_message_template="Venue name must be between 3 and 100 characters",
    ))

    # capacity
    a_cap = Attribute(
        entity_id=entity.entity_id,
        src_field_name="capacity",
        tgt_field_name="capacity",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=False,
        is_nullable=False,
        ordinal_position=2,
    )
    db.add(a_cap)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_cap.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 10000, "max": 150000}',
        error_message_template="Stadium capacity must be between 10,000 and 150,000",
    ))

    # surface
    a_surf = Attribute(
        entity_id=entity.entity_id,
        src_field_name="surface",
        tgt_field_name="surface_type",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=3,
    )
    db.add(a_surf)
    db.flush()
    for src, tgt, desc in [
        ("artificial", "ARTIFICIAL", "Artificial Turf"),
        ("turf", "TURF", "Natural / Hybrid Turf"),
        ("grass", "GRASS", "Natural Grass"),
    ]:
        db.add(CodeManagement(
            attribute_id=a_surf.attribute_id,
            code_system_name="VENUE_SURFACE",
            source_code=src,
            target_code=tgt,
            target_description=desc,
        ))

    # venue_type
    a_type = Attribute(
        entity_id=entity.entity_id,
        src_field_name="venue_type",
        tgt_field_name="venue_type",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=4,
    )
    db.add(a_type)
    db.flush()
    for src, tgt, desc in [
        ("outdoor", "OUTDOOR", "Open Air Stadium"),
        ("dome", "DOME", "Enclosed Fixed Dome"),
        ("retractable_dome", "RETRACTABLE_DOME", "Retractable Roof Stadium"),
    ]:
        db.add(CodeManagement(
            attribute_id=a_type.attribute_id,
            code_system_name="VENUE_TYPE",
            source_code=src,
            target_code=tgt,
            target_description=desc,
        ))

    # created_date
    a_date = Attribute(
        entity_id=entity.entity_id,
        src_field_name="created_date",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        src_data_type="timestamp",
        is_pk=False,
        is_nullable=True,
        ordinal_position=5,
    )
    db.add(a_date)

    # create_user
    a_user = Attribute(
        entity_id=entity.entity_id,
        src_field_name="create_user",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=6,
    )
    db.add(a_user)

    return contract


def seed_nfl_weather_contract(db: Session, force: bool = False) -> DataContract:
    """Seeds the nfl-weather data contract specification based on weather.csv."""
    existing = db.query(DataContract).filter_by(
        contract_name="nfl-weather",
        contract_version="v1.0.0",
    ).first()
    if existing:
        if not force:
            logger.info("[Seed] Contract 'nfl-weather' (v1.0.0) already exists. Skipping.")
            return existing
        db.delete(existing)
        db.flush()

    logger.info("[Seed] Creating 'nfl-weather' (v1.0.0) contract...")
    contract = DataContract(
        contract_name="nfl-weather",
        contract_version="v1.0.0",
        data_steward_email="nfl-data.steward@veylo.internal",
        is_active=True,
    )
    db.add(contract)
    db.flush()

    entity = Entity(
        data_contract_id=contract.data_contract_id,
        src_entity_name="weather",
        tgt_entity_name="nfl_game_weather",
        tgt_dataset="veylo_bronze",
    )
    db.add(entity)
    db.flush()

    # weather_game_id
    a_wid = Attribute(
        entity_id=entity.entity_id,
        src_field_name="weather_game_id",
        tgt_field_name="weather_game_id",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=True,
        is_nullable=False,
        ordinal_position=0,
    )
    db.add(a_wid)

    # game_id
    a_gid = Attribute(
        entity_id=entity.entity_id,
        src_field_name="game_id",
        tgt_field_name="game_id",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=False,
        is_nullable=False,
        ordinal_position=1,
    )
    db.add(a_gid)

    # TEMPERATURE
    a_temp = Attribute(
        entity_id=entity.entity_id,
        src_field_name="TEMPERATURE",
        tgt_field_name="temperature_f",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=False,
        is_nullable=False,
        ordinal_position=2,
    )
    db.add(a_temp)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_temp.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": -30, "max": 130}',
        error_message_template="Game temperature must be between -30°F and 130°F",
    ))

    # WEATHER_CONDITION
    a_cond = Attribute(
        entity_id=entity.entity_id,
        src_field_name="WEATHER_CONDITION",
        tgt_field_name="weather_condition",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=True,
        ordinal_position=3,
    )
    db.add(a_cond)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_cond.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["Partly Cloudy", "Overcast", "Sunny", "Clear", "Mist", "Light rain", "Rain", "Snow", "Fog"]',
        error_message_template="Weather condition '{value}' is not recognized",
    ))

    # WIND_SPEED
    a_wind = Attribute(
        entity_id=entity.entity_id,
        src_field_name="WIND_SPEED",
        tgt_field_name="wind_speed_mph",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=False,
        is_nullable=True,
        ordinal_position=4,
    )
    db.add(a_wind)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_wind.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 0, "max": 100}',
        error_message_template="Wind speed must be between 0 and 100 mph",
    ))

    # HUMIDITY
    a_hum = Attribute(
        entity_id=entity.entity_id,
        src_field_name="HUMIDITY",
        tgt_field_name="humidity_pct",
        tgt_data_type="INT64",
        src_data_type="integer",
        is_pk=False,
        is_nullable=True,
        ordinal_position=5,
    )
    db.add(a_hum)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_hum.attribute_id,
        rule_type="RANGE",
        severity="ERROR",
        rule_value='{"min": 0, "max": 100}',
        error_message_template="Humidity percentage must be between 0 and 100",
    ))

    # WIND_DIRECTION
    a_dir = Attribute(
        entity_id=entity.entity_id,
        src_field_name="WIND_DIRECTION",
        tgt_field_name="wind_direction",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=True,
        ordinal_position=6,
    )
    db.add(a_dir)
    db.flush()
    db.add(DataQuality(
        attribute_id=a_dir.attribute_id,
        rule_type="ENUM",
        severity="ERROR",
        rule_value='["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]',
        error_message_template="Wind direction '{value}' must be a valid compass abbreviation",
    ))

    # created_date
    a_date = Attribute(
        entity_id=entity.entity_id,
        src_field_name="created_date",
        tgt_field_name="created_at",
        tgt_data_type="TIMESTAMP",
        src_data_type="timestamp",
        is_pk=False,
        is_nullable=True,
        ordinal_position=7,
    )
    db.add(a_date)

    # create_user
    a_user = Attribute(
        entity_id=entity.entity_id,
        src_field_name="create_user",
        tgt_field_name="created_by",
        tgt_data_type="STRING",
        src_data_type="string",
        is_pk=False,
        is_nullable=False,
        ordinal_position=8,
    )
    db.add(a_user)

    return contract


def seed_all_nfl_contracts(db: Session, force: bool = False) -> None:
    """Seeds all NFL reference contracts: teams, venues, weather."""
    seed_nfl_teams_contract(db, force=force)
    seed_nfl_venues_contract(db, force=force)
    seed_nfl_weather_contract(db, force=force)
