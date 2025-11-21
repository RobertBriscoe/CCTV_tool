-- ============================================================================
-- Phase 5: Advanced Alerting & Notifications System
-- Migration 004
-- ============================================================================

USE FDOT_CCTV_System;
GO

-- ============================================================================
-- Alert Rules Table
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'alert_rules')
BEGIN
    CREATE TABLE alert_rules (
        id INT IDENTITY(1,1) PRIMARY KEY,
        rule_name NVARCHAR(100) NOT NULL,
        rule_type NVARCHAR(50) NOT NULL, -- 'sla_violation', 'extended_downtime', 'health_degradation', 'recovery'
        description NVARCHAR(500),

        -- Conditions
        threshold_value DECIMAL(10,2), -- e.g., 95.0 for SLA, 30 for downtime minutes
        threshold_operator NVARCHAR(10), -- '<', '>', '<=', '>=', '=='
        evaluation_window_minutes INT DEFAULT 30, -- How long to evaluate condition

        -- Scope
        applies_to NVARCHAR(20) DEFAULT 'all', -- 'all', 'group', 'camera'
        camera_name NVARCHAR(100), -- Specific camera if applies_to = 'camera'
        group_id INT, -- Specific group if applies_to = 'group'

        -- Alert behavior
        severity NVARCHAR(20) DEFAULT 'warning', -- 'info', 'warning', 'error', 'critical'
        enabled BIT DEFAULT 1,
        suppress_during_maintenance BIT DEFAULT 1,
        rate_limit_minutes INT DEFAULT 60, -- Minimum time between repeat alerts

        -- Notification settings
        notification_channels NVARCHAR(200) DEFAULT 'email', -- Comma-separated: 'email', 'webhook', 'mims'
        email_recipients NVARCHAR(500), -- Comma-separated email addresses
        webhook_url NVARCHAR(500),

        -- Escalation
        escalation_enabled BIT DEFAULT 0,
        escalation_after_minutes INT DEFAULT 120,
        escalation_recipients NVARCHAR(500), -- Escalation email list

        -- Metadata
        created_by NVARCHAR(100),
        created_at DATETIME2 DEFAULT GETDATE(),
        updated_at DATETIME2 DEFAULT GETDATE(),

        CONSTRAINT FK_alert_rules_group FOREIGN KEY (group_id)
            REFERENCES camera_groups(id) ON DELETE SET NULL
    );

    CREATE INDEX IX_alert_rules_type ON alert_rules(rule_type);
    CREATE INDEX IX_alert_rules_enabled ON alert_rules(enabled);
    CREATE INDEX IX_alert_rules_camera ON alert_rules(camera_name);

    PRINT 'Created table: alert_rules';
END
GO

-- ============================================================================
-- Alert History Table
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'alert_history')
BEGIN
    CREATE TABLE alert_history (
        id INT IDENTITY(1,1) PRIMARY KEY,
        alert_rule_id INT NOT NULL,

        -- Alert details
        camera_name NVARCHAR(100) NOT NULL,
        alert_type NVARCHAR(50) NOT NULL,
        severity NVARCHAR(20) NOT NULL,
        message NVARCHAR(1000) NOT NULL,

        -- Trigger conditions
        trigger_value DECIMAL(10,2), -- Actual value that triggered alert
        threshold_value DECIMAL(10,2), -- Threshold that was crossed

        -- State
        status NVARCHAR(20) DEFAULT 'triggered', -- 'triggered', 'acknowledged', 'resolved', 'auto_resolved'
        triggered_at DATETIME2 DEFAULT GETDATE(),
        acknowledged_at DATETIME2,
        acknowledged_by NVARCHAR(100),
        resolved_at DATETIME2,
        resolved_by NVARCHAR(100),
        resolution_notes NVARCHAR(1000),

        -- Notification tracking
        notification_sent BIT DEFAULT 0,
        notification_sent_at DATETIME2,
        notification_channels NVARCHAR(200), -- Channels used for this alert
        notification_error NVARCHAR(500),

        -- Escalation tracking
        escalated BIT DEFAULT 0,
        escalated_at DATETIME2,
        escalation_level INT DEFAULT 0,

        -- Metadata
        metadata NVARCHAR(MAX), -- JSON for additional context

        CONSTRAINT FK_alert_history_rule FOREIGN KEY (alert_rule_id)
            REFERENCES alert_rules(id) ON DELETE CASCADE
    );

    CREATE INDEX IX_alert_history_camera ON alert_history(camera_name);
    CREATE INDEX IX_alert_history_triggered ON alert_history(triggered_at DESC);
    CREATE INDEX IX_alert_history_status ON alert_history(status);
    CREATE INDEX IX_alert_history_severity ON alert_history(severity);
    CREATE INDEX IX_alert_history_rule ON alert_history(alert_rule_id);

    PRINT 'Created table: alert_history';
