-- ============================================================
-- SQL Server Trigger 测试脚本 (修正版)
-- 说明：该脚本用于测试触发器的功能验证。
-- 请按顺序执行。每次执行前可以清空数据以保证环境纯净。
-- ============================================================

-- 0. 清理旧数据 (按照依赖关系倒序删除)
USE FleetDB
GO

DELETE FROM history_log;
DELETE FROM exception_events;
DELETE FROM orders;
DELETE FROM supervisors;
DELETE FROM drivers;
DELETE FROM vehicles;
DELETE FROM fleets;
DELETE FROM centers;
GO

PRINT '=== 0. 环境初始化完成 ===';
GO

-- 1. 插入基础测试数据
INSERT INTO centers (center_name) VALUES (N'北京配送中心');
DECLARE @CenterID INT = SCOPE_IDENTITY();

INSERT INTO fleets (fleet_name, center_id) VALUES (N'第一车队', @CenterID);
DECLARE @FleetID INT = SCOPE_IDENTITY();

-- 插入一辆最大载重为 1000kg 的车
INSERT INTO vehicles (max_weight, max_volume, fleet_id, status, license_plate_number) 
VALUES (1000.00, 50.00, @FleetID, N'空闲', N'京A88888');

INSERT INTO drivers (name, license_level, phone, fleet_id) 
VALUES (N'张三', N'A2', N'13800138000', @FleetID);

PRINT '=== 1. 基础数据准备完成 ===';
PRINT '   Vehicle Max Weight: 1000.00';
GO

-- ============================================================
-- 测试场景 1: 自动载重校验 (Trigger: trg_check_vehicle_capacity)
-- ============================================================
PRINT ' ';
PRINT '--- 开始测试 Trigger 1: 自动载重校验 ---';
GO

-- 1.1 正常插入测试 (500kg <= 1000kg)
-- 预期：成功
BEGIN TRY
    DECLARE @VehicleID INT = (SELECT TOP 1 vehicle_id FROM vehicles);
    DECLARE @DriverID INT = (SELECT TOP 1 driver_id FROM drivers);

    INSERT INTO orders (weight, volume, destination, vehicle_id, driver_id, status)
    VALUES (500.00, 10.00, N'地点A', @VehicleID, @DriverID, N'待分配');
    
    PRINT 'Test 1.1 [正常插入]: 成功 (PASSED)';
END TRY
BEGIN CATCH
    PRINT 'Test 1.1 [正常插入]: 失败 - 意外报错: ' + ERROR_MESSAGE();
END CATCH;
GO

-- 1.2 超载插入测试 (现有500 + 新增600 = 1100 > 1000)
-- 预期：失败并抛出错误
BEGIN TRY
    DECLARE @VehicleID INT = (SELECT TOP 1 vehicle_id FROM vehicles);
    DECLARE @DriverID INT = (SELECT TOP 1 driver_id FROM drivers);

    INSERT INTO orders (weight, volume, destination, vehicle_id, driver_id, status)
    VALUES (600.00, 10.00, N'地点B', @VehicleID, @DriverID, N'待分配');

    PRINT 'Test 1.2 [超载插入]: 失败 - 未拦截超载 (FAILED)';
END TRY
BEGIN CATCH
    PRINT 'Test 1.2 [超载插入]: 成功 - 捕获预期错误: ' + ERROR_MESSAGE() + ' (PASSED)';
END CATCH;
GO

-- 1.3 超载更新测试 (将原有500kg订单改为1200kg)
-- 预期：失败并抛出错误
BEGIN TRY
    DECLARE @VehicleID INT = (SELECT TOP 1 vehicle_id FROM vehicles);
    
    -- 找到刚才插入的那个订单
    UPDATE orders 
    SET weight = 1200.00 
    WHERE vehicle_id = @VehicleID AND status = N'待分配';

    PRINT 'Test 1.3 [超载更新]: 失败 - 未拦截超载 (FAILED)';
END TRY
BEGIN CATCH
    PRINT 'Test 1.3 [超载更新]: 成功 - 捕获预期错误: ' + ERROR_MESSAGE() + ' (PASSED)';
END CATCH;
GO

-- ============================================================
-- 测试场景 2: 车辆状态自动流转 (Trigger: trg_vehicle_status_auto_update)
-- ============================================================
PRINT ' ';
PRINT '--- 开始测试 Trigger 2: 车辆状态自动流转 ---';
GO

DECLARE @VehicleID INT = (SELECT TOP 1 vehicle_id FROM vehicles);
DECLARE @CurrStatus NVARCHAR(50);

-- 预设环境：将车辆状态设为“运输中”，并将已有订单设为“运输中”
UPDATE vehicles SET status = N'运输中' WHERE vehicle_id = @VehicleID;
UPDATE orders SET status = N'运输中' WHERE vehicle_id = @VehicleID;

SELECT @CurrStatus = status FROM vehicles WHERE vehicle_id = @VehicleID;
PRINT '   当前车辆状态: ' + @CurrStatus;

