USE FleetDB;
GO

/* =========================================================
   Procedures.sql
   说明：本文件集中存放本项目所有存储过程（Stored Procedure）
   ========================================================= */


/* ---------------------------------------------------------
   Procedure: dbo.sp_fleet_monthly_report
   用途：按“车队+年月”统计运单总数、异常总数、罚款总额
   --------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_fleet_monthly_report
    @fleet_id INT,
    @year INT,
    @month INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @start DATETIME = DATETIMEFROMPARTS(@year, @month, 1, 0, 0, 0, 0);
    DECLARE @end   DATETIME = DATEADD(MONTH, 1, @start);

    /* 1) 当月车队运单集合（核心口径） */
    ;WITH fleet_orders AS (
        SELECT
            o.order_id,
            o.driver_id,
            o.vehicle_id,
            o.status,
            o.weight,
            o.volume,
            o.created_at
        FROM dbo.orders o
        JOIN dbo.vehicles v ON v.vehicle_id = o.vehicle_id
        WHERE v.fleet_id = @fleet_id
          AND o.created_at >= @start AND o.created_at < @end
    ),
    /* 2) 当月这些运单对应的异常事件 */
    fleet_exceptions AS (
        SELECT
            e.event_id,
            e.order_id,
            e.exception_type,
            e.status AS exception_status,
            e.fine_amount,
            e.occurred_time
        FROM dbo.exception_events e
        JOIN fleet_orders fo ON fo.order_id = e.order_id
        WHERE e.occurred_time >= @start AND e.occurred_time < @end
    ),
    /* 3) 车队车辆全集（用于算空闲车辆数） */
    fleet_vehicles AS (
        SELECT v.vehicle_id
        FROM dbo.vehicles v
        WHERE v.fleet_id = @fleet_id
    )
    SELECT
        /* 基本维度 */
        @fleet_id AS fleet_id,
        @year     AS [year],
        @month    AS [month],

        /* A. 基础指标（你已实现的三项） */
        COUNT(*) AS total_orders,
        (SELECT COUNT(*) FROM fleet_exceptions) AS total_exceptions,
        (SELECT ISNULL(SUM(fine_amount), 0) FROM fleet_exceptions) AS total_fines,

        /* B. 运单状态结构 + 比率（建议 1） */
        SUM(CASE WHEN fo.status = N'待分配' THEN 1 ELSE 0 END) AS orders_pending,
        SUM(CASE WHEN fo.status = N'运输中' THEN 1 ELSE 0 END) AS orders_in_transit,
        SUM(CASE WHEN fo.status = N'已完成' THEN 1 ELSE 0 END) AS orders_completed,
        SUM(CASE WHEN fo.status = N'异常'   THEN 1 ELSE 0 END) AS orders_abnormal,

        CAST(
            1.0 * SUM(CASE WHEN fo.status = N'已完成' THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0)
            AS DECIMAL(10,4)
        ) AS completion_rate,

        CAST(
            1.0 * SUM(CASE WHEN fo.status = N'异常' THEN 1 ELSE 0 END)
            / NULLIF(COUNT(*), 0)
            AS DECIMAL(10,4)
        ) AS abnormal_order_rate,

        /* 也可按“异常事件/总运单”定义异常率（朋友给的另一口径） */
        CAST(
            1.0 * (SELECT COUNT(*) FROM fleet_exceptions)
            / NULLIF(COUNT(*), 0)
            AS DECIMAL(10,4)
        ) AS abnormal_event_rate,

        /* C. 货量规模与结构（建议 2） */
        ISNULL(SUM(fo.weight), 0) AS total_weight,
        ISNULL(SUM(fo.volume), 0) AS total_volume,
        CAST(ISNULL(AVG(CAST(fo.weight AS FLOAT)), 0) AS DECIMAL(18,4)) AS avg_weight,
        CAST(ISNULL(AVG(CAST(fo.volume AS FLOAT)), 0) AS DECIMAL(18,4)) AS avg_volume,
        ISNULL(MAX(fo.weight), 0) AS max_weight,
        ISNULL(MIN(fo.weight), 0) AS min_weight,
        ISNULL(MAX(fo.volume), 0) AS max_volume,
        ISNULL(MIN(fo.volume), 0) AS min_volume,

        /* D. 车辆利用（建议 3） */
        (SELECT COUNT(DISTINCT fo2.vehicle_id) FROM fleet_orders fo2) AS active_vehicles,
        CAST(
            1.0 * COUNT(*) / NULLIF((SELECT COUNT(DISTINCT fo2.vehicle_id) FROM fleet_orders fo2), 0)
            AS DECIMAL(10,4)
        ) AS orders_per_active_vehicle,
        (SELECT COUNT(*) FROM fleet_vehicles fv
         WHERE NOT EXISTS (SELECT 1 FROM fleet_orders fo3 WHERE fo3.vehicle_id = fv.vehicle_id)
        ) AS idle_vehicles,

        /* E. 司机绩效（建议 4：先做车队维度参与司机数 + 人均运单） */
        (SELECT COUNT(DISTINCT fo4.driver_id) FROM fleet_orders fo4) AS active_drivers,
        CAST(
            1.0 * COUNT(*) / NULLIF((SELECT COUNT(DISTINCT fo4.driver_id) FROM fleet_orders fo4), 0)
            AS DECIMAL(10,4)
        ) AS orders_per_active_driver,

        /* F. 异常结构（建议 5：异常类型分布需要单独结果集，这里先给“待处理异常数/单均罚款”） */
        (SELECT COUNT(*) FROM fleet_exceptions WHERE exception_status = N'待处理') AS pending_exceptions,
        CAST(
            1.0 * (SELECT ISNULL(SUM(fine_amount),0) FROM fleet_exceptions)
            / NULLIF((SELECT COUNT(*) FROM fleet_exceptions), 0)
            AS DECIMAL(10,4)
        ) AS avg_fine_per_exception
    FROM fleet_orders fo;
END;
GO

/* ---------------------------------------------------------
   Procedure: dbo.sp_driver_performance
   用途：司机绩效统计（时间段内运单数 + 异常明细列表）
   --------------------------------------------------------- */
CREATE OR ALTER PROCEDURE dbo.sp_driver_performance
    @driver_id INT,     -- 司机ID
    @start DATETIME,    -- 统计起始时间
    @end   DATETIME     -- 统计结束时间
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        @driver_id AS driver_id, -- 司机ID
        COUNT(*) AS total_orders -- 司机在时间段内的运单数量
    FROM orders
    WHERE driver_id = @driver_id
      AND created_at >= @start
      AND created_at < @end;

    SELECT
        e.event_id,                  -- 异常事件ID
        e.occurred_time,             -- 异常发生时间
        e.exception_type,            -- 异常类型
        e.status AS exception_status,-- 异常状态
        e.fine_amount,               -- 罚款金额
        e.description,               -- 异常描述

        o.order_id,                  -- 运单ID
        o.created_at,                -- 运单创建时间
        o.destination,               -- 运单目的地
        o.status AS order_status,    -- 运单状态

        v.vehicle_id,                -- 车辆ID
        v.license_plate_number       -- 车牌号
    FROM orders o
    JOIN vehicles v ON v.vehicle_id = o.vehicle_id
    JOIN exception_events e ON e.order_id = o.order_id
    WHERE o.driver_id = @driver_id
      AND o.created_at >= @start
      AND o.created_at < @end
    ORDER BY e.occurred_time DESC;
    -- 按异常发生时间倒序显示
END;
GO

