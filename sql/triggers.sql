USE FleetDB
GO

-- Trigger 1: 自动载重校验
-- 当向一辆车分配运单时，检查该车“当前已分配货物重量 + 新运单重量”是否超过“车辆最大载重”。
CREATE OR ALTER TRIGGER trg_check_vehicle_capacity
ON orders
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 仅当涉及 vehicle_id 或 weight 或 status 变更时检查
    IF NOT (UPDATE(vehicle_id) OR UPDATE(weight) OR UPDATE(status))
        RETURN;

    -- 检查每一个受影响的车辆
    IF EXISTS (
        SELECT 1
        FROM vehicles v
        JOIN (
            -- 计算每辆车当前的活跃总重量（包括本次新增/修改后的数据，因为是 AFTER TRIGGER）
            -- 活跃运单状态通常为：待分配、运输中。
            -- 如果 UPDATE 把运单改为 '已完成'，则不会计入重量（符合逻辑）
            SELECT vehicle_id, SUM(weight) AS current_total_weight
            FROM orders
            WHERE status IN (N'待分配', N'运输中') -- 假设仅这两种状态占用载重
            GROUP BY vehicle_id
        ) o_sum ON v.vehicle_id = o_sum.vehicle_id
        WHERE o_sum.current_total_weight > v.max_weight
    )
    BEGIN
        RAISERROR (N'车辆超载！当前已分配货物重量超过车辆最大载重。', 16, 1);
        ROLLBACK TRANSACTION;
        RETURN;
    END
END;
GO

-- Trigger 2: 车辆/运单状态自动流转
-- A. 运单完成 -> 车辆空闲
-- B. 异常处理完成 -> 车辆恢复
CREATE OR ALTER TRIGGER trg_vehicle_status_auto_update
ON orders
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 场景 A: 运单状态变更引发的车辆状态流转
    IF UPDATE(status)
    BEGIN
        -- 1. 当运单状态从“待分配”变为“运输中”时，若对应车辆当前处于空闲状态，则将其转换为“运输中”
        UPDATE v
        SET status = N'运输中'
        FROM vehicles v
        JOIN inserted i ON v.vehicle_id = i.vehicle_id
        JOIN deleted d ON i.order_id = d.order_id
        WHERE i.status = N'运输中' 
          AND d.status = N'待分配' 
          AND v.status = N'空闲';

        -- 2. 当运单状态变为“已完成”时，检查是否可以释放车辆
        -- 找出所有在本次更新中涉及的车辆，且该车辆目前状态为 '运输中'
        -- 检查这些车辆是否还有未完成的运单
        
        DECLARE @FinishedVehicleIds TABLE (vehicle_id INT);

        INSERT INTO @FinishedVehicleIds (vehicle_id)
        SELECT DISTINCT i.vehicle_id
        FROM inserted i
        JOIN vehicles v ON i.vehicle_id = v.vehicle_id
        WHERE i.status = N'已完成' 
          AND v.status = N'运输中'; -- 仅处理当前在运输中的车

        -- 如果某辆车没有任何“待分配”或“运输中”或“异常”的运单，则视为空闲
        UPDATE v
        SET status = N'空闲'
        FROM vehicles v
        JOIN @FinishedVehicleIds fv ON v.vehicle_id = fv.vehicle_id
        WHERE NOT EXISTS (
            SELECT 1 
            FROM orders o 
            WHERE o.vehicle_id = v.vehicle_id 
              AND o.status IN (N'待分配', N'运输中', N'异常') -- 只要还有活或是异常单，就不是空闲
        );
    END
END;
GO

-- 针对异常表发生的 Trigger (Trigger 2 Part C: 异常发生)
-- 当异常发生时，对应运单和车辆状态变为“异常”
CREATE OR ALTER TRIGGER trg_exception_occurred_vehicle_status
ON exception_events
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    -- 1. 更新运单状态为“异常”
    UPDATE o
    SET status = N'异常'
    FROM orders o
    JOIN inserted i ON o.order_id = i.order_id
    WHERE o.status <> N'异常';

    -- 2. 更新车辆状态为“异常”
    UPDATE v
    SET status = N'异常'
    FROM vehicles v
    JOIN orders o ON v.vehicle_id = o.vehicle_id
    JOIN inserted i ON o.order_id = i.order_id
    WHERE v.status <> N'异常';
