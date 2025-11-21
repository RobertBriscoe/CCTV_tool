-- ============================================================================
-- Migration 003 - Phase 2 (Requires DBA/Admin Privileges)
-- ============================================================================
-- This script must be run by a user with the following permissions:
--   - GRANT REFERENCES
--   - CREATE VIEW
--   - CREATE PROCEDURE
--
-- Run this as a database administrator or ask your DBA to execute it.
-- ============================================================================

USE FDOT_CCTV_System;
GO

PRINT '============================================================================';
PRINT 'Migration 003 - Phase 2: Foreign Keys, Views, and Stored Procedures';
PRINT '============================================================================';
PRINT '';

-- ============================================================================
-- 1. GRANT NECESSARY PERMISSIONS TO RTMCSNAP USER
-- ============================================================================

PRINT 'Granting permissions to RTMCSNAP user...';

-- Grant REFERENCES permission for foreign key creation
GRANT REFERENCES ON dbo.camera_groups TO RTMCSNAP;
GRANT REFERENCES ON dbo.camera_downtime_log TO RTMCSNAP;
GRANT REFERENCES ON dbo.camera_health_summary TO RTMCSNAP;
GRANT REFERENCES ON dbo.camera_locations TO RTMCSNAP;

-- Grant CREATE VIEW permission
GRANT CREATE VIEW TO RTMCSNAP;

-- Grant CREATE PROCEDURE permission
GRANT CREATE PROCEDURE TO RTMCSNAP;

PRINT '✓ Permissions granted';
GO

-- ============================================================================
-- 2. ADD FOREIGN KEY CONSTRAINT
-- ============================================================================

PRINT '';
PRINT 'Creating foreign key constraint...';

IF NOT EXISTS (SELECT * FROM sys.foreign_keys WHERE name = 'FK_camera_group_members_groups')
BEGIN
    ALTER TABLE dbo.camera_group_members
    ADD CONSTRAINT FK_camera_group_members_groups
    FOREIGN KEY (group_id) REFERENCES dbo.camera_groups(id) ON DELETE CASCADE;
    PRINT '✓ Foreign key constraint created';
END
ELSE
BEGIN
    PRINT '⚠ Foreign key constraint already exists';
END
GO

-- ============================================================================
-- 3. CREATE VIEWS
-- ============================================================================

PRINT '';
PRINT 'Creating views...';

-- View: Current Camera Status with Downtime
IF EXISTS (SELECT * FROM sys.views WHERE name = 'vw_camera_status_with_downtime')
    DROP VIEW vw_camera_status_with_downtime;
GO

CREATE VIEW vw_camera_status_with_downtime AS
SELECT
    chs.camera_name,
    chs.camera_ip,
    chs.current_status,
    chs.consecutive_failures,
    chs.last_check,
    chs.last_online,
    chs.avg_response_time_ms,
    chs.uptime_percentage,
    d.id as active_downtime_id,
    d.downtime_start,
    DATEDIFF(MINUTE, d.downtime_start, GETDATE()) as current_downtime_minutes,
    cl.latitude,
    cl.longitude,
    cl.county,
    cl.highway
FROM camera_health_summary chs
LEFT JOIN camera_downtime_log d ON chs.camera_name = d.camera_name
    AND d.downtime_end IS NULL
LEFT JOIN camera_locations cl ON chs.camera_name = cl.camera_name;
GO

PRINT '✓ Created vw_camera_status_with_downtime';
GO

-- View: Monthly SLA Compliance
IF EXISTS (SELECT * FROM sys.views WHERE name = 'vw_monthly_sla_compliance')
    DROP VIEW vw_monthly_sla_compliance;
GO

CREATE VIEW vw_monthly_sla_compliance AS
SELECT
    camera_name,
    YEAR(downtime_start) as year,
    MONTH(downtime_start) as month,
    COUNT(*) as downtime_incidents,
    SUM(ISNULL(duration_minutes, 0)) as total_downtime_minutes,
    AVG(ISNULL(duration_minutes, 0)) as avg_downtime_minutes,
    MAX(ISNULL(duration_minutes, 0)) as max_downtime_minutes,
    -- Calculate uptime percentage (assuming 43800 minutes per month)
    100.0 - (SUM(ISNULL(duration_minutes, 0)) * 100.0 / 43800) as uptime_percentage
