"""应用配置"""

import os


class Settings:
    APP_NAME: str = "国画临摹AI教练"
    VERSION: str = "0.1.0"
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")


settings = Settings()
