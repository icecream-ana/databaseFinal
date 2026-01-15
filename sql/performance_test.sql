/* ============================================================
   Part 5：性能对比
   ============================================================ */

------------------------------------------------------------
-- Perf Test：开启 IO/TIME 统计后执行核心查询
------------------------------------------------------------
SET STATISTICS IO ON;
SET STATISTICS TIME ON;

EXEC dbo.sp_fleet_monthly_report @fleet_id=1, @year=2026, @month=1;
EXEC dbo.sp_driver_performance @driver_id=1, @start='2026-01-01', @end='2026-02-01';

SET STATISTICS IO OFF;
SET STATISTICS TIME OFF;
GO


/* ============================================================
   Part 6：检查索引是否创建成功
   ============================================================ */

------------------------------------------------------------
-- Check 1：列出项目相关表上的 IX_ 开头索引
------------------------------------------------------------
SELECT
    OBJECT_NAME(i.object_id) AS table_name,
    i.name AS index_name,
    i.type_desc AS index_type
FROM sys.indexes i
WHERE i.name LIKE 'IX_%'
  AND OBJECT_NAME(i.object_id) IN ('orders','vehicles','exception_events','fleets')
ORDER BY table_name, index_name;
GO


------------------------------------------------------------
-- Check 2：检查索引是否被使用（user_seeks/scans/lookup）
-- 说明：
--   - user_seeks > 0 通常说明索引被“按条件查找”使用
--   - user_scans 说明可能在扫索引或扫表
------------------------------------------------------------
SELECT
    OBJECT_NAME(s.object_id) AS table_name,
    i.name AS index_name,
    s.user_seeks,
    s.user_scans,
    s.user_lookups
FROM sys.dm_db_index_usage_stats s
JOIN sys.indexes i
    ON i.object_id = s.object_id AND i.index_id = s.index_id
WHERE s.database_id = DB_ID()
  AND OBJECT_NAME(s.object_id) IN ('orders','vehicles','exception_events','fleets')
ORDER BY table_name, index_name;
GO