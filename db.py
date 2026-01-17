# 数据库连接模块
import pymssql

DB_CONFIG = {
    "server": "localhost",      # 或 IP
    "user": "sa",               # SQL Server 用户
    "password": "123456",
    "database": "FleetDB",
    "charset": "utf8"
}

def get_conn():
    return pymssql.connect(
        server=DB_CONFIG["server"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"]
    )

def fetch_all(sql: str, params=()):
    with get_conn() as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute(sql, params)
        return list(cur.fetchall())

def fetch_one(sql: str, params=()):
    rows = fetch_all(sql, params)
    return rows[0] if rows else None

def execute(sql: str, params=()):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()

def call_proc_sp_driver_performance(driver_id: int, start_dt: str, end_dt: str):
    """
    sp_driver_performance returns TWO result sets:
      1) {driver_id, total_orders}
      2) exception detail list
    """
    with get_conn() as conn:
        cur = conn.cursor(as_dict=True)
        cur.execute("EXEC dbo.sp_driver_performance %s, %s, %s", (driver_id, start_dt, end_dt))

        rs1 = list(cur.fetchall())  # 第一结果集
        summary = rs1[0] if rs1 else None

        rs2 = []
        if cur.nextset():
            rs2 = list(cur.fetchall())  # 第二结果集

        return summary, rs2

def call_proc_sp_fleet_monthly_report(fleet_id: int, year: int, month: int):
    conn = get_conn()
    try:
        cur = conn.cursor(as_dict=True)
        cur.execute("EXEC dbo.sp_fleet_monthly_report %s, %s, %s", (fleet_id, year, month))
        row = cur.fetchone()
        conn.commit()
        return row
    finally:
        conn.close()
