from pydantic_settings import BaseSettings


class CreatorSettings(BaseSettings):

    app_db_schema: str = "control"
    storage_container: str = "ppt_creator"


settings = CreatorSettings()
