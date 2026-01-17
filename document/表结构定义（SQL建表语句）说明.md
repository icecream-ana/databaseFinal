# 表结构定义（SQL建表语句）说明

## 一、数据库总体设计说明

- **数据库名称**：`FleetDB`

- **应用背景**：城市配送车队管理系统。系统围绕“配送中心 – 车队 – 车辆/司机 – 运单 – 异常事件”这条业务链路进行建模，并通过审计日志记录关键业务数据的历史变化。

- **主要业务对象**：
  
  - 配送中心（centers）
  
  - 车队（fleets）
  
  - 车辆（vehicles）
  
  - 司机（drivers）
  
  - 主管（supervisors）
  
  - 运单（orders）
  
  - 异常事件（exception_events）
  
  - 审计日志（history_log）

## 二、表间关系概述

- 一个配送中心 `centers` 下可以有多个车队 `fleets`（1:N）。

- 一个车队 `fleets` 下可以有多辆车辆 `vehicles`、多名司机 `drivers`，并且对应一个主管 `supervisors`（1:N 和 1:1）。

- 一辆车辆 `vehicles` 可以执行多张运单 `orders`（1:N）。

- 一名司机 `drivers` 可以执行多张运单 `orders`（1:N）。

- 一张运单 `orders` 可以产生多条异常事件 `exception_events`（1:N）。

- `history_log` 作为通用审计日志表，通过逻辑字段记录各业务表的历史变更，不与具体业务表建立外键约束

## 三、各表结构定义

### 3.1 centers表（配送中心表）

**业务含义**：记录公司所有配送中心的基础信息，为车队提供组织归属。

**字段定义**

| 字段名         | 数据类型              | 约束          | 含义           |
| ----------- | ----------------- | ----------- | ------------ |
| center_id   | INT IDENTITY(1,1) | PRIMARY KEY | 配送中心ID、主键，自增 |
| center_name | NVARCHAR(100)     | NOT NULL    | 配送中心名称       |

**建表语句**

```sql
CREATE TABLE centers (
    center_id INT IDENTITY(1,1) PRIMARY KEY,   -- 配送中心ID，主键，自增
    center_name NVARCHAR(100) NOT NULL         -- 配送中心名称
);
```

### 3.2 fleets表（车队表）

**业务含义**：记录每个车队的名称以及隶属的配送中心

**字段定义**

| 字段名        | 数据类型              | 约束                    | 含义         |
| ---------- | ----------------- | --------------------- | ---------- |
| fleet_id   | INT IDENTITY(1,1) | PRIMARY KEY           | 车队ID、主键，自增 |
| fleet_name | NVARCHAR(100)     | NOT NULL              | 车队名称       |
| center_id  | INT               | NOT NULL, FOREIGN KEY | 所属配送中心ID   |

**约束说明**

- `FOREIGN KEY (center_id) REFERENCES centers(center_id)`
  
  车队必须隶属于某个已存在的配送中心

**建表语句**

```sql
CREATE TABLE fleets (
    fleet_id INT IDENTITY(1,1) PRIMARY KEY,     -- 车队ID，主键，自增
    fleet_name NVARCHAR(100) NOT NULL,           -- 车队名称
    center_id INT NOT NULL,                      -- 所属配送中心ID（外键）

    FOREIGN KEY (center_id) REFERENCES centers(center_id)
    -- 外键约束：车队必须隶属于某个配送中心
);
```

### 3.3 vehicles表（车辆表）

**业务含义**：记录车队下所有车辆的基本信息和能力参数，用于运单分配与车辆状态管理。

**字段定义**

| 字段名                  | 数据类型              | 约束                             | 含义             |
| -------------------- | ----------------- | ------------------------------ | -------------- |
| vehicle_id           | INT IDENTITY(1,1) | PRIMARY KEY                    | 车辆ID、主键，自增     |
| max_weight           | DECIMAL(10,2)     | NOT NULL                       | 最大载重（kg）       |
| max_volume           | DECIMAL(10,2)     | NOT NULL                       | 最大容积（立方米）      |
| fleet_id             | INT               | NOT NULL, FOREIGN KEY          | 所属车队ID（外键）     |
| status               | NVARCHAR(20)      | NOT NULL, DEFAULT N'空闲', CHECK | 车辆状态：空闲/运输中/异常 |
| license_plate_number | NVARCHAR(50)      | NOT NULL, UNIQUE               | 车牌号（唯一）        |

