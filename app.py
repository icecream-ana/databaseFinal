# Flask 入口

import os
from datetime import datetime, date
from flask import Flask, render_template, request, redirect, url_for, session, flash

import db
from auth import login_required, role_required, ROLE_DRIVER, ROLE_SUPERVISOR, current_user

import re
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-change-me")


# ----------------------------
# Helpers
# ----------------------------
def parse_dt(s: str, default: str):
    if not s:
        return default
    # Accept 'YYYY-MM-DD' or 'YYYY-MM-DDTHH:MM'
    try:
        if "T" in s:
            return datetime.fromisoformat(s).strftime("%Y-%m-%d %H:%M:%S")
        return datetime.fromisoformat(s).strftime("%Y-%m-%d 00:00:00")
    except Exception:
        return default

def supervisor_fleet_guard(fleet_id: int) -> bool:
    """
    Supervisor can only operate on their own fleet (per requirement).
    Driver can only operate on own records.
    """
    user = current_user()
    if user["role"] == ROLE_SUPERVISOR:
        return user.get("fleet_id") == fleet_id
    return False

# 电话号格式校验：11位中国大陆手机号（1开头）
_PHONE_RE = re.compile(r"^1\d{10}$")  
def validate_phone(phone: str) -> bool:
    phone = (phone or "").strip()
    return bool(_PHONE_RE.match(phone))

# 车牌号格式校验
_PLATE_RE = re.compile(r"^[京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼][A-Z][A-Z0-9]{5}$")
def validate_plate_cn_blue(plate: str) -> bool:
    plate = (plate or "").strip().upper()
    return bool(_PLATE_RE.match(plate))

# 提取触发器错误号与消息
def mssql_error_code_and_message(e: Exception):
    code = None
    msg = ""

    try:
        if hasattr(e, "args") and len(e.args) >= 2:
            code = e.args[0]
            raw = e.args[1]
            if isinstance(raw, (bytes, bytearray)):
                msg = raw.decode("utf-8", errors="ignore")
            else:
                msg = str(raw)
        else:
            msg = str(e)
    except Exception:
        msg = str(e)

    return code, msg

# 是否是触发器超载错误
def is_overload_trigger_error(e: Exception) -> bool:
    code, msg = mssql_error_code_and_message(e)
    return code == 50000 and ("车辆超载" in msg)

# 解析时间
def parse_date_range(start_str, end_str):
    """
    兼容输入：
      - YYYY-MM-DD
      - YYYY-MM-DD HH:MM:SS
      - YYYY-MM-DDTHH:MM (datetime-local)
    输出：
      start_dt: 当天 00:00:00
      end_dt:   (结束日期 + 1天) 00:00:00  （左闭右开）
    """
    if not start_str or not end_str:
        return None, None

    # 统一只取日期部分（前 10 位：YYYY-MM-DD）
    start_str = start_str.strip()[:10]
    end_str = end_str.strip()[:10]

    start_date = datetime.strptime(start_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_str, "%Y-%m-%d")

    start_dt = start_date
    end_dt = end_date + timedelta(days=1)
    return start_dt, end_dt


# ----------------------------
# Login / Logout
# ----------------------------
@app.get("/login")
def login():
    drivers = db.fetch_all("SELECT driver_id, name, fleet_id FROM drivers ORDER BY driver_id")
    supervisors = db.fetch_all("SELECT supervisor_id, name, fleet_id FROM supervisors ORDER BY supervisor_id")
    next_url = request.args.get("next") or url_for("dashboard")
    return render_template("login.html", drivers=drivers, supervisors=supervisors, next_url=next_url)

@app.post("/login")
def login_post():
    role = request.form.get("role")
    next_url = request.form.get("next_url") or url_for("dashboard")

    session.clear()

    if role == ROLE_DRIVER:
        driver_id = int(request.form["driver_id"])
        d = db.fetch_one(
            "SELECT driver_id, name, fleet_id FROM drivers WHERE driver_id=%s",
            (driver_id,)
        )
        if not d:
            flash("司机不存在。", "error")
            return redirect(url_for("login"))
        session["role"] = ROLE_DRIVER
        session["driver_id"] = d["driver_id"]
        session["fleet_id"] = d["fleet_id"]
        flash(f"已以司机身份登录：{d['name']}", "success")
        return redirect(next_url)

    if role == ROLE_SUPERVISOR:
        supervisor_id = int(request.form["supervisor_id"])
        s = db.fetch_one(
            "SELECT supervisor_id, name, fleet_id FROM supervisors WHERE supervisor_id=%s",
            (supervisor_id,)
        )
        if not s:
            flash("主管不存在。", "error")
            return redirect(url_for("login"))
        # find center_id for convenience
        f = db.fetch_one("SELECT fleet_id, center_id FROM fleets WHERE fleet_id=%s", (s["fleet_id"],))
        session["role"] = ROLE_SUPERVISOR
        session["supervisor_id"] = s["supervisor_id"]
        session["fleet_id"] = s["fleet_id"]
        session["center_id"] = f["center_id"] if f else None
        flash(f"已以主管身份登录：{s['name']}", "success")
        return redirect(next_url)

    flash("请选择有效角色。", "error")
    return redirect(url_for("login"))

