-- ============================================================================
-- Remove CCTV-BAY-SR75@SR388 from FDOT_CCTV_System Database
-- ============================================================================
-- This camera is not part of FDOT District 3 maintenance
-- Run this script when database connectivity is restored
--
-- Database: FDOT_CCTV_System
-- Server: SG-8-Test-SQL.CHPFMS.D3ITS.local
-- ============================================================================

USE FDOT_CCTV_System;
GO

DECLARE @camera_name NVARCHAR(100) = 'CCTV-BAY-SR75@SR388';
DECLARE @total_deleted INT = 0;
DECLARE @rows INT;

PRINT 'Removing camera: ' + @camera_name;
PRINT '';

-- Delete from camera_health_log
DELETE FROM camera_health_log WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_health_log';

-- Delete from camera_downtime_log
DELETE FROM camera_downtime_log WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_downtime_log';

-- Delete from reboot_history
DELETE FROM reboot_history WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from reboot_history';

-- Delete from camera_group_members
DELETE FROM camera_group_members WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_group_members';

-- Delete from camera_notes
DELETE FROM camera_notes WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_notes';

-- Delete from maintenance_schedule
DELETE FROM maintenance_schedule WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from maintenance_schedule';

-- Delete from camera_locations
DELETE FROM camera_locations WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_locations';

-- Delete from camera_health_summary (LAST - this is the summary table)
DELETE FROM camera_health_summary WHERE camera_name = @camera_name;
SET @rows = @@ROWCOUNT;
SET @total_deleted = @total_deleted + @rows;
PRINT '  Deleted ' + CAST(@rows AS VARCHAR) + ' records from camera_health_summary';

PRINT '';
PRINT 'Successfully removed ' + @camera_name;
PRINT 'Total records deleted: ' + CAST(@total_deleted AS VARCHAR);
GO
