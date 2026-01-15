/* =========================================================
   File: init_data.sql

   初始化数据规模：
     - 配送中心（centers）：2 个
     - 每个配送中心下设车队（fleets）：5 个（共 10 个）
     - 每个车队：
         * 车辆（vehicles）：5 辆
         * 司机（drivers）：5 名
         * 主管（supervisors）：1 名

     - 运单表（orders）为空
     - 异常事件表（exception_events）为空
     - 审计日志表（history_log）为空

   执行说明：
     - 本脚本在执行前会清空已有数据（按外键依赖顺序）
     - 适用于开发/测试/课程演示环境
     - 需在 init_table.sql 执行完成后运行
   ========================================================= */


USE FleetDB;
GO

SET NOCOUNT ON;

BEGIN TRY
    BEGIN TRAN;

    /* =========================================================
       0) 清空数据（按依赖顺序）
       要求：orders / exception_events / history_log 为空
       ========================================================= */
    DELETE FROM history_log;
    DELETE FROM exception_events;
    DELETE FROM orders;

    DELETE FROM supervisors;
    DELETE FROM drivers;
    DELETE FROM vehicles;
    DELETE FROM fleets;
    DELETE FROM centers;

    /* =========================================================
       1) 插入 2 个配送中心
       ========================================================= */
    DECLARE @Centers TABLE (
        center_id   INT PRIMARY KEY,
        center_name NVARCHAR(100)
    );

    INSERT INTO centers (center_name)
    OUTPUT inserted.center_id, inserted.center_name
    INTO @Centers(center_id, center_name)
    VALUES
        (N'华东配送中心'),
        (N'华南配送中心');

    /* =========================================================
       2) 每个中心插入 5 个车队（共 10 个）
       ========================================================= */
    DECLARE @Fleets TABLE (
        fleet_id   INT PRIMARY KEY,
        fleet_name NVARCHAR(100),
        center_id  INT
    );

    ;WITH n AS (
        SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
    )
    INSERT INTO fleets (fleet_name, center_id)
    OUTPUT inserted.fleet_id, inserted.fleet_name, inserted.center_id
    INTO @Fleets(fleet_id, fleet_name, center_id)
    SELECT
        CONCAT(c.center_name, N'-车队', n.n) AS fleet_name,
        c.center_id
    FROM @Centers c
    CROSS JOIN n;

    /* =========================================================
       3) 每个车队插入 5 辆车（共 50 辆）
       - status 使用默认值“空闲”
       - 车牌号符合中国大陆普通号牌格式：省份简称 + 字母 + 5位编号（示例：沪A12345）
       - 车牌号保证唯一（通过 fleet_id + n 生成唯一序号）
       ========================================================= */
    ;WITH n AS (
        SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
    )
    INSERT INTO vehicles (max_weight, max_volume, fleet_id, license_plate_number)
    SELECT
        CAST(8000 + (f.fleet_id % 5) * 500 + n.n * 50 AS DECIMAL(10,2))  AS max_weight, -- 8.0t 起
        CAST(35   + (f.fleet_id % 5) * 2   + n.n * 0.5 AS DECIMAL(10,2)) AS max_volume, -- 35m³ 起
        f.fleet_id,

        -- 车牌号：省份简称 + 城市字母 + 5位编号（00001-99999）
        CONCAT(
            CASE f.center_id
                WHEN 1 THEN N'沪'  -- 华东配送中心（示例：上海）
                WHEN 2 THEN N'粤'  -- 华南配送中心（示例：广东）
                ELSE N'京'
            END,
            CHAR(65 + ((f.fleet_id - 1) % 26)),  -- A-Z（按 fleet_id 映射）
            RIGHT(CONCAT('00000', CAST((f.fleet_id * 10 + n.n) AS VARCHAR(10))), 5)
        ) AS license_plate_number
    FROM @Fleets f
    CROSS JOIN n;


    /* =========================================================
       4) 每个车队插入 5 名司机（共 50 名）
       - license_level ∈ {C1,C2,B2,A2}
       ========================================================= */
    ;WITH n AS (
        SELECT 1 AS n UNION ALL SELECT 2 UNION ALL SELECT 3 UNION ALL SELECT 4 UNION ALL SELECT 5
    )
    INSERT INTO drivers (name, license_level, phone, fleet_id)
    SELECT
        CONCAT(f.fleet_name, N'-司机', n.n) AS name,
        CASE n.n
            WHEN 1 THEN 'C2'
            WHEN 2 THEN 'C1'
            WHEN 3 THEN 'B2'
            WHEN 4 THEN 'A2'
            ELSE 'C1'
        END AS license_level,
        CONCAT(N'138', RIGHT(CONCAT(N'00000000', CAST(f.fleet_id * 10 + n.n AS NVARCHAR(10))), 8)) AS phone,
        f.fleet_id
    FROM @Fleets f
    CROSS JOIN n;

    /* =========================================================
       5) 每个车队插入 1 名主管（共 10 名）
       - supervisors.fleet_id 有 UNIQUE 约束：一个车队只能有一个主管
       ========================================================= */
    INSERT INTO supervisors (name, phone, fleet_id)
    SELECT
        CONCAT(f.fleet_name, N'-主管') AS name,
        CONCAT(N'139', RIGHT(CONCAT(N'00000000', CAST(f.fleet_id AS NVARCHAR(10))), 8)) AS phone,
        f.fleet_id
    FROM @Fleets f;

    COMMIT TRAN;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRAN;

    DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
    RAISERROR(N'初始化数据脚本执行失败：%s', 16, 1, @msg);
END CATCH;
GO
