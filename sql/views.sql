USE FleetDB;
GO

/* =========================================================
   Views.sql
   说明：本文件集中存放本项目所有视图（View）
   ========================================================= */


/* ---------------------------------------------------------
   View: dbo.vw_weekly_exception_alert
   用途：近7天异常告警视图（异常+运单+司机+车辆+车队+中心联查）
   --------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_weekly_exception_alert
AS
SELECT
    e.event_id,                  -- 异常事件ID
    e.occurred_time,             -- 异常发生时间
    e.exception_type,            -- 异常类型
    e.status AS exception_status,-- 异常处理状态
    e.fine_amount,               -- 罚款金额
    e.description,               -- 异常详细描述

    o.order_id,                  -- 运单ID
    o.created_at,                -- 运单创建时间
    o.destination,               -- 运单目的地
    o.status AS order_status,    -- 运单状态

    d.driver_id,                 -- 司机ID
    d.name AS driver_name,       -- 司机姓名
    d.phone AS driver_phone,     -- 司机联系方式
    d.license_level,             -- 司机驾照等级

    v.vehicle_id,                -- 车辆ID
    v.license_plate_number,      -- 车牌号
    v.status AS vehicle_status,  -- 车辆状态

    f.fleet_id,                  -- 车队ID
    f.fleet_name,                -- 车队名称

    c.center_id,                 -- 配送中心ID
    c.center_name                -- 配送中心名称
FROM exception_events e
JOIN orders o   ON o.order_id = e.order_id      -- 异常 → 运单
JOIN drivers d  ON d.driver_id = o.driver_id    -- 运单 → 司机
JOIN vehicles v ON v.vehicle_id = o.vehicle_id  -- 运单 → 车辆
JOIN fleets f   ON f.fleet_id = v.fleet_id      -- 车辆 → 车队
JOIN centers c  ON c.center_id = f.center_id    -- 车队 → 配送中心
WHERE e.occurred_time >= DATEADD(DAY, -7, CAST(GETDATE() AS DATE));
-- 仅显示最近 7 天内发生的异常
GO


/* ---------------------------------------------------------
   View: dbo.vw_abnormal_driver_vehicle_alert
   用途：异常司机/车辆预警（近30天异常次数>=3 或 车辆状态=异常）
   --------------------------------------------------------- */
CREATE OR ALTER VIEW dbo.vw_abnormal_driver_vehicle_alert
AS
WITH e30 AS (
    SELECT
        o.driver_id,             -- 司机ID
        o.vehicle_id,            -- 车辆ID
        e.event_id,              -- 异常事件ID
        e.occurred_time,         -- 异常发生时间
        e.fine_amount            -- 罚款金额
    FROM orders o
    LEFT JOIN exception_events e
        ON e.order_id = o.order_id
       AND e.occurred_time >= DATEADD(DAY, -30, GETDATE())
       -- 仅统计近 30 天内的异常
),
pair_stat AS (
    SELECT
        driver_id,
        vehicle_id,
        COUNT(event_id) AS exception_count,        -- 异常次数
        ISNULL(SUM(fine_amount), 0) AS total_fines -- 罚款总额
    FROM e30
    GROUP BY driver_id, vehicle_id
)
SELECT
    d.driver_id,                                   -- 司机ID
    d.name AS driver_name,                         -- 司机姓名
    d.phone AS driver_phone,                       -- 司机联系方式
    d.license_level,                               -- 驾照等级

    v.vehicle_id,                                  -- 车辆ID
    v.license_plate_number,                        -- 车牌号
    v.status AS vehicle_status,                    -- 车辆状态

    ps.exception_count AS exception_count_30d,      -- 30天异常次数
    ps.total_fines AS total_fines_30d,              -- 30天罚款总额

    f.fleet_id,                                    -- 车队ID
    f.fleet_name,                                  -- 车队名称
    c.center_id,                                   -- 配送中心ID
    c.center_name,                                 -- 配送中心名称

    CASE
        WHEN ps.exception_count >= 3
            THEN N'异常预警：近30天异常次数过多'
        WHEN v.status = N'异常'
            THEN N'异常预警：车辆状态为异常'
        ELSE N'正常'
    END AS warning_reason                           -- 预警原因说明
FROM pair_stat ps
JOIN drivers d  ON d.driver_id = ps.driver_id       -- 关联司机
JOIN vehicles v ON v.vehicle_id = ps.vehicle_id     -- 关联车辆
JOIN fleets f   ON f.fleet_id = v.fleet_id          -- 关联车队
JOIN centers c  ON c.center_id = f.center_id        -- 关联配送中心
WHERE ps.exception_count >= 3
   OR v.status = N'异常';
GO
