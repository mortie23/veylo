import logging
from typing import Any, Dict, List, Optional
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from config import get_settings
from database import SessionLocal, get_db
from models.orm import Attribute, CodeManagement, DataContract, DataQuality, Entity
from models.validation_result import ValidationErrorDetail, ValidationResult
from models.webhook import WebhookPayload
from services.bigquery_loader import BigQueryLoader
from services.contract_service import ContractService
from services.dataverse_callback import (
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_VALIDATING,
    DataverseCallback,
)
from services.file_parser import FileParser, FileParserError
from services.validation_service import ValidationEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("veylo-validation")

settings = get_settings()

app = FastAPI(
    title="Veylo Data Contract Validation Engine",
    description="Asynchronous cross-cloud data validation and BigQuery bronze loading service",
    version="1.0.0",
)

import secrets

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: Optional[str] = Header(default=None, alias="X-API-Key")) -> None:
    """Validates inbound server-to-server webhook requests using an API key."""
    if not settings.api_key:
        logger.error("Server API key configuration (VEYLO_CLOUD_RUN_API_KEY) is missing.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server API key configuration is missing",
        )
    if not x_api_key or not secrets.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header",
        )


def process_validation_task(payload: WebhookPayload) -> None:
    """
    Background worker task:
    1. Update Dataverse submission status -> Validating
    2. Query contract metadata from veylo_config (BigQuery)
    3. Stream file from Azure Blob Storage via read-only SAS URL
    4. Parse CSV/XLSX into DataFrame
    5. Validate all rows against data contract rules
    6. If errors: update submission -> Failed and insert row-level errors into vey_FileIngestionError
    7. If valid: load data into veylo_bronze target table (WRITE_TRUNCATE) and update status -> Processed
    """
    correlation_id = payload.correlation_id
    dataverse = DataverseCallback()

    logger.info(f"Starting background validation for submission: {correlation_id}")

    try:
        # Step 1: Transition status to Validating (non-fatal if already set by Azure Function)
        try:
            dataverse.update_submission_status(correlation_id, STATUS_VALIDATING, summary="Validation in progress...")
        except Exception as ex:
            logger.warning(f"Submission {correlation_id}: Non-fatal Dataverse callback failure on status update: {ex}")

        # Step 2: Fetch Contract
        with SessionLocal() as db:
            contract = ContractService.get_active_contract(
                db=db,
                contract_name=payload.contract_name,
                contract_version=payload.contract_version,
            )

        if not contract:
            err_msg = f"Unknown or inactive data contract: '{payload.contract_name}' ({payload.contract_version})"
            logger.warning(f"Submission {correlation_id} rejected: {err_msg}")
            dataverse.update_submission_status(correlation_id, STATUS_FAILED, summary=err_msg)
            dataverse.report_errors(
                correlation_id,
                [
                    ValidationErrorDetail(
                        row_number=None,
                        column_name=None,
                        error_code="UNKNOWN_CONTRACT",
                        error_message=err_msg,
                        raw_value=None,
                    )
                ],
            )
            return

        # Step 3: Stream file via SAS URL
        try:
            file_bytes = FileParser.stream_file_from_sas(payload.sas_url)
        except Exception as ex:
            err_msg = f"Failed to stream file from storage: {ex}"
            logger.exception(f"Submission {correlation_id}: {err_msg}")
            dataverse.update_submission_status(correlation_id, STATUS_FAILED, summary=err_msg)
            dataverse.report_errors(
                correlation_id,
                [
                    ValidationErrorDetail(
                        row_number=None,
                        column_name=None,
                        error_code="STORAGE_DOWNLOAD_FAILED",
                        error_message=err_msg,
                        raw_value=None,
                    )
                ],
            )
            return

        # Step 4: Parse file into DataFrame
        try:
            df = FileParser.parse(
                content=file_bytes,
                filename=payload.original_filename,
                mime_type=payload.mime_type,
            )
        except Exception as ex:
            err_msg = f"Failed to parse file: {ex}"
            logger.exception(f"Submission {correlation_id}: {err_msg}")
            dataverse.update_submission_status(correlation_id, STATUS_FAILED, summary=err_msg)
            dataverse.report_errors(
                correlation_id,
                [
                    ValidationErrorDetail(
                        row_number=None,
                        column_name=None,
                        error_code="FILE_PARSE_ERROR",
                        error_message=err_msg,
                        raw_value=None,
                    )
                ],
            )
            return

        # Step 5: Execute Contract Validation
        validator = ValidationEngine()
        result, transformed_df = validator.validate(df=df, contract=contract)

        if not result.is_valid or transformed_df is None:
            logger.info(f"Submission {correlation_id} failed validation: {result.summary}")
            dataverse.update_submission_status(correlation_id, STATUS_FAILED, summary=result.summary)
            dataverse.report_errors(correlation_id, result.errors)
            return

        # Step 6: All rows passed! Load data into BigQuery Bronze Warehouse
        entity = contract.entities[0]
        dataset_name = entity.tgt_dataset or settings.bq_bronze_dataset

        loader = BigQueryLoader(project_id=settings.gcp_project_id)
        target_table_name = loader.get_table_name(contract.contract_name, entity.tgt_entity_name)

        try:
            loader.load_dataframe(
                df=transformed_df,
                dataset_name=dataset_name,
                table_name=target_table_name,
                submission_id=correlation_id,
                attributes=entity.attributes,
            )
        except Exception as ex:
            err_msg = f"BigQuery bronze load failed: {ex}"
            logger.exception(f"Submission {correlation_id}: {err_msg}")
            dataverse.update_submission_status(correlation_id, STATUS_FAILED, summary=err_msg)
            dataverse.report_errors(
                correlation_id,
                [
                    ValidationErrorDetail(
                        row_number=None,
                        column_name=None,
                        error_code="WAREHOUSE_LOAD_ERROR",
                        error_message=err_msg,
                        raw_value=None,
                    )
                ],
            )
            return

        # Step 7: Update Dataverse status -> Processed
        dataverse.update_submission_status(correlation_id, STATUS_PROCESSED, summary=result.summary)
        logger.info(f"Submission {correlation_id} successfully validated and loaded to {dataset_name}.{target_table_name}")

    except Exception as ex:
        logger.exception(f"Unhandled exception during validation of {correlation_id}: {ex}")
        try:
            if dataverse.is_configured:
                dataverse.update_submission_status(
                    correlation_id,
                    STATUS_FAILED,
                    summary=f"Internal validation engine failure: {ex}",
                )
            else:
                logger.error(f"Cannot report failure for {correlation_id} to Dataverse: credentials are not configured.")
        except Exception as dv_ex:
            logger.error(f"Failed to update Dataverse with failure status for {correlation_id}: {dv_ex}")


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"])
def health_check() -> Dict[str, str]:
    """Liveness/readiness probe for Cloud Run."""
    return {"status": "healthy", "service": "data-validation"}


