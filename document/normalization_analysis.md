# 数据库规范化分析报告

本报告对 `init_table.sql` 中定义的数据库表结构进行规范化分析，检查其是否满足第三范式 (3NF)。

## 1. 概念与定义

*   **第一范式 (1NF)**: 强调列的原子性，即数据库表的每一列都是不可分割的原子数据项。
*   **第二范式 (2NF)**: 在满足 1NF 的基础上，消除非主属性对码的部分函数依赖（即非主属性必须完全依赖于主键）。
*   **第三范式 (3NF)**: 在满足 2NF 的基础上，消除非主属性对码的传递函数依赖（即非主属性不依赖于其他非主属性）。

## 2. 表结构分析

### 2.1 配送中心表 (centers)
*   **结构**: `center_id` (PK), `center_name`
*   **分析**:
    *   **1NF**: 所有字段均为原子值。
    *   **2NF**: 主键为单列 `center_id`，不存在部分依赖。
    *   **3NF**: `center_name` 直接依赖于 `center_id`，不存在传递依赖。
*   **结论**: 满足 **3NF**。

### 2.2 车队表 (fleets)
*   **结构**: `fleet_id` (PK), `fleet_name`, `center_id` (FK)
*   **分析**:
    *   **1NF**: 字段均为原子值。
    *   **2NF**: 主键为单列，不存在部分依赖。
    *   **3NF**: `fleet_name` 和 `center_id` 都直接依赖于 `fleet_id`。`center_id` 是外键，指向 `centers` 表，不存在非主属性决定其他非主属性的情况。
*   **结论**: 满足 **3NF**。

### 2.3 车辆表 (vehicles)
*   **结构**: `vehicle_id` (PK), `max_weight`, `max_volume`, `fleet_id` (FK), `status`, `license_plate_number` (Unique)
*   **分析**:
    *   **1NF**: 满足。
    *   **2NF**: 主键为单列，满足。
    *   **3NF**: 
        *   `license_plate_number` 是候选键，唯一标识车辆。
        *   所有非主属性（载重、容积、状态、所属车队）均直接依赖于 `vehicle_id`。
        *   虽然 `status` 有固定枚举值，但它是车辆当前的属性，不依赖于其他非主字段。
*   **结论**: 满足 **3NF**。

### 2.4 司机表 (drivers)
*   **结构**: `driver_id` (PK), `name`, `license_level`, `phone`, `fleet_id` (FK)
*   **分析**:
    *   **1NF**: 满足。
    *   **2NF**: 主键为单列，满足。
    *   **3NF**: 所有属性依赖于 `driver_id`。`fleet_id` 表示归属关系。不存在传递依赖。
*   **结论**: 满足 **3NF**。

### 2.5 主管表 (supervisors)
*   **结构**: `supervisor_id` (PK), `name`, `phone`, `fleet_id` (FK, Unique)
*   **分析**:
    *   **1NF**: 满足。
    *   **2NF**: 满足。
    *   **3NF**: `fleet_id` 具有唯一性约束，说明一个车队仅有一个主管，一个主管仅管理一个车队（1:1）。属性均依赖于主键。
*   **结论**: 满足 **3NF**。

### 2.6 运单表 (orders)
*   **结构**: `order_id` (PK), `weight`, `volume`, `destination`, `created_at`, `vehicle_id` (FK), `driver_id` (FK), `status`
*   **分析**:
    *   **1NF**: 满足。
    *   **2NF**: 满足。
    *   **3NF**:
        *   存在 `vehicle_id` 和 `driver_id` 两个外键。
        *   **潜在依赖讨论**: 如果业务逻辑规定“某辆车必须由特定司机驾驶”（即 `vehicle_id` -> `driver_id`），则存在传递依赖 (`order_id` -> `vehicle_id` -> `driver_id`)，这将违反 3NF。
        *   **实际场景分析**: 在物流系统中，司机和车辆通常是针对每次“运单”进行动态分配的（即多对多关系的实例化）。因此，`vehicle_id` 和 `driver_id` 在此表中表示“该次运单由谁驾驶哪辆车”，它们独立依赖于 `order_id`。
        *   `destination` 为地址字符串，`status` 为状态，均直接描述运单。
*   **结论**: 在司机与车辆动态分配的假设下，满足 **3NF**。

### 2.7 异常事件表 (exception_events)
*   **结构**: `event_id` (PK), `order_id` (FK), `exception_type`, `fine_amount`, `occurred_time`, `description`, `status`
*   **分析**:
    *   **1NF**: 满足。
    *   **2NF**: 满足。
    *   **3NF**:
        *   **潜在依赖**: `exception_type` 和 `fine_amount`。如果某种 `exception_type` 绝对对应固定的 `fine_amount`（例如：类型A罚款100元，类型B罚款200元，不可更改），则存在传递依赖 `event_id` -> `exception_type` -> `fine_amount`，此时应将罚款标准拆分为独立表。
        *   **当前设计**: `fine_amount` 被定义为一个可记录的数值字段。在实际业务中，即使类型相同，罚款金额可能因情节严重程度而异。因此，视 `fine_amount` 为该特定事件的属性而非类型的属性是合理的。
*   **结论**: 视为满足 **3NF**。

### 2.8 审计日志表 (history_log)
*   **结构**: `log_id` (PK), `table_name`, `change_id`, `operation_type`, `old_data`, `change_at`
*   **分析**:
    *   **1NF**: `old_data` 存储为 `NVARCHAR(MAX)`（通常为 JSON）。从数据库引擎角度看它是单个字符串，原子性满足。从语义内容看它包含结构化数据，但在日志归档场景下，通常不要求对其内容进行正则化拆分。
    *   **2NF/3NF**: 所有元数据（表名、操作类型、时间）都直接描述该次日志记录，依赖于 `log_id`。
*   **结论**: 满足 **3NF**。

## 3. 总体结论

经过对 `init_table.sql` 中所有表的分析，该数据库设计在通用的业务假设下（如司机车辆动态绑定、罚款金额各异），所有表均达到了 **第三范式 (3NF)** 的要求。表结构清晰，冗余度低，能够有效避免数据更新异常。