@app.get("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ----------------------------
# Dashboard
# ----------------------------
@app.get("/")
def root():
    return redirect(url_for("dashboard"))

@app.get("/dashboard")
@login_required
def dashboard():
    user = current_user()

    # KPIs (supervisor sees fleet/center context; driver sees own context)
    weekly_exceptions = db.fetch_all(
        "SELECT TOP 10 * FROM dbo.vw_weekly_exception_alert ORDER BY occurred_time DESC"
    )

    abnormal_pairs = db.fetch_all(
        "SELECT TOP 10 * FROM dbo.vw_abnormal_driver_vehicle_alert ORDER BY exception_count_30d DESC, total_fines_30d DESC"
    )

    kpis = {}

    # Counts from views / vehicles
    kpis["weekly_exception_count"] = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM dbo.vw_weekly_exception_alert"
    )["cnt"]

    kpis["abnormal_pair_count"] = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM dbo.vw_abnormal_driver_vehicle_alert"
    )["cnt"]

    kpis["vehicles_abnormal"] = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM vehicles WHERE status=N'异常'"
    )["cnt"]

    kpis["vehicles_in_transit"] = db.fetch_one(
        "SELECT COUNT(*) AS cnt FROM vehicles WHERE status=N'运输中'"
    )["cnt"]

    # Monthly fleet report for supervisor; driver gets personal quick stats
    if user["role"] == ROLE_SUPERVISOR:
        today = date.today()
        rep = db.call_proc_sp_fleet_monthly_report(user["fleet_id"], today.year, today.month)
        kpis["fleet_month_report"] = rep
    else:
        # Driver's monthly orders and exceptions
        today = date.today()
        start = f"{today.year}-{today.month:02d}-01 00:00:00"
        # end = next month
        if today.month == 12:
            end = f"{today.year+1}-01-01 00:00:00"
        else:
            end = f"{today.year}-{today.month+1:02d}-01 00:00:00"
        driver_id = user["driver_id"]
        total_orders = db.fetch_one(
            "SELECT COUNT(*) AS cnt FROM orders WHERE driver_id=%s AND created_at>=%s AND created_at<%s",
            (driver_id, start, end)
        )["cnt"]
        total_ex = db.fetch_one(
            """
            SELECT COUNT(*) AS cnt
            FROM exception_events e
            JOIN orders o ON o.order_id=e.order_id
            WHERE o.driver_id=%s AND e.occurred_time>=%s AND e.occurred_time<%s
            """,
            (driver_id, start, end)
        )["cnt"]
        kpis["driver_month_orders"] = total_orders
        kpis["driver_month_exceptions"] = total_ex

    return render_template(
        "dashboard.html",
        user=user,
        kpis=kpis,
        weekly_exceptions=weekly_exceptions,
        abnormal_pairs=abnormal_pairs
    )

# ----------------------------
# Master data: vehicles, drivers, fleets
# ----------------------------
# ----------------------------
# vehicles
# ----------------------------
@app.get("/master/vehicles")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicles():
    user = current_user()
    rows = db.fetch_all(
        """
        SELECT v.vehicle_id, v.license_plate_number, v.max_weight, v.max_volume, v.status,
               v.fleet_id, f.fleet_name, c.center_name
        FROM vehicles v
        JOIN fleets f ON f.fleet_id=v.fleet_id
        JOIN centers c ON c.center_id=f.center_id
        WHERE v.fleet_id=%s
        ORDER BY v.vehicle_id
        """,
        (user["fleet_id"],)
    )
    return render_template("master_vehicles.html", user=user, vehicles=rows)