@app.post(
    "/validate",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
    tags=["Validation"],
)
def validate_file(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
) -> Dict[str, Any]:
    """
    Webhook endpoint triggered by Azure Function upon blob creation.
    Acknowledges receipt immediately with HTTP 202 and processes validation asynchronously.
    """
    logger.info(
        f"Received validation request for submission {payload.correlation_id} "
        f"(contract: {payload.contract_name} {payload.contract_version}, file: {payload.original_filename})"
    )
    background_tasks.add_task(process_validation_task, payload)
    return {
        "status": "Accepted",
        "correlationId": payload.correlation_id,
        "message": "Validation pipeline initiated in background task.",
    }


# ---------------------------------------------------------------------------
# Metadata Management Endpoints (Admin / Contract Seeding)
# ---------------------------------------------------------------------------

@app.get(
    "/contracts",
    dependencies=[Depends(verify_api_key)],
    tags=["Contracts"],
)
def list_contracts(
    active_only: bool = True,
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """List data contracts configured in veylo_config."""
    contracts = ContractService.list_contracts(db=db, active_only=active_only)
    return [
        {
            "data_contract_id": c.data_contract_id,
            "contract_name": c.contract_name,
            "contract_version": c.contract_version,
            "data_steward_email": c.data_steward_email,
            "is_active": c.is_active,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "entities": [
                {
                    "entity_id": e.entity_id,
                    "tgt_entity_name": e.tgt_entity_name,
                    "src_entity_name": e.src_entity_name,
                    "tgt_dataset": e.tgt_dataset,
                    "attribute_count": len(e.attributes),
                }
                for e in c.entities
            ],
        }
        for c in contracts
    ]


@app.post(
    "/contracts",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(verify_api_key)],
    tags=["Contracts"],
)
def create_contract(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Seeds or creates a new contract definition with entities and attributes."""
    contract = ContractService.create_contract(
        db=db,
        contract_name=payload["contract_name"],
        contract_version=payload["contract_version"],
        data_steward_email=payload.get("data_steward_email"),
        is_active=payload.get("is_active", True),
    )

    for ent_data in payload.get("entities", []):
        entity = ContractService.add_entity(
            db=db,
            data_contract_id=contract.data_contract_id,
            tgt_entity_name=ent_data["tgt_entity_name"],
            src_entity_name=ent_data.get("src_entity_name"),
            tgt_dataset=ent_data.get("tgt_dataset", "veylo_bronze"),
        )
        for idx, attr_data in enumerate(ent_data.get("attributes", [])):
            attribute = ContractService.add_attribute(
                db=db,
                entity_id=entity.entity_id,
                src_field_name=attr_data["src_field_name"],
                tgt_field_name=attr_data["tgt_field_name"],
                tgt_data_type=attr_data["tgt_data_type"],
                src_data_type=attr_data.get("src_data_type"),
                is_pk=attr_data.get("is_pk", False),
                is_nullable=attr_data.get("is_nullable", True),
                ordinal_position=attr_data.get("ordinal_position", idx),
            )
            for code in attr_data.get("code_management", []):
                ContractService.add_code_management(
                    db=db,
                    attribute_id=attribute.attribute_id,
                    source_code=code["source_code"],
                    code_system_name=code.get("code_system_name"),
                    target_code=code.get("target_code"),
                    target_description=code.get("target_description"),
                )
            for dq in attr_data.get("data_quality", []):
                ContractService.add_data_quality_rule(
                    db=db,
                    attribute_id=attribute.attribute_id,
                    rule_type=dq["rule_type"],
                    severity=dq.get("severity", "ERROR"),
                    rule_value=dq.get("rule_value"),
                    error_message_template=dq.get("error_message_template"),
                )

    return {"data_contract_id": contract.data_contract_id, "status": "Created"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=settings.port, reload=True)
