import os
from dotenv import load_dotenv

load_dotenv()


PROJECT_NAME = "Intelligent Parent Dashboard System"
API_PREFIX = "/api"

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:password@localhost:3306/school_dashboard_db"
)

JWT_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "development-secret-change-this"
)

JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")

JWT_EXPIRE_HOURS = int(
    os.getenv("JWT_EXPIRE_HOURS", "8")
)