@app.get("/master/vehicles/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicle_new():
    user = current_user()
    return render_template("master_vehicle_form.html", user=user, vehicle=None)

@app.post("/master/vehicles/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicle_new_post():
    user = current_user()
    try:
        max_weight = float(request.form["max_weight"])
        max_volume = float(request.form["max_volume"])
        plate = request.form["license_plate_number"].strip().upper()

        # 非零校验（必须 > 0）
        if max_weight <= 0:
            flash("最大载重必须大于 0。", "error")
            return redirect(url_for("master_vehicle_new"))
        if max_volume <= 0:
            flash("最大容积必须大于 0。", "error")
            return redirect(url_for("master_vehicle_new"))

        # 车牌格式校验
        if not validate_plate_cn_blue(plate):
            flash("车牌号格式不合法（示例：沪A12345 / 粤B67890）。", "error")
            return redirect(url_for("master_vehicle_new"))

        db.execute(
            "INSERT INTO vehicles (max_weight, max_volume, fleet_id, license_plate_number) VALUES (%s, %s, %s, %s)",
            (max_weight, max_volume, user["fleet_id"], plate)
        )
        flash("车辆创建成功。", "success")
        return redirect(url_for("master_vehicles"))
    except Exception as e:
        flash(f"创建失败：{e}", "error")
        return redirect(url_for("master_vehicle_new"))


@app.get("/master/vehicles/<int:vehicle_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicle_edit(vehicle_id):
    user = current_user()
    v = db.fetch_one("SELECT * FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
    if not v or v["fleet_id"] != user["fleet_id"]:
        flash("车辆不存在或无权限。", "error")
        return redirect(url_for("master_vehicles"))
    return render_template("master_vehicle_form.html", user=user, vehicle=v)

@app.post("/master/vehicles/<int:vehicle_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicle_edit_post(vehicle_id):
    user = current_user()
    v = db.fetch_one("SELECT * FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
    if not v or v["fleet_id"] != user["fleet_id"]:
        flash("车辆不存在或无权限。", "error")
        return redirect(url_for("master_vehicles"))
    try:
        max_weight = float(request.form["max_weight"])
        max_volume = float(request.form["max_volume"])
        status = request.form["status"]
        plate = request.form["license_plate_number"].strip().upper()

        # 非零校验（必须 > 0）
        if max_weight <= 0:
            flash("最大载重必须大于 0。", "error")
            return redirect(url_for("master_vehicle_edit", vehicle_id=vehicle_id))
        if max_volume <= 0:
            flash("最大容积必须大于 0。", "error")
            return redirect(url_for("master_vehicle_edit", vehicle_id=vehicle_id))

        # 车牌格式校验
        if not validate_plate_cn_blue(plate):
            flash("车牌号格式不合法（示例：沪A12345 / 粤B67890）。", "error")
            return redirect(url_for("master_vehicle_edit", vehicle_id=vehicle_id))

        db.execute(
            """
            UPDATE vehicles
            SET max_weight=%s, max_volume=%s, status=%s, license_plate_number=%s
            WHERE vehicle_id=%s
            """,
            (max_weight, max_volume, status, plate, vehicle_id)
        )
        flash("车辆更新成功。", "success")
    except Exception as e:
        flash(f"更新失败：{e}", "error")
    return redirect(url_for("master_vehicles"))


@app.post("/master/vehicles/<int:vehicle_id>/delete")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_vehicle_delete_post(vehicle_id):
    user = current_user()
    v = db.fetch_one("SELECT * FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
    if not v or v["fleet_id"] != user["fleet_id"]:
        flash("车辆不存在或无权限。", "error")
        return redirect(url_for("master_vehicles"))

    # 业务约束：车辆若存在未结束订单，不允许删除
    active = db.fetch_one(
        """
        SELECT TOP 1 order_id
        FROM orders
        WHERE vehicle_id=%s AND status IN (N'待分配', N'运输中', N'异常')
        """,
        (vehicle_id,)
    )
    if active:
        flash("该车辆存在未结束的运单（待分配/运输中/异常），无法删除。", "error")
        return redirect(url_for("master_vehicles"))

    try:
        db.execute("DELETE FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
        flash("车辆已删除。", "success")
    except Exception as e:
        # 若仍有历史订单引用该 vehicle_id，会触发外键约束错误
        flash(f"删除失败：{e}", "error")

    return redirect(url_for("master_vehicles"))


# ----------------------------
# drivers
# ----------------------------
@app.get("/master/drivers")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_drivers():
    user = current_user()
    rows = db.fetch_all(
        """
        SELECT d.driver_id, d.name, d.license_level, d.phone, d.fleet_id, f.fleet_name
        FROM drivers d
        JOIN fleets f ON f.fleet_id=d.fleet_id
        WHERE d.fleet_id=%s
        ORDER BY d.driver_id
        """,
        (user["fleet_id"],)
    )
    return render_template("master_drivers.html", user=user, drivers=rows)

@app.get("/master/drivers/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_driver_new():
    user = current_user()
    return render_template("master_driver_form.html", user=user, driver=None)

@app.post("/master/drivers/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_driver_new_post():
    user = current_user()
    try:
        name = request.form["name"].strip()
        license_level = request.form["license_level"]
        phone = request.form["phone"].strip()

        # 联系方式校验
        if not validate_phone(phone):
            flash("联系方式格式不合法，请输入 11 位手机号（如 138xxxxxxxx）。", "error")
            return redirect(url_for("master_driver_new"))
        
        db.execute(
            "INSERT INTO drivers (name, license_level, phone, fleet_id) VALUES (%s, %s, %s, %s)",
            (name, license_level, phone, user["fleet_id"])
        )
        flash("司机创建成功。", "success")
        return redirect(url_for("master_drivers"))
    except Exception as e:
        flash(f"创建失败：{e}", "error")
        return redirect(url_for("master_driver_new"))

@app.get("/master/drivers/<int:driver_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_driver_edit(driver_id):
    user = current_user()
    d = db.fetch_one("SELECT * FROM drivers WHERE driver_id=%s", (driver_id,))
    if not d or d["fleet_id"] != user["fleet_id"]:
        flash("司机不存在或无权限。", "error")
        return redirect(url_for("master_drivers"))
    return render_template("master_driver_form.html", user=user, driver=d)

@app.post("/master/drivers/<int:driver_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_driver_edit_post(driver_id):
    user = current_user()
    d = db.fetch_one("SELECT * FROM drivers WHERE driver_id=%s", (driver_id,))
    if not d or d["fleet_id"] != user["fleet_id"]:
        flash("司机不存在或无权限。", "error")
        return redirect(url_for("master_drivers"))
    try:
        name = request.form["name"].strip()
        license_level = request.form["license_level"]
        phone = request.form["phone"].strip()

        # 联系方式校验
        if not validate_phone(phone):
            flash("联系方式格式不合法，请输入 11 位手机号（如 138xxxxxxxx）。", "error")
            return redirect(url_for("master_driver_new"))
        
        db.execute(
            "UPDATE drivers SET name=%s, license_level=%s, phone=%s WHERE driver_id=%s",
            (name, license_level, phone, driver_id)
        )
        # triggers will write history_log automatically
        flash("司机更新成功（审计已记录）。", "success")
    except Exception as e:
        flash(f"更新失败：{e}", "error")
    return redirect(url_for("master_drivers"))

@app.post("/master/drivers/<int:driver_id>/delete")
@login_required
@role_required(ROLE_SUPERVISOR)
def master_driver_delete_post(driver_id):
    user = current_user()

    d = db.fetch_one("SELECT * FROM drivers WHERE driver_id=%s", (driver_id,))
    if not d or d["fleet_id"] != user["fleet_id"]:
        flash("司机不存在或无权限。", "error")
        return redirect(url_for("master_drivers"))

    # 业务约束：如果该司机有未完成/未结束的订单，不允许删除
    active = db.fetch_one(
        """
        SELECT TOP 1 order_id
        FROM orders
        WHERE driver_id=%s AND status IN (N'待分配', N'运输中', N'异常')
        """,
        (driver_id,)
    )
    if active:
        flash("该司机存在未结束的运单（待分配/运输中/异常），无法删除。", "error")
        return redirect(url_for("master_drivers"))

    try:
        db.execute("DELETE FROM drivers WHERE driver_id=%s", (driver_id,))
        flash("司机已删除。", "success")
    except Exception as e:
        # 若数据库存在 FK 限制或其他依赖，这里会报错
        flash(f"删除失败：{e}", "error")

    return redirect(url_for("master_drivers"))

# ----------------------------
# Orders
# ----------------------------
from flask import request, render_template

@app.get("/orders/list")
@login_required
def orders_list():
    user = current_user()

    # 读取筛选条件（默认：所有订单 + 全部（不限定已/未分配））
    scope = request.args.get("scope", "all")          # all | mine
    assign = request.args.get("assign", "all")        # all | assigned | unassigned

    where_clauses = []
    params = []

    # 角色控制：司机只能看“我的订单”
    if user["role"] != ROLE_SUPERVISOR:
        scope = "mine"

    # scope 过滤
    if scope == "mine":
        if user["role"] == ROLE_SUPERVISOR:
            # “我的订单”= 车辆或司机归属我的车队（注：两者都为空的订单无法归属）
            where_clauses.append("(v.fleet_id = %s OR d.fleet_id = %s)")
            params.extend([user["fleet_id"], user["fleet_id"]])
        else:
            # 司机的“我的订单”= driver_id = 自己
            where_clauses.append("o.driver_id = %s")
            params.append(user["driver_id"])

    # assign 过滤
    if assign == "assigned":
        # 已分配：车辆和司机都不为空
        where_clauses.append("o.vehicle_id IS NOT NULL AND o.driver_id IS NOT NULL")
    elif assign == "unassigned":
        # 未分配：车辆或司机任一为空
        where_clauses.append("(o.vehicle_id IS NULL OR o.driver_id IS NULL)")

    # 拼接 WHERE
    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    # 主查询（LEFT JOIN 支持 vehicle/driver 为空）
    sql = f"""
        SELECT
            o.order_id, o.created_at, o.destination, o.weight, o.volume, o.status,
            o.vehicle_id, o.driver_id,
            v.license_plate_number,
            d.name AS driver_name
        FROM orders o
        LEFT JOIN vehicles v ON v.vehicle_id = o.vehicle_id
        LEFT JOIN drivers  d ON d.driver_id  = o.driver_id
        {where_sql}
        ORDER BY o.created_at DESC
    """

    rows = db.fetch_all(sql, tuple(params))

    # 主管需要车辆/司机下拉（用于：新建运单 + 给未分配运单分配）
    vehicles, drivers = [], []
    if user["role"] == ROLE_SUPERVISOR:
        vehicles = db.fetch_all(
            """
            SELECT vehicle_id, license_plate_number, max_weight, status
            FROM vehicles
            WHERE fleet_id=%s
            ORDER BY vehicle_id
            """,
            (user["fleet_id"],)
        )
        drivers = db.fetch_all(
            """
            SELECT driver_id, name, license_level
            FROM drivers
            WHERE fleet_id=%s
            ORDER BY driver_id
            """,
            (user["fleet_id"],)
        )

    return render_template(
        "orders_list.html",
        user=user,
        orders=rows,
        vehicles=vehicles,
        drivers=drivers,
        scope=scope,
        assign=assign
    )


@app.get("/orders/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def orders_new():
    user = current_user()

    # 新建页需要车辆/司机下拉（本车队）
    vehicles = db.fetch_all(
        """
        SELECT vehicle_id, license_plate_number, max_weight, max_volume, status
        FROM vehicles
        WHERE fleet_id=%s
        ORDER BY vehicle_id
        """,
        (user["fleet_id"],)
    )
    drivers = db.fetch_all(
        """
        SELECT driver_id, name, license_level
        FROM drivers
        WHERE fleet_id=%s
        ORDER BY driver_id
        """,
        (user["fleet_id"],)
    )

    return render_template("order_form.html", user=user, vehicles=vehicles, drivers=drivers, order=None, mode="new")


@app.post("/orders/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def orders_create_post():
    user = current_user()
    try:
        weight = float(request.form["weight"])
        volume = float(request.form["volume"])
        destination = request.form["destination"].strip()

        if weight <= 0:
            flash("货物重量必须大于 0。", "error")
            return redirect(url_for("orders_new"))

        if volume <= 0:
            flash("货物体积必须大于 0。", "error")
            return redirect(url_for("orders_new"))

        # 允许为空：空字符串/缺失 => None
        vehicle_id_raw = request.form.get("vehicle_id", "").strip()
        driver_id_raw = request.form.get("driver_id", "").strip()
        vehicle_id = int(vehicle_id_raw) if vehicle_id_raw else None
        driver_id = int(driver_id_raw) if driver_id_raw else None

        # 若填写了车辆/司机，校验必须属于当前车队
        if vehicle_id is not None:
            v = db.fetch_one("SELECT vehicle_id, fleet_id FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
            if not v or v["fleet_id"] != user["fleet_id"]:
                flash("车辆不属于你的车队，无法选择。", "error")
                return redirect(url_for("orders_new"))

        if driver_id is not None:
            d = db.fetch_one("SELECT driver_id, fleet_id FROM drivers WHERE driver_id=%s", (driver_id,))
            if not d or d["fleet_id"] != user["fleet_id"]:
                flash("司机不属于你的车队，无法选择。", "error")
                return redirect(url_for("orders_new"))

        # 状态规则：
        # - 未分配（车辆或司机任一为空） => 待分配
        # - 已分配（两者都有） => 待分配（你也可以改成运输中，但你之前明确：分配后改运输中；新建时可保持待分配）
        if vehicle_id and driver_id:
            status = "运输中"
        else:
            status = '待分配'

        db.execute(
            """
            INSERT INTO orders (weight, volume, destination, vehicle_id, driver_id, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (weight, volume, destination, vehicle_id, driver_id, status)
        )

        flash("运单创建成功。", "success")
        return redirect(url_for("orders_list"))

    except Exception as e:
        if is_overload_trigger_error(e):
            flash("分配失败：车辆超载")
        else:
            code, msg = mssql_error_code_and_message(e)
            flash(f"分配失败：{msg or e}", "error")
        return redirect(url_for("orders_new"))



@app.get("/orders/<int:order_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def order_edit(order_id):
    user = current_user()

    o = db.fetch_one(
        """
        SELECT
            o.*,
            v.license_plate_number,
            d.name AS driver_name
        FROM orders o
        LEFT JOIN vehicles v ON v.vehicle_id = o.vehicle_id
        LEFT JOIN drivers  d ON d.driver_id  = o.driver_id
        WHERE o.order_id=%s
        """,
        (order_id,)
    )
    if not o:
        flash("运单不存在或无权限。", "error")
        return redirect(url_for("orders_list"))

    vehicles = db.fetch_all(
        """
        SELECT vehicle_id, license_plate_number, max_weight, max_volume, status
        FROM vehicles
        WHERE fleet_id=%s
        ORDER BY vehicle_id
        """,
        (user["fleet_id"],)
    )
    drivers = db.fetch_all(
        """
        SELECT driver_id, name, license_level
        FROM drivers
        WHERE fleet_id=%s
        ORDER BY driver_id
        """,
        (user["fleet_id"],)
    )

    return render_template("order_form.html", user=user, order=o, vehicles=vehicles, drivers=drivers, mode="edit")



@app.post("/orders/<int:order_id>/edit")
@login_required
@role_required(ROLE_SUPERVISOR)
def order_edit_post(order_id):
    user = current_user()

    o = db.fetch_one("SELECT * FROM orders WHERE order_id=%s", (order_id,))
    if not o:
        flash("运单不存在或无权限。", "error")
        return redirect(url_for("orders_list"))

    try:
        weight = float(request.form["weight"])
        volume = float(request.form["volume"])
        destination = request.form["destination"].strip()
        status = request.form.get("status", "").strip()

        if weight <= 0:
            flash("货物重量必须大于 0。", "error")
            return redirect(url_for("order_edit", order_id=order_id))
        if volume <= 0:
            flash("货物体积必须大于 0。", "error")
            return redirect(url_for("order_edit", order_id=order_id))
        if status not in ["待分配", "运输中", "已完成", "异常"]:
            flash("非法的运单状态。", "error")
            return redirect(url_for("order_edit", order_id=order_id))

        vehicle_id_raw = request.form.get("vehicle_id", "").strip()
        driver_id_raw = request.form.get("driver_id", "").strip()
        vehicle_id = int(vehicle_id_raw) if vehicle_id_raw else None
        driver_id = int(driver_id_raw) if driver_id_raw else None

        # 校验车辆/司机归属车队（如果填写）
        if vehicle_id is not None:
            v = db.fetch_one("SELECT vehicle_id, fleet_id FROM vehicles WHERE vehicle_id=%s", (vehicle_id,))
            if not v or v["fleet_id"] != user["fleet_id"]:
                flash("车辆不属于你的车队，无法选择。", "error")
                return redirect(url_for("order_edit", order_id=order_id))

        if driver_id is not None:
            d = db.fetch_one("SELECT driver_id, fleet_id FROM drivers WHERE driver_id=%s", (driver_id,))
            if not d or d["fleet_id"] != user["fleet_id"]:
                flash("司机不属于你的车队，无法选择。", "error")
                return redirect(url_for("order_edit", order_id=order_id))

        # 校验状态
        old_status = o["status"]

        if vehicle_id is None or driver_id is None:
            if status != "待分配":
                flash("未分配车辆或司机的运单，状态必须为“待分配”。", "error")
                return redirect(url_for("order_edit", order_id=order_id))
            
        if old_status != status:
            if (old_status != "运输中" and status == "已完成"):
                flash(f"不允许将运单状态从“{old_status}”修改为“{status}”。", "error")
                return redirect(url_for("order_edit", order_id=order_id))

        if old_status == "异常":
            flash("不允许修改异常订单的状态，请通过处理异常完成状态改变", "error")
            return redirect(url_for("order_edit", order_id=order_id))

        db.execute(
            """
            UPDATE orders
            SET weight=%s, volume=%s, destination=%s,
                vehicle_id=%s, driver_id=%s, status=%s
            WHERE order_id=%s
            """,
            (weight, volume, destination, vehicle_id, driver_id, status, order_id)
        )

        flash("运单更新成功。", "success")
        return redirect(url_for("orders_list"))

    except Exception as e:
        if is_overload_trigger_error(e):
            flash("更新失败：车辆超载。")
        else:
            code, msg = mssql_error_code_and_message(e)
            flash(f"更新失败：{msg or e}", "error")
        return redirect(url_for("order_edit", order_id=order_id))



@app.get("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    user = current_user()
    o = db.fetch_one(
        """
        SELECT o.*, v.license_plate_number, v.fleet_id, v.status AS vehicle_status,
               d.name AS driver_name, d.driver_id
        FROM orders o
        JOIN vehicles v ON v.vehicle_id=o.vehicle_id
        JOIN drivers d ON d.driver_id=o.driver_id
        WHERE o.order_id=%s
        """,
        (order_id,)
    )
    if not o:
        flash("运单不存在。", "error")
        return redirect(url_for("orders_list"))

    # Access control
    if user["role"] == ROLE_SUPERVISOR and o["fleet_id"] != user["fleet_id"]:
        flash("无权限查看该运单。", "error")
        return redirect(url_for("orders_list"))
    if user["role"] == ROLE_DRIVER and o["driver_id"] != user["driver_id"]:
        flash("无权限查看该运单。", "error")
        return redirect(url_for("orders_list"))

    # Exceptions for this order
    ex = db.fetch_all(
        "SELECT * FROM exception_events WHERE order_id=%s ORDER BY occurred_time DESC",
        (order_id,)
    )
    return render_template("order_detail.html", user=user, order=o, exceptions=ex)

@app.post("/orders/<int:order_id>/status")
@login_required
def order_update_status(order_id):
    user = current_user()
    new_status = request.form.get("status")
    o = db.fetch_one(
        """
        SELECT o.order_id, o.driver_id, v.fleet_id
        FROM orders o JOIN vehicles v ON v.vehicle_id=o.vehicle_id
        WHERE o.order_id=%s
        """,
        (order_id,)
    )
    if not o:
        flash("运单不存在。", "error")
        return redirect(url_for("orders_list"))

    # Supervisor can change status for own fleet; driver can only change their own order to limited statuses
    if user["role"] == ROLE_SUPERVISOR:
        if o["fleet_id"] != user["fleet_id"]:
            flash("无权限更新该运单。", "error")
            return redirect(url_for("orders_list"))
    else:
        if o["driver_id"] != user["driver_id"]:
            flash("无权限更新该运单。", "error")
            return redirect(url_for("orders_list"))
        if new_status not in ["运输中", "已完成", "异常"]:
            flash("司机不允许设置该状态。", "error")
            return redirect(url_for("order_detail", order_id=order_id))

    try:
        db.execute("UPDATE orders SET status=%s WHERE order_id=%s", (new_status, order_id))
        # order completion trigger may set vehicle idle automatically
        flash("运单状态更新成功。", "success")
    except Exception as e:
        flash(f"更新失败：{e}", "error")
    return redirect(url_for("order_detail", order_id=order_id))

# ----------------------------
# Exceptions
# ----------------------------
@app.get("/exceptions/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def exceptions_new():
    user = current_user()
    # pick order from supervisor's fleet
    orders = db.fetch_all(
        """
        SELECT o.order_id, o.created_at, o.destination, o.status,
               v.license_plate_number, d.name AS driver_name
        FROM orders o
        JOIN vehicles v ON v.vehicle_id=o.vehicle_id
        JOIN drivers d ON d.driver_id=o.driver_id
        WHERE v.fleet_id=%s
        ORDER BY o.created_at DESC
        """,
        (user["fleet_id"],)
    )
    return render_template("exceptions_new.html", user=user, orders=orders)

@app.post("/exceptions/new")
@login_required
@role_required(ROLE_SUPERVISOR)
def exceptions_new_post():
    user = current_user()
    try:
        order_id = int(request.form["order_id"])
        exception_type = request.form["exception_type"]
        occurred_time = request.form["occurred_time"].replace("T", " ")
        fine_amount = int(request.form.get("fine_amount", "0") or "0")
        description = request.form["description"].strip()
        status = request.form.get("status") or "待处理"

        # Guard: order must belong to supervisor's fleet
        o = db.fetch_one(
            """
            SELECT o.order_id, v.fleet_id
            FROM orders o JOIN vehicles v ON v.vehicle_id=o.vehicle_id
            WHERE o.order_id=%s
            """,
            (order_id,)
        )
        if not o or o["fleet_id"] != user["fleet_id"]:
            flash("运单不存在或不属于你的车队。", "error")
            return redirect(url_for("exceptions_new"))

        db.execute(
            """
            INSERT INTO exception_events (order_id, exception_type, fine_amount, occurred_time, description, status)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (order_id, exception_type, fine_amount, occurred_time, description, status)
        )
        flash("异常记录已创建。", "success")
        return redirect(url_for("exceptions_list"))
    except Exception as e:
        flash(f"创建失败：{e}", "error")
        return redirect(url_for("exceptions_new"))

@app.get("/exceptions/list")
@login_required
def exceptions_list():
    user = current_user()
    if user["role"] == ROLE_SUPERVISOR:
        rows = db.fetch_all(
            """
            SELECT e.*, o.destination, o.status AS order_status,
                   v.license_plate_number, d.name AS driver_name, v.fleet_id
            FROM exception_events e
            JOIN orders o ON o.order_id=e.order_id
            JOIN vehicles v ON v.vehicle_id=o.vehicle_id
            JOIN drivers d ON d.driver_id=o.driver_id
            WHERE v.fleet_id=%s
            ORDER BY e.occurred_time DESC
            """,
            (user["fleet_id"],)
        )
    else:
        rows = db.fetch_all(
            """
            SELECT e.*, o.destination, o.status AS order_status,
                   v.license_plate_number, d.name AS driver_name
            FROM exception_events e
            JOIN orders o ON o.order_id=e.order_id
            JOIN vehicles v ON v.vehicle_id=o.vehicle_id
            JOIN drivers d ON d.driver_id=o.driver_id
            WHERE o.driver_id=%s
            ORDER BY e.occurred_time DESC
            """,
            (user["driver_id"],)
        )
    return render_template("exceptions_list.html", user=user, exceptions=rows)

@app.get("/exceptions/<int:event_id>")
@login_required
def exception_detail(event_id):
    user = current_user()
    e = db.fetch_one(
        """
        SELECT e.*, o.destination, o.status AS order_status, o.order_id,
               v.license_plate_number, v.status AS vehicle_status, v.fleet_id,
               d.name AS driver_name, d.driver_id
        FROM exception_events e
        JOIN orders o ON o.order_id=e.order_id
        JOIN vehicles v ON v.vehicle_id=o.vehicle_id
        JOIN drivers d ON d.driver_id=o.driver_id
        WHERE e.event_id=%s
        """,
        (event_id,)
    )
    if not e:
        flash("异常记录不存在。", "error")
        return redirect(url_for("exceptions_list"))

    if user["role"] == ROLE_SUPERVISOR and e["fleet_id"] != user["fleet_id"]:
        flash("无权限查看该异常。", "error")
        return redirect(url_for("exceptions_list"))
    if user["role"] == ROLE_DRIVER and e["driver_id"] != user["driver_id"]:
        flash("无权限查看该异常。", "error")
        return redirect(url_for("exceptions_list"))

    return render_template("exception_detail.html", user=user, ex=e)

@app.post("/exceptions/<int:event_id>/status")
@login_required
@role_required(ROLE_SUPERVISOR)
def exception_update_status(event_id):
    user = current_user()
    new_status = request.form.get("status")
    e = db.fetch_one(
        """
        SELECT e.event_id, v.fleet_id
        FROM exception_events e
        JOIN orders o ON o.order_id=e.order_id
        JOIN vehicles v ON v.vehicle_id=o.vehicle_id
        WHERE e.event_id=%s
        """,
        (event_id,)
    )
    if not e or e["fleet_id"] != user["fleet_id"]:
        flash("异常不存在或无权限。", "error")
        return redirect(url_for("exceptions_list"))

    try:
        db.execute("UPDATE exception_events SET status=%s WHERE event_id=%s", (new_status, event_id))
        # triggers will:
        # - if status becomes 已处理: write audit log and restore vehicle status based on exception_type
        flash("异常状态更新成功（如置为已处理，将触发车辆恢复与审计）。", "success")
    except Exception as ex:
        flash(f"更新失败：{ex}", "error")
    return redirect(url_for("exceptions_list", event_id=event_id))

# ----------------------------
# Resources (center/fleet)
# ----------------------------
@app.get("/resources/center")
@login_required
@role_required(ROLE_SUPERVISOR)
def resources_center():
    user = current_user()
    centers = db.fetch_all("SELECT center_id, center_name FROM centers ORDER BY center_id")
    center_id = int(request.args.get("center_id") or (user.get("center_id") or centers[0]["center_id"]))
    fleets = db.fetch_all(
        """
        SELECT f.fleet_id, f.fleet_name,
               SUM(CASE WHEN v.status=N'空闲' THEN 1 ELSE 0 END) AS idle_cnt,
               SUM(CASE WHEN v.status=N'运输中' THEN 1 ELSE 0 END) AS transit_cnt,
               SUM(CASE WHEN v.status=N'异常' THEN 1 ELSE 0 END) AS abnormal_cnt
        FROM fleets f
        LEFT JOIN vehicles v ON v.fleet_id=f.fleet_id
        WHERE f.center_id=%s
        GROUP BY f.fleet_id, f.fleet_name
        ORDER BY f.fleet_id
        """,
        (center_id,)
    )
    return render_template("resources_center.html", user=user, centers=centers, center_id=center_id, fleets=fleets)

@app.get("/resources/fleet/<int:fleet_id>")
@login_required
@role_required(ROLE_SUPERVISOR)
def resources_fleet_detail(fleet_id):
    user = current_user()
    # Supervisor can view any fleet in same center, or restrict to own; here keep simple: own fleet only
    # if not supervisor_fleet_guard(fleet_id):
    #     flash("仅允许查看自己监管的车队资源。", "error")
    #     return redirect(url_for("resources_center"))

    vehicles = db.fetch_all(
        """
        SELECT v.vehicle_id, v.license_plate_number, v.max_weight, v.status,
               ISNULL(osum.current_total_weight, 0) AS active_weight
        FROM vehicles v
        LEFT JOIN (
            SELECT vehicle_id, SUM(weight) AS current_total_weight
            FROM orders
            WHERE status IN (N'待分配', N'运输中')
            GROUP BY vehicle_id
        ) osum ON osum.vehicle_id=v.vehicle_id
        WHERE v.fleet_id=%s
        ORDER BY v.vehicle_id
        """,
        (fleet_id,)
    )
    return render_template("resources_fleet_detail.html", user=user, fleet_id=fleet_id, vehicles=vehicles)

# ----------------------------
# Reports
# ----------------------------
@app.get("/reports/driver-performance")
@login_required
def report_driver_performance():
    user = current_user()

    driver_id = request.args.get("driver_id")
    if user["role"] == ROLE_DRIVER:
        driver_id = str(user["driver_id"])

    # ===== 默认日期：本月 =====
    today = datetime.today()
    start_default = today.replace(day=1).strftime("%Y-%m-%d")
    end_default = today.strftime("%Y-%m-%d")

    start_str = request.args.get("start", start_default)
    end_str = request.args.get("end", end_default)

    start_dt, end_dt = parse_date_range(start_str, end_str)

    if start_dt and end_dt and end_dt <= start_dt:
        flash("结束日期必须大于等于开始日期。", "error")
        return redirect(url_for("report_driver_performance"))

    drivers = []
    if user["role"] == ROLE_SUPERVISOR:
        drivers = db.fetch_all(
            "SELECT driver_id, name FROM drivers WHERE fleet_id=%s ORDER BY driver_id",
            (user["fleet_id"],)
        )

    summary = None
    details = []
    if driver_id and start_dt and end_dt:
        if user["role"] == ROLE_SUPERVISOR:
            d = db.fetch_one(
                "SELECT driver_id, fleet_id FROM drivers WHERE driver_id=%s",
                (int(driver_id),)
            )
            if not d or d["fleet_id"] != user["fleet_id"]:
                flash("只能查询自己车队的司机。", "error")
                return redirect(url_for("report_driver_performance"))

        summary, details = db.call_proc_sp_driver_performance(
            int(driver_id),
            start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            end_dt.strftime("%Y-%m-%d %H:%M:%S")
        )

    return render_template(
        "report_driver_performance.html",
        user=user,
        drivers=drivers,
        driver_id=driver_id,
        start=start_str,  # YYYY-MM-DD
        end=end_str,
        summary=summary,
        details=details
    )

@app.get("/reports/fleet-monthly")
@login_required
@role_required(ROLE_SUPERVISOR)
def report_fleet_monthly():
    user = current_user()
    fleet_id = int(request.args.get("fleet_id") or user["fleet_id"])
    year = int(request.args.get("year") or date.today().year)
    month = int(request.args.get("month") or date.today().month)

    if not supervisor_fleet_guard(fleet_id):
        flash("只能查询自己监管的车队月报。", "error")
        fleet_id = user["fleet_id"]

    report = db.call_proc_sp_fleet_monthly_report(fleet_id, year, month)
    return render_template(
        "report_fleet_monthly.html",
        user=user,
        fleet_id=fleet_id,
        year=year,
        month=month,
        report=report
    )

# ----------------------------
# Alerts (views)
# ----------------------------
from datetime import datetime, timedelta

@app.get("/alerts/weekly-exceptions")
@login_required
@role_required(ROLE_SUPERVISOR)
def alerts_weekly_exceptions():
    user = current_user()

    status = request.args.get("status", "all").strip()
    ex_type = request.args.get("type", "all").strip()
    q = request.args.get("q", "").strip()
    min_fine_raw = request.args.get("min_fine", "").strip()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()

    where = ["fleet_id=%s"]
    params = [user["fleet_id"]]

    if status != "all":
        where.append("exception_status=%s")
        params.append(status)

    if ex_type != "all":
        where.append("exception_type=%s")
        params.append(ex_type)

    # 时间范围（按“日”）
    if start_date:
        where.append("occurred_time >= %s")
        params.append(start_date + " 00:00:00")

    if end_date:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
        where.append("occurred_time < %s")
        params.append(end_dt.strftime("%Y-%m-%d 00:00:00"))

    # 最低罚款
    if min_fine_raw:
        try:
            min_fine = max(int(min_fine_raw), 0)
            where.append("fine_amount >= %s")
            params.append(min_fine)
        except:
            min_fine = 0
    else:
        min_fine = 0

    # 关键词
    if q:
        where.append("""
            (
                CAST(event_id AS NVARCHAR(50)) LIKE %s OR
                CAST(order_id AS NVARCHAR(50)) LIKE %s OR
                destination LIKE %s OR
                driver_name LIKE %s OR
                license_plate_number LIKE %s
            )
        """)
        like = f"%{q}%"
        params.extend([like] * 5)

    where_sql = " AND ".join(where)

    rows = db.fetch_all(
        f"""
        SELECT *
        FROM dbo.vw_weekly_exception_alert
        WHERE {where_sql}
        ORDER BY occurred_time DESC
        """,
        tuple(params)
    )

    total = len(rows)
    total_fine = sum(r.get("fine_amount") or 0 for r in rows)
    by_status = {"待处理": 0, "处理中": 0, "已处理": 0}
    for r in rows:
        if r["exception_status"] in by_status:
            by_status[r["exception_status"]] += 1

    return render_template(
        "alerts_weekly_exceptions.html",
        user=user,
        rows=rows,
        status=status,
        ex_type=ex_type,
        q=q,
        min_fine=min_fine,
        start_date=start_date,
        end_date=end_date,
        total=total,
        total_fine=total_fine,
        by_status=by_status,
    )



@app.get("/alerts/weekly-exceptions/<int:event_id>")
@login_required
@role_required(ROLE_SUPERVISOR)
def alerts_weekly_exception_detail(event_id):
    user = current_user()

    r = db.fetch_one(
        """
        SELECT *
        FROM dbo.vw_weekly_exception_alert
        WHERE event_id=%s AND fleet_id=%s
        """,
        (event_id, user["fleet_id"])
    )
    if not r:
        flash("异常记录不存在或无权限查看。", "error")
        return redirect(url_for("alerts_weekly_exceptions"))

    return render_template(
        "alerts_weekly_exception_detail.html",
        user=user,
        r=r
    )


@app.get("/alerts/abnormal-pairs")
@login_required
@role_required(ROLE_SUPERVISOR)
def alerts_abnormal_pairs():
    user = current_user()
    rows = db.fetch_all(
        """
        SELECT *
        FROM dbo.vw_abnormal_driver_vehicle_alert
        WHERE fleet_id=%s
        ORDER BY exception_count_30d DESC, total_fines_30d DESC
        """,
        (user["fleet_id"],)
    )
    return render_template("alerts_abnormal_pairs.html", user=user, rows=rows)

# ----------------------------
# Audit (history_log)
# ----------------------------
@app.get("/audit/history")
@login_required
@role_required(ROLE_SUPERVISOR)
def audit_history():
    user = current_user()
    # Only show last 200 for demo
    rows = db.fetch_all(
        """
        SELECT TOP 200 log_id, table_name, change_id, operation_type, change_at, old_data
        FROM history_log
        ORDER BY change_at DESC
        """
    )
    return render_template("audit_history.html", user=user, rows=rows)

if __name__ == "__main__":
    app.run(debug=True)


