from feedback import db, User  # 从 feedback.py 导入 db 和模型
from app import app  # 导入 Flask 应用

# 在 Flask 应用上下文中操作数据库
with app.app_context():
    # 创建所有表（如果尚未创建）
    db.create_all()

    # 查询 User 表中的所有记录
    users = User.query.all()
    print(f"Number of users: {len(users)}")

    # 打印所有用户
    for user in users:
        print(f"ID: {user.id}, Username: {user.username}")