END
GO

-- ============================================================================
-- Alert Subscriptions Table (Optional - for per-user subscriptions)
-- ============================================================================
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'alert_subscriptions')
BEGIN
    CREATE TABLE alert_subscriptions (
        id INT IDENTITY(1,1) PRIMARY KEY,
        user_email NVARCHAR(200) NOT NULL,
        user_name NVARCHAR(100),

        -- Subscription preferences
        subscribe_all BIT DEFAULT 0,
        alert_types NVARCHAR(200), -- Comma-separated alert types to receive
        severity_filter NVARCHAR(100) DEFAULT 'warning,error,critical', -- Min severity levels

        -- Scope
        camera_name NVARCHAR(100), -- Subscribe to specific camera
        group_id INT, -- Subscribe to group

        -- Delivery preferences
        delivery_method NVARCHAR(50) DEFAULT 'email', -- 'email', 'digest'
        digest_frequency NVARCHAR(20), -- 'daily', 'weekly' if digest enabled
        quiet_hours_start TIME, -- Don't send alerts during these hours
        quiet_hours_end TIME,

        -- Status
        active BIT DEFAULT 1,
        created_at DATETIME2 DEFAULT GETDATE(),
        updated_at DATETIME2 DEFAULT GETDATE(),

        CONSTRAINT FK_alert_subscriptions_group FOREIGN KEY (group_id)
            REFERENCES camera_groups(id) ON DELETE SET NULL
    );

    CREATE INDEX IX_alert_subscriptions_email ON alert_subscriptions(user_email);
    CREATE INDEX IX_alert_subscriptions_active ON alert_subscriptions(active);

    PRINT 'Created table: alert_subscriptions';
END
GO

-- ============================================================================
-- Alert Rate Limiting View
-- ============================================================================
IF OBJECT_ID('vw_recent_alerts_rate_limit', 'V') IS NOT NULL
    DROP VIEW vw_recent_alerts_rate_limit;
GO

CREATE VIEW vw_recent_alerts_rate_limit AS
SELECT
    ar.id as rule_id,
    ar.rule_name,
    ar.camera_name,
    ar.rate_limit_minutes,
    ah.camera_name as alert_camera,
    MAX(ah.triggered_at) as last_alert_time,
    DATEDIFF(MINUTE, MAX(ah.triggered_at), GETDATE()) as minutes_since_last_alert,
    CASE
        WHEN DATEDIFF(MINUTE, MAX(ah.triggered_at), GETDATE()) >= ar.rate_limit_minutes
        THEN 1
        ELSE 0
    END as can_trigger
FROM alert_rules ar
LEFT JOIN alert_history ah ON ar.id = ah.alert_rule_id
WHERE ar.enabled = 1
GROUP BY ar.id, ar.rule_name, ar.camera_name, ar.rate_limit_minutes, ah.camera_name;
GO

PRINT 'Created view: vw_recent_alerts_rate_limit';
GO

-- ============================================================================
-- Alert Summary View
-- ============================================================================
IF OBJECT_ID('vw_alert_summary', 'V') IS NOT NULL
    DROP VIEW vw_alert_summary;
GO

CREATE VIEW vw_alert_summary AS
SELECT
    ah.alert_rule_id,
    ar.rule_name,
    ah.alert_type,
    ah.severity,
    ah.camera_name,
    ah.status,
    COUNT(*) as alert_count,
    MAX(ah.triggered_at) as last_triggered,
    MIN(ah.triggered_at) as first_triggered,
    SUM(CASE WHEN ah.notification_sent = 1 THEN 1 ELSE 0 END) as notifications_sent,
    SUM(CASE WHEN ah.escalated = 1 THEN 1 ELSE 0 END) as escalations,
    AVG(CASE
        WHEN ah.resolved_at IS NOT NULL
        THEN DATEDIFF(MINUTE, ah.triggered_at, ah.resolved_at)
        ELSE NULL
    END) as avg_resolution_minutes
