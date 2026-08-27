from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """App configuration, overridable via environment or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "TinyProtocol"
    stage: str = "dev"
    table_name: str = "TinyProtocol-dev"

    jwt_secret: str = "dev-secret-change-me"
    jwt_expiry_days: int = 90

    # Enables the AI assistant endpoints when set.
    openai_api_key: str = ""
    assistant_model: str = "gpt-5.5"

    # Care documents pipeline.
    docs_bucket: str = ""
    worker_function_name: str = ""
    max_doc_bytes: int = 15 * 1024 * 1024

    # MyChart (Epic patient-access FHIR). Endpoints stay 503 until the Epic
    # client id (from fhir.epic.com app registration) is configured.
    mychart_client_id: str = ""
    mychart_redirect_url: str = ""  # https://<api>/v1/mychart/callback
    mychart_fhir_base: str = "https://epicmobile.luriechildrens.org/Interconnect-FHIRPRD/api/FHIR/R4/"
    # USCDI-only scopes: adding non-USCDI APIs (e.g. Communication for MyChart
    # messages) disqualifies the app from Epic's AUTOMATIC client-id
    # distribution to health systems — the sync still probes Communication and
    # degrades gracefully if the token lacks it.
    mychart_scopes: str = (
        "openid fhirUser offline_access "
        "patient/Patient.read patient/Observation.read "
        "patient/DocumentReference.read patient/Binary.read"
    )

    # Point at DynamoDB Local for development (e.g. http://localhost:8000).
    dynamo_endpoint_url: str | None = None

    # "*" is fine while it's just the two of us.
    cors_origins: str = "*"


settings = Settings()
