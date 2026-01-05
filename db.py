# 数据库连接模块

import pymssql

DB_CONFIG = {
    "server": "localhost",      # 或 IP
    "user": "sa",               # SQL Server 用户
    "password": "123456",
    "database": "FleetDB",
    "charset": "utf8"
}

def get_connection():
    return pymssql.connect(
        server=DB_CONFIG["server"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"]
    )
