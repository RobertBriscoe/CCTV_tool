# FreeTDS Cursor State Issues - Analysis

## Current Problems

### 1. High Error Rate
- **4,580 cursor state errors** logged today alone
- Error: `('24000', '[24000] [FreeTDS][SQL Server]Invalid cursor state (0)')`
- Affects multiple operations throughout the application

### 2. Affected Components
- **Alert Statistics API** - Returns HTTP 500 errors
- **Alert Engine** - Maintenance window and rate limiting checks fail
- **Various API endpoints** - Intermittent failures under concurrent load

### 3. Root Causes

#### Multi-Threading Issues
FreeTDS has known issues with cursor management in multi-threaded environments:
- Alert engine runs in background thread
- Flask handles concurrent web requests
- Health monitor runs periodic checks
- All share database connections → cursor state conflicts

#### Cursor Management Limitations
FreeTDS cursor implementation:
- Doesn't properly handle multiple active cursors on same connection
- Cursor state gets corrupted when:
  - Multiple queries execute concurrently
  - Cursors not properly closed before new queries
  - Connection used by multiple threads

#### Specific Problem Patterns
```python
# Pattern 1: Nested cursor usage (fails with FreeTDS)
cursor1 = conn.cursor()
cursor1.execute("SELECT ...")
for row in cursor1:
    cursor2 = conn.cursor()  # ← Cursor state error!
    cursor2.execute("SELECT ...")
    
# Pattern 2: Thread-local connection (fails with FreeTDS)
# Thread A creates cursor
# Thread B uses same connection
# → Cursor state corruption
```

## Current Workarounds in Place

### Temporarily Disabled Features
In `alert_engine.py`:
- Maintenance window suppression (lines 219-222, 275-278)
- Rate limiting checks (lines 224-227, 280-283, 332-335)

**Impact**: Alerts sent during maintenance, potential duplicate alerts

### Error Handling
- Try/except blocks catch cursor errors
- Functions return default values on error
- Allows system to continue but degrades functionality

## Proposed Solution

### Migrate to Microsoft ODBC Driver 18
**Benefits**:
- Native SQL Server driver from Microsoft
- Excellent multi-threading support
- Proper cursor state management
- Better performance and reliability
- Active maintenance and support

### Add Connection Pooling (SQLAlchemy)
**Benefits**:
- Manage connection lifecycle properly
- Thread-safe connection distribution
- Automatic connection recycling
- Query optimization layer
- Connection health checks

### Expected Improvements
- ✓ Eliminate 4,580+ daily cursor errors
- ✓ Re-enable all alert engine features
- ✓ Fix alert statistics API endpoint
- ✓ Improve overall system stability
- ✓ Better concurrent request handling
- ✓ Foundation for future scaling

## Technical Details

### Current Configuration
```
Driver: FreeTDS v1.4.23
ODBC Manager: unixODBC 2.3.7
TDS Version: 7.4
Connection String: DRIVER={FreeTDS};SERVER=...;DATABASE=...
```

### Target Configuration
```
Driver: Microsoft ODBC Driver 18 for SQL Server
ODBC Manager: unixODBC 2.3.7
Connection Pooling: SQLAlchemy
Connection String: DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=...
```

## Migration Plan

1. Install Microsoft ODBC Driver 18
2. Create SQLAlchemy connection pool layer
3. Update db_manager.py to use new driver
4. Update alert_engine.py to use new driver
5. Re-enable disabled features
6. Test all database operations
7. Deploy to production

**Estimated Time**: 2-4 hours
**Risk Level**: Low (can rollback to FreeTDS if issues)
**Downtime Required**: ~5 minutes for service restart

---
**Document Created**: 2025-11-21
**Status**: Ready for implementation
