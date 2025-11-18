-- CCTV Camera Health Monitoring Tables
-- Migration: 001 - Camera Health Dashboard
-- Created: 2025-11-17

-- =====================================================
-- Table: camera_health_log
-- Purpose: Track health check results for all cameras
-- =====================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_health_log')
BEGIN
    CREATE TABLE camera_health_log (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL,
        camera_ip NVARCHAR(50) NOT NULL,
        check_timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
        status NVARCHAR(20) NOT NULL, -- 'online', 'offline', 'degraded', 'unknown'
        response_time_ms INT NULL,
        ping_success BIT NOT NULL DEFAULT 0,
        snapshot_success BIT NOT NULL DEFAULT 0,
        error_message NVARCHAR(500) NULL,
        check_type NVARCHAR(20) NOT NULL DEFAULT 'auto', -- 'auto' or 'manual'
        INDEX idx_camera_name (camera_name),
        INDEX idx_camera_ip (camera_ip),
        INDEX idx_check_timestamp (check_timestamp DESC),
        INDEX idx_status (status)
    );
    PRINT 'Created table: camera_health_log';
END
ELSE
BEGIN
    PRINT 'Table camera_health_log already exists';
END
GO

-- =====================================================
-- Table: camera_health_summary
-- Purpose: Current health status for each camera (for quick lookups)
-- =====================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'camera_health_summary')
BEGIN
    CREATE TABLE camera_health_summary (
        camera_name NVARCHAR(100) PRIMARY KEY,
        camera_ip NVARCHAR(50) NOT NULL,
        current_status NVARCHAR(20) NOT NULL, -- 'online', 'offline', 'degraded', 'unknown'
        last_check DATETIME2 NOT NULL,
        last_online DATETIME2 NULL,
        last_offline DATETIME2 NULL,
        consecutive_failures INT NOT NULL DEFAULT 0,
        total_checks INT NOT NULL DEFAULT 0,
        successful_checks INT NOT NULL DEFAULT 0,
        avg_response_time_ms INT NULL,
        uptime_percentage DECIMAL(5,2) NULL,
        updated_at DATETIME2 NOT NULL DEFAULT GETDATE(),
        INDEX idx_status (current_status),
        INDEX idx_last_check (last_check DESC)
    );
    PRINT 'Created table: camera_health_summary';
END
ELSE
BEGIN
    PRINT 'Table camera_health_summary already exists';
END
GO

-- =====================================================
-- Table: reboot_history
-- Purpose: Track all camera reboot operations
-- =====================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'reboot_history')
BEGIN
    CREATE TABLE reboot_history (
        id INT IDENTITY(1,1) PRIMARY KEY,
        camera_name NVARCHAR(100) NOT NULL,
        camera_ip NVARCHAR(50) NOT NULL,
        reboot_timestamp DATETIME2 NOT NULL DEFAULT GETDATE(),
        operator NVARCHAR(100) NOT NULL,
        reason NVARCHAR(500) NOT NULL,
        outcome NVARCHAR(20) NOT NULL, -- 'success', 'failure'
        mims_ticket_id INT NULL,
        reboot_type NVARCHAR(20) NOT NULL DEFAULT 'manual', -- 'manual', 'scheduled', 'auto'
        error_message NVARCHAR(500) NULL,
        INDEX idx_camera_name (camera_name),
        INDEX idx_reboot_timestamp (reboot_timestamp DESC),
        INDEX idx_outcome (outcome)
    );
    PRINT 'Created table: reboot_history';
END
ELSE
BEGIN
    PRINT 'Table reboot_history already exists';
END
GO

-- =====================================================
-- Initial data population
-- =====================================================
PRINT 'Migration 001 completed successfully';
PRINT 'Tables created: camera_health_log, camera_health_summary, reboot_history';
GO
