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
    @fleet_id INT,  -- 车队ID
    @year INT,      -- 年份
    @month INT      -- 月份
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @start DATETIME =
        DATETIMEFROMPARTS(@year, @month, 1, 0, 0, 0, 0);
        -- 统计区间起始时间（当月第一天）

    DECLARE @end DATETIME =
        DATEADD(MONTH, 1, @start);
        -- 统计区间结束时间（下月第一天）

    ;WITH fleet_orders AS (
        SELECT o.order_id
        FROM orders o
        JOIN vehicles v ON v.vehicle_id = o.vehicle_id
        WHERE v.fleet_id = @fleet_id
          AND o.created_at >= @start
          AND o.created_at < @end
          -- 筛选该车队在指定月份内的运单
    )
    SELECT
        @fleet_id AS fleet_id,   -- 返回车队ID
        @year AS [year],         -- 返回年份
        @month AS [month],       -- 返回月份

        (SELECT COUNT(*) FROM fleet_orders) AS total_orders,
        -- 运单总数

        (SELECT COUNT(*)
         FROM exception_events e
         JOIN fleet_orders fo ON fo.order_id = e.order_id
         WHERE e.occurred_time >= @start
           AND e.occurred_time < @end
        ) AS total_exceptions,
        -- 异常事件总数

        (SELECT ISNULL(SUM(e.fine_amount), 0)
         FROM exception_events e
         JOIN fleet_orders fo ON fo.order_id = e.order_id
         WHERE e.occurred_time >= @start
           AND e.occurred_time < @end
        ) AS total_fines;
        -- 罚款总金额
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
