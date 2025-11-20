-- ============================================================================
-- Migration 003: Advanced Features (Groups, Downtime, Maintenance, Map)
-- ============================================================================
-- Date: 2025-11-20
-- Description: Add support for camera groups, downtime tracking, maintenance
--              scheduling, and map view features

USE FDOT_CCTV_System;
GO

-- ============================================================================
-- 1. CAMERA GROUPS
-- ============================================================================

-- Camera Groups Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_groups')
BEGIN
    CREATE TABLE camera_groups (
        id INT IDENTITY(1,1) PRIMARY KEY,
        group_name NVARCHAR(100) NOT NULL UNIQUE,
        group_type NVARCHAR(50) NOT NULL,  -- 'highway', 'county', 'custom'
        description NVARCHAR(500),
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX idx_group_type ON camera_groups(group_type);
    PRINT '✓ Created camera_groups table';
END
ELSE
BEGIN
    PRINT '⚠ camera_groups table already exists';
END
GO

-- Camera Group Membership Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_group_members')
BEGIN
    CREATE TABLE camera_group_members (
        id INT IDENTITY(1,1) PRIMARY KEY,
        group_id INT NOT NULL,
        camera_name NVARCHAR(100) NOT NULL,
        added_at DATETIME DEFAULT GETDATE(),
        FOREIGN KEY (group_id) REFERENCES camera_groups(id) ON DELETE CASCADE
    );

    CREATE INDEX idx_group_id ON camera_group_members(group_id);
    CREATE INDEX idx_camera_name ON camera_group_members(camera_name);
    CREATE UNIQUE INDEX idx_unique_membership ON camera_group_members(group_id, camera_name);
    PRINT '✓ Created camera_group_members table';
END
ELSE
BEGIN
    PRINT '⚠ camera_group_members table already exists';
END
GO

-- ============================================================================
-- 2. DOWNTIME TRACKING & SLA
-- ============================================================================

-- Camera Downtime Log Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_downtime_log')
BEGIN
    CREATE TABLE camera_downtime_log (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL,
        camera_ip NVARCHAR(50),
        downtime_start DATETIME NOT NULL,
        downtime_end DATETIME NULL,
        duration_minutes INT NULL,
        status_before NVARCHAR(20),  -- 'online', 'degraded'
        status_during NVARCHAR(20),  -- 'offline', 'degraded'
        recovery_method NVARCHAR(50), -- 'auto', 'manual', 'self-recovery'
        mims_ticket_id NVARCHAR(50),
        notes NVARCHAR(1000),
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX idx_downtime_camera ON camera_downtime_log(camera_name);
    CREATE INDEX idx_downtime_start ON camera_downtime_log(downtime_start);
    CREATE INDEX idx_downtime_end ON camera_downtime_log(downtime_end);
    CREATE INDEX idx_downtime_duration ON camera_downtime_log(duration_minutes);
    PRINT '✓ Created camera_downtime_log table';
END
ELSE
BEGIN
    PRINT '⚠ camera_downtime_log table already exists';
END
GO

-- SLA Targets Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'sla_targets')
BEGIN
    CREATE TABLE sla_targets (
        id INT IDENTITY(1,1) PRIMARY KEY,
        target_name NVARCHAR(100) NOT NULL UNIQUE,
        uptime_percentage DECIMAL(5,2) NOT NULL,  -- e.g., 95.00 for 95%
        max_downtime_minutes_monthly INT,
        description NVARCHAR(500),
        active BIT DEFAULT 1,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    PRINT '✓ Created sla_targets table';

    -- Insert default SLA targets
    INSERT INTO sla_targets (target_name, uptime_percentage, max_downtime_minutes_monthly, description)
    VALUES
        ('Standard', 95.00, 2160, 'Standard SLA - 95% uptime (2160 min downtime/month allowed)'),
        ('Premium', 99.00, 432, 'Premium SLA - 99% uptime (432 min downtime/month allowed)'),
        ('Critical', 99.90, 43, 'Critical SLA - 99.9% uptime (43 min downtime/month allowed)');

    PRINT '✓ Inserted default SLA targets';
END
ELSE
BEGIN
    PRINT '⚠ sla_targets table already exists';
END
GO

-- ============================================================================
-- 3. MAINTENANCE SCHEDULING
-- ============================================================================

-- Maintenance Schedule Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'maintenance_schedule')
BEGIN
    CREATE TABLE maintenance_schedule (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL,
        camera_ip NVARCHAR(50),
        maintenance_type NVARCHAR(50) NOT NULL, -- 'planned', 'emergency', 'vendor'
        scheduled_start DATETIME NOT NULL,
        scheduled_end DATETIME NOT NULL,
        actual_start DATETIME NULL,
        actual_end DATETIME NULL,
        status NVARCHAR(20) DEFAULT 'scheduled', -- 'scheduled', 'in-progress', 'completed', 'cancelled'
        suppress_alerts BIT DEFAULT 1,
        description NVARCHAR(1000),
        technician NVARCHAR(100),
        vendor NVARCHAR(100),
        mims_ticket_id NVARCHAR(50),
        notes NVARCHAR(2000),
        created_by NVARCHAR(100),
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX idx_maint_camera ON maintenance_schedule(camera_name);
    CREATE INDEX idx_maint_scheduled_start ON maintenance_schedule(scheduled_start);
    CREATE INDEX idx_maint_scheduled_end ON maintenance_schedule(scheduled_end);
    CREATE INDEX idx_maint_status ON maintenance_schedule(status);
    PRINT '✓ Created maintenance_schedule table';
END
ELSE
BEGIN
    PRINT '⚠ maintenance_schedule table already exists';
END
GO

-- ============================================================================
-- 4. CAMERA LOCATIONS (for Map View)
-- ============================================================================

-- Camera Locations Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_locations')
BEGIN
    CREATE TABLE camera_locations (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL UNIQUE,
        latitude DECIMAL(10, 7) NULL,
        longitude DECIMAL(10, 7) NULL,
        address NVARCHAR(500),
        county NVARCHAR(50),
        highway NVARCHAR(50),
        milepost DECIMAL(6, 2),
        direction NVARCHAR(10), -- 'NB', 'SB', 'EB', 'WB', 'M' (median)
        location_source NVARCHAR(50), -- 'manual', 'gps', 'derived', 'estimated'
        accuracy_meters INT,
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE()
    );

    CREATE INDEX idx_location_camera ON camera_locations(camera_name);
    CREATE INDEX idx_location_coords ON camera_locations(latitude, longitude);
    CREATE INDEX idx_location_county ON camera_locations(county);
    CREATE INDEX idx_location_highway ON camera_locations(highway);
    PRINT '✓ Created camera_locations table';
END
ELSE
BEGIN
    PRINT '⚠ camera_locations table already exists';
END
GO

-- ============================================================================
-- 5. CAMERA NOTES/COMMENTS
-- ============================================================================

-- Camera Notes Table
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_notes')
BEGIN
    CREATE TABLE camera_notes (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL,
        note_type NVARCHAR(50), -- 'issue', 'maintenance', 'info', 'warning'
        note_text NVARCHAR(2000) NOT NULL,
        is_active BIT DEFAULT 1,
        show_on_dashboard BIT DEFAULT 1,
        priority INT DEFAULT 0, -- 0=info, 1=low, 2=medium, 3=high
        created_by NVARCHAR(100),
        created_at DATETIME DEFAULT GETDATE(),
        updated_at DATETIME DEFAULT GETDATE(),
        expires_at DATETIME NULL
    );

    CREATE INDEX idx_notes_camera ON camera_notes(camera_name);
    CREATE INDEX idx_notes_active ON camera_notes(is_active);
    CREATE INDEX idx_notes_priority ON camera_notes(priority DESC);
    PRINT '✓ Created camera_notes table';
END
ELSE
BEGIN
    PRINT '⚠ camera_notes table already exists';
END
GO

-- ============================================================================
-- 6. VIEWS FOR REPORTING
-- ============================================================================

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
    chs.last_check_time,
    chs.last_online_time,
    chs.response_time_ms,
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

PRINT '✓ Created vw_camera_status_with_downtime view';
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

PRINT '✓ Created vw_monthly_sla_compliance view';
GO

-- ============================================================================
-- 7. STORED PROCEDURES
-- ============================================================================

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

PRINT '✓ Created sp_start_downtime procedure';
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

PRINT '✓ Created sp_end_downtime procedure';
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

PRINT '✓ Created sp_is_in_maintenance procedure';
GO

PRINT '';
PRINT '============================================================================';
PRINT '✓ Migration 003 completed successfully!';
PRINT '============================================================================';
PRINT '';
PRINT 'New tables created:';
PRINT '  - camera_groups (camera grouping by highway/county/custom)';
PRINT '  - camera_group_members (group membership)';
PRINT '  - camera_downtime_log (downtime tracking for SLA)';
PRINT '  - sla_targets (SLA target definitions)';
PRINT '  - maintenance_schedule (maintenance window tracking)';
PRINT '  - camera_locations (GPS coordinates for map view)';
PRINT '  - camera_notes (operator notes and comments)';
PRINT '';
PRINT 'New views created:';
PRINT '  - vw_camera_status_with_downtime';
PRINT '  - vw_monthly_sla_compliance';
PRINT '';
PRINT 'New procedures created:';
PRINT '  - sp_start_downtime';
PRINT '  - sp_end_downtime';
PRINT '  - sp_is_in_maintenance';
PRINT '';
GO
