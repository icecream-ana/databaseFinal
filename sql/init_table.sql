USE FleetDB
GO

-- 删除已存在的表（按照依赖关系）
DROP TABLE IF EXISTS history_log;
DROP TABLE IF EXISTS exception_events;
DROP TABLE IF EXISTS orders;
DROP TABLE IF EXISTS supervisors;
DROP TABLE IF EXISTS drivers;
DROP TABLE IF EXISTS vehicles;
DROP TABLE IF EXISTS fleets;
DROP TABLE IF EXISTS centers;

-- 配送中心表
CREATE TABLE centers (
    center_id INT IDENTITY(1,1) PRIMARY KEY,   -- 配送中心ID，主键，自增
    center_name NVARCHAR(100) NOT NULL,         -- 配送中心名称
);


-- 车队表
CREATE TABLE fleets (
    fleet_id INT IDENTITY(1,1) PRIMARY KEY,     -- 车队ID，主键，自增
    fleet_name NVARCHAR(100) NOT NULL,           -- 车队名称
    center_id INT NOT NULL,                      -- 所属配送中心ID（外键）

    FOREIGN KEY (center_id) REFERENCES centers(center_id)
    -- 外键约束：车队必须隶属于某个配送中心
);



-- 车辆表
CREATE TABLE vehicles (
    vehicle_id INT IDENTITY(1,1) PRIMARY KEY,   -- 车辆ID，主键，自增
    max_weight DECIMAL(10,2) NOT NULL,           -- 最大载重（kg）
    max_volume DECIMAL(10,2) NOT NULL,           -- 最大容积（立方米）
    fleet_id INT NOT NULL,                       -- 所属车队ID（外键）
    status NVARCHAR(20) NOT NULL DEFAULT N'空闲',-- 车辆状态：空闲 / 运输中 / 异常
    license_plate_number NVARCHAR(50) NOT NULL, -- 车牌号（唯一，但不作为主键）

    FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id),
    -- 外键约束：车辆必须属于某个车队

    CHECK (status IN (N'空闲', N'运输中', N'异常')),
    -- 状态完整性约束

    UNIQUE (license_plate_number)
    -- 车牌号唯一性约束
);



-- 司机表
CREATE TABLE drivers (
    driver_id INT IDENTITY(1,1) PRIMARY KEY,    -- 司机工号，主键，自增
    name NVARCHAR(50) NOT NULL,                  -- 司机姓名
    license_level NVARCHAR(10) NOT NULL,         -- 驾照等级（最高等级）
    phone NVARCHAR(50) NOT NULL,                 -- 联系方式
    fleet_id INT NOT NULL,                       -- 所属车队ID（外键）

    FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id),
    -- 外键约束：司机隶属于某个车队

    CHECK (license_level IN ('C1','C2','B2','A2'))
    -- 驾照等级约束
);


-- 主管表
CREATE TABLE supervisors (
    supervisor_id INT IDENTITY(1,1) PRIMARY KEY,-- 主管工号，主键，自增
    name NVARCHAR(50) NOT NULL,                  -- 主管姓名
    phone NVARCHAR(50) NOT NULL,                 -- 联系方式
    fleet_id INT NOT NULL,                       -- 所属车队ID（外键）

    FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id),
    -- 外键约束：主管隶属于某个车队

    UNIQUE (fleet_id)
    -- 唯一约束：一个车队只能有一个主管（1:1 关系）
);


-- 运单表
CREATE TABLE orders (
    order_id INT IDENTITY(1,1) PRIMARY KEY,     -- 运单ID，主键，自增
    weight DECIMAL(10,2) NOT NULL,               -- 货物重量（kg）
    volume DECIMAL(10,2) NOT NULL,               -- 货物体积（立方米）
    destination NVARCHAR(255) NOT NULL,          -- 目的地
    created_at DATETIME NOT NULL DEFAULT GETDATE(), 
                                                  -- 运单创建时间
    vehicle_id INT NOT NULL,                     -- 执行车辆ID（外键）
    driver_id INT NOT NULL,                      -- 执行司机ID（外键）
    status NVARCHAR(20) NOT NULL DEFAULT N'待分配',
                                                  -- 运单状态

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    -- 外键约束：运单由某辆车执行

    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    -- 外键约束：运单由某名司机执行

    CHECK (status IN (N'待分配', N'运输中', N'已完成', N'异常'))
    -- 运单状态完整性约束
);


-- 异常事件表
CREATE TABLE exception_events (
    event_id INT IDENTITY(1,1) PRIMARY KEY,     -- 异常事件ID，主键，自增
    order_id INT NOT NULL,                       -- 关联运单ID（外键）
    exception_type NVARCHAR(50) NOT NULL,        -- 异常类型
    fine_amount INT NOT NULL DEFAULT 0,          -- 罚款金额
    occurred_time DATETIME NOT NULL,             -- 异常发生时间
    description NVARCHAR(MAX) NOT NULL,          -- 异常详细描述
    status NVARCHAR(20) NOT NULL DEFAULT N'待处理',
                                                  -- 异常处理状态

    FOREIGN KEY (order_id) REFERENCES orders(order_id),
    -- 外键约束：异常事件必须关联某个运单

    CHECK (exception_type IN (N'运输时异常', N'空闲时异常')),
    -- 异常类型约束

    CHECK (status IN (N'待处理', N'处理中', N'已处理'))
    -- 异常处理状态约束
);


-- 审计日志表
CREATE TABLE history_log (
    log_id INT IDENTITY(1,1) PRIMARY KEY,        -- 日志ID，主键，自增
    table_name NVARCHAR(50) NOT NULL,            -- 被修改的表名
    change_id INT NOT NULL,                      -- 被修改记录的主键ID
    operation_type NVARCHAR(50) NOT NULL,        -- 操作类型说明
    old_data NVARCHAR(MAX) NOT NULL,             -- 修改前数据（JSON / 文本）
    change_at DATETIME NOT NULL DEFAULT GETDATE()-- 修改时间
);