END;
GO

-- 针对异常表处理的 Trigger (Trigger 2 Part B)
CREATE OR ALTER TRIGGER trg_exception_handled_vehicle_status
ON exception_events
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 场景 B: 当异常状态变为“已处理”
    IF UPDATE(status)
    BEGIN
        -- 查找本次变为“已处理”的记录
        SELECT 
            i.exception_type,
            o.vehicle_id,
            i.order_id
        INTO #HandledExceptions
        FROM inserted i
        JOIN deleted d ON i.event_id = d.event_id
        JOIN orders o ON i.order_id = o.order_id
        WHERE i.status = N'已处理' AND d.status <> N'已处理'; -- 状态流转检测
        
        -- 更新运单状态：只要异常被处理，且运单当前是“异常”状态，均恢复为“运输中”
        -- (注：空闲时异常通常不关联运输中运单，但如果有关联则同样处理)
        UPDATE o
        SET status = N'运输中'
        FROM orders o
        JOIN #HandledExceptions he ON o.order_id = he.order_id
        WHERE o.status = N'异常';

        -- 更新车辆状态
        -- 1. 运输时异常 -> 恢复为“运输中” (假设任务继续) 或 “空闲” (如果没有任务)
        --    题目说：取决于异常类型。此处简化逻辑：
        --    如果是“运输时异常”，通常车上还有货，恢复为“运输中”。
        UPDATE v
        SET status = N'运输中'
        FROM vehicles v
        JOIN #HandledExceptions he ON v.vehicle_id = he.vehicle_id
        WHERE he.exception_type = N'运输时异常' 
          AND v.status = N'异常'; -- 只有当前是异常状态才恢复

        -- 2. 空闲时异常 -> 恢复为“空闲”
        UPDATE v
        SET status = N'空闲'
        FROM vehicles v
        JOIN #HandledExceptions he ON v.vehicle_id = he.vehicle_id
        WHERE he.exception_type = N'空闲时异常'
          AND v.status = N'异常';
          
        DROP TABLE #HandledExceptions;
    END
END;
GO

-- Trigger 3: 审计日志
-- 当修改司机的关键信息（如驾照等级）或异常记录被处理时，自动备份旧数据。
CREATE OR ALTER TRIGGER trg_audit_log_drivers
ON drivers
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 检测关键字段变更：驾照等级 (还可以加 name, phone 等)
    IF UPDATE(license_level) OR UPDATE(name) OR UPDATE(phone)
    BEGIN
        INSERT INTO history_log (table_name, change_id, operation_type, old_data)
        SELECT 
            'drivers',
            d.driver_id,
            'UPDATE_KEY_INFO',
            (SELECT d.* FOR JSON PATH, WITHOUT_ARRAY_WRAPPER) -- 将旧行数据转为 JSON
        FROM deleted d;
    END
END;
GO

CREATE OR ALTER TRIGGER trg_audit_log_exceptions
ON exception_events
AFTER UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    -- 当异常记录被处理时 (status 变为 '已处理')
    -- 或者只要是 update 也可以记录，题目重点强调“被处理时”
    -- 这里实现为：只要状态变更为“已处理”，就记录变更前的状态
    IF UPDATE(status)
    BEGIN
        INSERT INTO history_log (table_name, change_id, operation_type, old_data)
        SELECT 
            'exception_events',
            d.event_id,
            'EXCEPTION_PROCESSED',
            (SELECT d.* FOR JSON PATH, WITHOUT_ARRAY_WRAPPER)
        FROM deleted d
        JOIN inserted i ON d.event_id = i.event_id
        WHERE i.status = N'已处理' 
          AND d.status <> N'已处理';
    END
END;
GO