**约束说明**

- `FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id)`：车辆必须属于某个车队。

- `CHECK (status IN (N'空闲', N'运输中', N'异常'))`：车辆状态枚举约束。

- `UNIQUE (license_plate_number)`：车牌号在系统中唯一。

**建表语句**

```sql
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

```

### 3.4 drivers表（司机表）

**业务含义**：记录车队司机的基本信息、驾照等级及所属车队。

**字段含义**

| 字段名           | 数据类型              | 约束                    | 含义         |
| ------------- | ----------------- | --------------------- | ---------- |
| driver_id     | INT IDENTITY(1,1) | PRIMARY KEY           | 司机工号，主键、自增 |
| name          | NVARCHAR(50)      | NOT NULL              | 司机姓名       |
| license_level | NVARCHAR(10)      | NOT NULL, CHECK       | 驾照等级       |
| phone         | NVARCHAR(50)      | NOT NULL              | 联系方式       |
| fleet_id      | INT               | NOT NULL, FOREIGN KEY | 所属车队ID（外键） |

**约束说明**

- `FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id)`：司机必须隶属于某个车队。

- `CHECK (license_level IN ('A2','B2','C1','C2'))`：限定驾照等级为 A2/B2/C1/C2

**建表语句**

```sql
CREATE TABLE drivers (
    driver_id INT IDENTITY(1,1) PRIMARY KEY,    -- 司机工号，主键，自增
    name NVARCHAR(50) NOT NULL,                  -- 司机姓名
    license_level NVARCHAR(10) NOT NULL,         -- 驾照等级（最高等级）
    phone NVARCHAR(50) NOT NULL,                 -- 联系方式
    fleet_id INT NOT NULL,                       -- 所属车队ID（外键）

    FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id),
    -- 外键约束：司机隶属于某个车队

    CHECK (license_level IN ('A2','B2','C1','C2'))
    -- 驾照等级约束
);
```

### 3.5 supervisors表（主管表）

**业务含义**：记录车队主管的信息，每个车队最多一个主管。

**字段定义**

| 字段名           | 数据类型              | 约束                            | 含义         |
| ------------- | ----------------- | ----------------------------- | ---------- |
| supervisor_id | INT IDENTITY(1,1) | PRIMARY KEY                   | 主管工号，主键、自增 |
| name          | NVARCHAR(50)      | NOT NULL                      | 主管姓名       |
| phone         | NVARCHAR(50)      | NOT NULL                      | 联系方式       |
| fleet_id      | INT               | NOT NULL, FOREIGN KEY, UNIQUE | 所属车队ID（唯一） |

**约束说明**

- `FOREIGN KEY (fleet_id) REFERENCES fleets(fleet_id)`：主管隶属于某个车队。

- `UNIQUE (fleet_id)`：同一个车队最多只能对应一个主管，实现 1:1 关系。

**建表语句**

```sql
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
```

### 3.6 orders表（运单表）

**业务含义**：记录货物运输任务，包括货量、目的地、创建时间、分配车辆与司机及运单状态。

**字段定义**

| 字段名         | 数据类型              | 约束                              | 含义               |
| ----------- | ----------------- | ------------------------------- | ---------------- |
| order_id    | INT IDENTITY(1,1) | PRIMARY KEY                     | 运单ID，主键、自增       |
| weight      | DECIMAL(10,2)     | NOT NULL                        | 货物重量（kg）         |
| volume      | DECIMAL(10,2)     | NOT NULL                        | 货物体积（立方米）        |
| destination | NVARCHAR(255)     | NOT NULL                        | 目的地              |
| created_at  | DATETIME          | NOT NULL, DEFAULT GETDATE()     | 运单创建时间           |
| vehicle_id  | INT               | NULL, FOREIGN KEY               | 执行车辆ID（可空，表示待分配） |
| driver_id   | INT               | NULL, FOREIGN KEY               | 执行司机ID（可空，表示待分配） |
| status      | NVARCHAR(20)      | NOT NULL, DEFAULT N'待分配', CHECK | 运单状态             |

**约束说明**

- `FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id)`：运单由某辆车辆执行。