FROM alert_history ah
JOIN alert_rules ar ON ah.alert_rule_id = ar.id
WHERE ah.triggered_at >= DATEADD(DAY, -30, GETDATE())
GROUP BY ah.alert_rule_id, ar.rule_name, ah.alert_type, ah.severity, ah.camera_name, ah.status;
GO

PRINT 'Created view: vw_alert_summary';
GO

-- ============================================================================
-- Default Alert Rules (Examples)
-- ============================================================================

-- Rule 1: Critical SLA Violation
IF NOT EXISTS (SELECT * FROM alert_rules WHERE rule_name = 'Critical SLA Violation')
BEGIN
    INSERT INTO alert_rules (
        rule_name, rule_type, description,
        threshold_value, threshold_operator, evaluation_window_minutes,
        applies_to, severity, enabled, suppress_during_maintenance,
        rate_limit_minutes, notification_channels,
        created_by
    ) VALUES (
        'Critical SLA Violation',
        'sla_violation',
        'Alert when camera uptime falls below Critical SLA target (99.9%)',
        99.9, '<', 1440, -- 24 hour evaluation window
        'all', 'critical', 1, 1,
        120, 'email',
        'system'
    );
    PRINT 'Created default rule: Critical SLA Violation';
END
GO

-- Rule 2: Extended Downtime
IF NOT EXISTS (SELECT * FROM alert_rules WHERE rule_name = 'Extended Downtime (30 min)')
BEGIN
    INSERT INTO alert_rules (
        rule_name, rule_type, description,
        threshold_value, threshold_operator, evaluation_window_minutes,
        applies_to, severity, enabled, suppress_during_maintenance,
        rate_limit_minutes, notification_channels,
        created_by
    ) VALUES (
        'Extended Downtime (30 min)',
        'extended_downtime',
        'Alert when camera is down for more than 30 consecutive minutes',
        30, '>=', 30,
        'all', 'error', 1, 1,
        60, 'email',
        'system'
    );
    PRINT 'Created default rule: Extended Downtime (30 min)';
END
GO

-- Rule 3: Standard SLA Violation
IF NOT EXISTS (SELECT * FROM alert_rules WHERE rule_name = 'Standard SLA Violation')
BEGIN
    INSERT INTO alert_rules (
        rule_name, rule_type, description,
        threshold_value, threshold_operator, evaluation_window_minutes,
        applies_to, severity, enabled, suppress_during_maintenance,
        rate_limit_minutes, notification_channels,
        created_by
    ) VALUES (
        'Standard SLA Violation',
        'sla_violation',
        'Alert when camera uptime falls below Standard SLA target (95%)',
        95.0, '<', 1440, -- 24 hour evaluation window
        'all', 'warning', 1, 1,
        240, 'email', -- 4 hour rate limit
        'system'
    );
    PRINT 'Created default rule: Standard SLA Violation';
END
GO

-- Rule 4: Camera Recovery
IF NOT EXISTS (SELECT * FROM alert_rules WHERE rule_name = 'Camera Recovery Notification')
BEGIN
    INSERT INTO alert_rules (
        rule_name, rule_type, description,
        threshold_value, threshold_operator, evaluation_window_minutes,
        applies_to, severity, enabled, suppress_during_maintenance,
        rate_limit_minutes, notification_channels,
        created_by
    ) VALUES (
        'Camera Recovery Notification',
        'recovery',
        'Notify when a previously down camera comes back online',
        30, '>=', 5, -- Was down for at least 30 min, check recovery in 5 min window
        'all', 'info', 1, 0, -- Don't suppress during maintenance
        30, 'email',
        'system'
    );
    PRINT 'Created default rule: Camera Recovery Notification';
END
GO

PRINT '============================================================================';
PRINT 'Phase 5 Alerting System Migration Complete!';
PRINT '============================================================================';
PRINT 'Created Tables:';
PRINT '  - alert_rules (Alert rule definitions)';
PRINT '  - alert_history (Alert event log)';
PRINT '  - alert_subscriptions (User notification preferences)';
PRINT '';
PRINT 'Created Views:';
PRINT '  - vw_recent_alerts_rate_limit (Rate limiting helper)';
PRINT '  - vw_alert_summary (30-day alert statistics)';
PRINT '';
PRINT 'Created Default Rules:';
PRINT '  - Critical SLA Violation (99.9%)';
PRINT '  - Standard SLA Violation (95%)';
PRINT '  - Extended Downtime (30 min)';
PRINT '  - Camera Recovery Notification';
PRINT '============================================================================';
GO