FROM camera_downtime_log
WHERE downtime_end IS NOT NULL
GROUP BY camera_name, YEAR(downtime_start), MONTH(downtime_start);
GO

PRINT '✓ Created vw_monthly_sla_compliance';
GO

-- ============================================================================
-- 4. CREATE STORED PROCEDURES
-- ============================================================================

PRINT '';
PRINT 'Creating stored procedures...';

-- Procedure: Start Downtime Tracking
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_start_downtime')
    DROP PROCEDURE sp_start_downtime;
GO

CREATE PROCEDURE sp_start_downtime
    @camera_name NVARCHAR(100),
    @camera_ip NVARCHAR(50),
    @status_before NVARCHAR(20),
    @status_during NVARCHAR(20)
AS
BEGIN
    -- Check if there's already an open downtime record
    IF NOT EXISTS (SELECT 1 FROM camera_downtime_log
                   WHERE camera_name = @camera_name AND downtime_end IS NULL)
    BEGIN
        INSERT INTO camera_downtime_log (camera_name, camera_ip, downtime_start, status_before, status_during)
        VALUES (@camera_name, @camera_ip, GETDATE(), @status_before, @status_during);

        SELECT SCOPE_IDENTITY() as downtime_id;
    END
    ELSE
    BEGIN
        SELECT id as downtime_id FROM camera_downtime_log
        WHERE camera_name = @camera_name AND downtime_end IS NULL;
    END
END
GO

PRINT '✓ Created sp_start_downtime';
GO

-- Procedure: End Downtime Tracking
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_end_downtime')
    DROP PROCEDURE sp_end_downtime;
GO

CREATE PROCEDURE sp_end_downtime
    @camera_name NVARCHAR(100),
    @recovery_method NVARCHAR(50) = NULL,
    @mims_ticket_id NVARCHAR(50) = NULL,
    @notes NVARCHAR(1000) = NULL
AS
BEGIN
    UPDATE camera_downtime_log
    SET
        downtime_end = GETDATE(),
        duration_minutes = DATEDIFF(MINUTE, downtime_start, GETDATE()),
        recovery_method = ISNULL(@recovery_method, recovery_method),
        mims_ticket_id = ISNULL(@mims_ticket_id, mims_ticket_id),
        notes = ISNULL(@notes, notes),
        updated_at = GETDATE()
    WHERE camera_name = @camera_name
        AND downtime_end IS NULL;

    SELECT @@ROWCOUNT as rows_updated;
END
GO

PRINT '✓ Created sp_end_downtime';
GO

-- Procedure: Check Maintenance Window
IF EXISTS (SELECT * FROM sys.procedures WHERE name = 'sp_is_in_maintenance')
    DROP PROCEDURE sp_is_in_maintenance;
GO

CREATE PROCEDURE sp_is_in_maintenance
    @camera_name NVARCHAR(100),
    @check_time DATETIME = NULL
AS
BEGIN
    IF @check_time IS NULL
        SET @check_time = GETDATE();

    SELECT
        COUNT(*) as is_in_maintenance,
        MAX(id) as maintenance_id,
        MAX(description) as maintenance_description
    FROM maintenance_schedule
    WHERE camera_name = @camera_name
        AND status IN ('scheduled', 'in-progress')
        AND suppress_alerts = 1
        AND @check_time BETWEEN scheduled_start AND scheduled_end;
END
GO

PRINT '✓ Created sp_is_in_maintenance';
GO

-- ============================================================================
-- COMPLETION
-- ============================================================================

PRINT '';
PRINT '============================================================================';
PRINT '✓ Migration 003 - Phase 2 COMPLETED!';
PRINT '============================================================================';
PRINT '';
PRINT 'Created:';
PRINT '  ✓ Foreign key constraint: FK_camera_group_members_groups';
PRINT '  ✓ Views: 2';
PRINT '  ✓ Stored procedures: 3';
PRINT '';
PRINT 'Permissions granted to RTMCSNAP:';
PRINT '  ✓ REFERENCES on tables';
PRINT '  ✓ CREATE VIEW';
PRINT '  ✓ CREATE PROCEDURE';
PRINT '';
GO