- `FOREIGN KEY (driver_id) REFERENCES drivers(driver_id)`：运单由某名司机执行。

- `CHECK (status IN (N'待分配', N'运输中', N'已完成', N'异常'))`：运单状态枚举约束。

**建表语句**

```sql
CREATE TABLE orders (
    order_id INT IDENTITY(1,1) PRIMARY KEY,     -- 运单ID，主键，自增
    weight DECIMAL(10,2) NOT NULL,               -- 货物重量（kg）
    volume DECIMAL(10,2) NOT NULL,               -- 货物体积（立方米）
    destination NVARCHAR(255) NOT NULL,          -- 目的地
    created_at DATETIME NOT NULL DEFAULT GETDATE(), 
                                                  -- 运单创建时间
    vehicle_id INT NULL,                     -- 执行车辆ID（外键，允许为空，表示待分配）
    driver_id INT NULL,                      -- 执行司机ID（外键，允许为空，表示待分配）
    status NVARCHAR(20) NOT NULL DEFAULT N'待分配',
                                                  -- 运单状态

    FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
    -- 外键约束：运单由某辆车执行

    FOREIGN KEY (driver_id) REFERENCES drivers(driver_id),
    -- 外键约束：运单由某名司机执行

    CHECK (status IN (N'待分配', N'运输中', N'已完成', N'异常'))
    -- 运单状态完整性约束
);
```

### 3.7 exception_events表（异常事件表）

**业务含义**：记录运单在执行过程中发生的异常，包括异常类型、罚款金额及处理状态。

**字段定义**

| 字段名            | 数据类型              | 约束                              | 含义           |
| -------------- | ----------------- | ------------------------------- | ------------ |
| event_id       | INT IDENTITY(1,1) | PRIMARY KEY                     | 异常事件ID，主键、自增 |
| order_id       | INT               | NOT NULL, FOREIGN KEY           | 关联运单ID（外键）   |
| exception_type | NVARCHAR(50)      | NOT NULL, CHECK                 | 异常类型         |
| fine_amount    | INT               | NOT NULL, DEFAULT 0             | 罚款金额         |
| occurred_time  | DATETIME          | NOT NULL                        | 异常发生时间       |
| description    | NVARCHAR(MAX)     | NOT NULL                        | 异常详细描述       |
| status         | NVARCHAR(20)      | NOT NULL, DEFAULT N'待处理', CHECK | 异常处理状态       |

**约束说明**

- `FOREIGN KEY (order_id) REFERENCES orders(order_id)`：异常必须挂在某张运单上。

- `CHECK (exception_type IN (N'运输时异常', N'空闲时异常'))`：异常类型固定两类。

- `CHECK (status IN (N'待处理', N'处理中', N'已处理'))`：异常处理状态枚举。

**建表语句**

```sql
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
```

### 3.8 history_log表（审计日志表）

**业务含义**：记录关键业务表（例如司机信息、异常处理等）被修改前的旧数据，用于审计追踪。

**字段定义**

| 字段名            | 数据类型              | 约束                          | 含义               |
| -------------- | ----------------- | --------------------------- | ---------------- |
| log_id         | INT IDENTITY(1,1) | PRIMARY KEY                 | 日志ID，主键、自增       |
| table_name     | NVARCHAR(50)      | NOT NULL                    | 被修改的表名           |
| change_id      | INT               | NOT NULL                    | 被修改记录的主键ID       |
| operation_type | NVARCHAR(50)      | NOT NULL                    | 操作类型说明           |
| old_data       | NVARCHAR(MAX)     | NOT NULL                    | 修改前数据（JSON / 文本） |
| change_at      | DATETIME          | NOT NULL, DEFAULT GETDATE() | 修改时间             |

**建表语句**

```sql
-- 审计日志表
CREATE TABLE history_log (
    log_id INT IDENTITY(1,1) PRIMARY KEY,        -- 日志ID，主键，自增
    table_name NVARCHAR(50) NOT NULL,            -- 被修改的表名
    change_id INT NOT NULL,                      -- 被修改记录的主键ID
    operation_type NVARCHAR(50) NOT NULL,        -- 操作类型说明
    old_data NVARCHAR(MAX) NOT NULL,             -- 修改前数据（JSON / 文本）
    change_at DATETIME NOT NULL DEFAULT GETDATE()-- 修改时间
);
```