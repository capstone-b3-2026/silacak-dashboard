from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql://silacak:silacak@localhost:5432/silacak"

    # Parameter Auto-SOS, sengaja dibuat configurable (bukan hardcode)
    # karena radius & window perlu dikalibrasi ulang pakai data GPS
    # asli di lapangan (akurasi GPS di bawah kanopi bisa drift 10-30m).
    stagnant_window_minutes: int = 180
    stagnant_radius_m: float = 50.0
    stagnant_check_interval_minutes: int = 2

    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://localhost:8080",
    ]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
