from pydantic_settings import BaseSettings, SettingsConfigDict


class CloudSettings(BaseSettings):
    citibank_user_id: str = ""
    citibank_password: str = ""
    project_id: str = ""
    secret_id: str = ""
    trusted_user_emails: list = []
    otp_email_subject: str = ""
    bucket_name: str = ""
    from_email: str
    to_email: str

    model_config = SettingsConfigDict(env_file=".env", extra="allow")


settings = CloudSettings()
