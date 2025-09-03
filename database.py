import os
from sqlalchemy import create_engine

# 读取 Render 数据库的环境变量
DATABASE_URL = os.getenv("DATABASE_URL")

# 如果本地开发未设置 DATABASE_URL，可以提供默认值（可选）
if not DATABASE_URL:
    DATABASE_URL = "postgres://your_user:your_password@your_external_host:your_port/your_db"

# 创建数据库连接引擎
engine = create_engine(DATABASE_URL, echo=True)

# 你也可以在这里创建数据库会话管理
from sqlalchemy.orm import sessionmaker
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 方便外部调用
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