-- 2.1 运单完成 -> 车辆变空闲
-- 操作：将该车所有运单设为“已完成”
UPDATE orders SET status = N'已完成' WHERE vehicle_id = @VehicleID;

DECLARE @NewStatus NVARCHAR(50);
SELECT @NewStatus = status FROM vehicles WHERE vehicle_id = @VehicleID;

IF @NewStatus = N'空闲'
    PRINT 'Test 2.1 [运单全完成 -> 空闲]: 成功 (PASSED)';
ELSE
    PRINT 'Test 2.1 [运单全完成 -> 空闲]: 失败, 当前状态: ' + @NewStatus + ' (FAILED)';
GO

-- ============================================================
-- 测试场景 2(续): 异常处理流转 (Trigger: trg_exception_handled_vehicle_status)
-- ============================================================
PRINT ' ';
PRINT '--- 开始测试 Trigger 2(续): 异常处理流转 ---';
GO

DECLARE @VehicleID INT = (SELECT TOP 1 vehicle_id FROM vehicles);
DECLARE @DriverID INT = (SELECT TOP 1 driver_id FROM drivers);
DECLARE @CurrStatus NVARCHAR(50);

-- 预设环境：车辆状态“异常”，有一个“运输中”的订单（用来挂载异常）
UPDATE vehicles SET status = N'异常' WHERE vehicle_id = @VehicleID;

-- 插入一个新订单用于关联异常
INSERT INTO orders (weight, volume, destination, vehicle_id, driver_id, status)
VALUES (100.00, 5.00, N'异常测试单', @VehicleID, @DriverID, N'运输中');
DECLARE @OrderId INT = SCOPE_IDENTITY();

-- 2.2 插入异常事件 (运输时异常)
INSERT INTO exception_events (order_id, exception_type, occurred_time, description, status)
VALUES (@OrderId, N'运输时异常', GETDATE(), N'车辆故障', N'待处理');
DECLARE @EventID INT = SCOPE_IDENTITY();

SELECT @CurrStatus = status FROM vehicles WHERE vehicle_id = @VehicleID;
PRINT '   当前车辆状态(应为异常): ' + @CurrStatus;

-- 操作：处理异常
UPDATE exception_events SET status = N'已处理' WHERE event_id = @EventID;

DECLARE @NewStatus NVARCHAR(50);
SELECT @NewStatus = status FROM vehicles WHERE vehicle_id = @VehicleID;

-- 预期：运输时异常处理后，车辆恢复为“运输中”（因为属于运输过程中的恢复）
IF @NewStatus = N'运输中'
    PRINT 'Test 2.2 [运输异常处理 -> 恢复运输]: 成功 (PASSED)';
ELSE
    PRINT 'Test 2.2 [运输异常处理 -> 恢复运输]: 失败, 当前状态: ' + @NewStatus + ' (FAILED)';
GO

-- ============================================================
-- 测试场景 3: 审计日志 (Trigger: trg_audit_log_drivers / trg_audit_log_exceptions)
-- ============================================================
PRINT ' ';
PRINT '--- 开始测试 Trigger 3: 审计日志 ---';
GO

-- 3.1 司机信息修改审计
DECLARE @DriverID INT = (SELECT TOP 1 driver_id FROM drivers);
DECLARE @OldLevel NVARCHAR(50);
DECLARE @NewLevel NVARCHAR(50);

SELECT @OldLevel = license_level FROM drivers WHERE driver_id = @DriverID;
PRINT '   修改前司机等级: ' + @OldLevel;

-- 操作：修改司机等级
UPDATE drivers SET license_level = N'C2' WHERE driver_id = @DriverID;

SELECT @NewLevel = license_level FROM drivers WHERE driver_id = @DriverID;
PRINT '   修改后司机等级: ' + @NewLevel;

-- 验证：检查日志
IF EXISTS (
    SELECT 1 FROM history_log 
    WHERE table_name = 'drivers' 
      AND change_id = @DriverID 
      AND operation_type = 'UPDATE_KEY_INFO'
      AND old_data LIKE '%"license_level":"A2"%'
)
    PRINT 'Test 3.1 [司机修改日志]: 成功 (PASSED)';
ELSE
    PRINT 'Test 3.1 [司机修改日志]: 失败 - 未找到符合条件的日志记录 (FAILED)';
GO

-- 3.2 异常处理审计
-- 在 Test 2.2 中我们已经将一个异常更新为“已处理”，此时应该已经触发了日志
DECLARE @EventID INT = (SELECT TOP 1 event_id FROM exception_events WHERE status = N'已处理');

IF EXISTS (
    SELECT 1 FROM history_log
    WHERE table_name = 'exception_events'
      AND change_id = @EventID
      AND operation_type = 'EXCEPTION_PROCESSED'
)
    PRINT 'Test 3.2 [异常处理日志]: 成功 (PASSED)';
ELSE
    PRINT 'Test 3.2 [异常处理日志]: 失败 - 未找到符合条件的日志记录 (FAILED)';
GO
