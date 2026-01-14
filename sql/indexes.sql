-- 运单表：时间过滤 + 司机/车辆统计
CREATE INDEX IX_orders_created_at
ON orders(created_at);

CREATE INDEX IX_orders_driver_created_at
ON orders(driver_id, created_at);

CREATE INDEX IX_orders_vehicle_created_at
ON orders(vehicle_id, created_at);

-- 异常事件表：时间过滤 + 运单关联
CREATE INDEX IX_exception_events_occurred_time
ON exception_events(occurred_time);

CREATE INDEX IX_exception_events_order_id
ON exception_events(order_id);

-- 组织层级关联
CREATE INDEX IX_vehicles_fleet_id
ON vehicles(fleet_id);

CREATE INDEX IX_fleets_center_id
ON fleets(center_id);
