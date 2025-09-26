# CRM API Requirements for V2 Case Discovery

## Overview

CaseGuard V2 requires enhanced CRM API endpoints for efficient case discovery and synchronization. Current Proclaim REST API lacks bulk case enumeration capabilities, forcing reliance on static YAML configuration files.

## Critical Missing Endpoints

### 1. `GET /api/tenant/{tenant_id}/cases`

**Purpose**: Retrieve complete case inventory for historical backfill during tenant onboarding

**Required Parameters**:
- `tenant_id`: Law firm identifier (string)
- `include_closed`: Boolean to include closed cases (default: true)
- `date_range`: Optional filter for case opening dates (ISO 8601 format)
- `limit`: Maximum number of cases to return (default: 1000)
- `offset`: Pagination offset (default: 0)

**Required Response**:
```json
{
  "tenant_id": "fdm_solicitors",
  "total_cases": 2117,
  "returned_cases": 1000,
  "has_more": true,
  "cases": [
    {
      "case_ref": "FDM0001",
      "status": "active",
      "opened_date": "2020-01-15T10:30:00Z",
      "closed_date": null,
      "last_modified": "2024-09-26T14:22:15Z",
      "serialno": 12345,
      "case_type": "Personal Injury",
      "handler": "John Smith",
      "client_name": "Jane Doe"
    }
  ]
}
```

**Current Status**: ❌ Not Available
**Priority**: Critical - Required for tenant onboarding
**Workaround**: CSV fallback adapter using "FDM example Funded Cases.csv"

### 2. `GET /api/tenant/{tenant_id}/cases/active`

**Purpose**: Lightweight endpoint for daily synchronization, returning only currently active cases

**Required Parameters**:
- `tenant_id`: Law firm identifier
- `last_modified_after`: ISO timestamp for change detection (optional)
- `include_metadata`: Include case metadata for change detection (default: true)

**Required Response**:
```json
{
  "tenant_id": "fdm_solicitors",
  "active_cases_count": 1037,
  "last_sync_timestamp": "2024-09-26T14:22:15Z",
  "cases": [
    {
      "case_ref": "FDM0001",
      "status": "active",
      "last_modified": "2024-09-26T14:22:15Z",
      "serialno": 12346,
      "needs_processing": true
    }
  ]
}
```

**Current Status**: ❌ Not Available
**Priority**: High - Required for daily sync efficiency
**Workaround**: Simulate based on FDM CSV data (1037 active cases)

### 3. `GET /api/case/{case_ref}/metadata`

**Purpose**: High-watermark change detection using serial numbers for efficient synchronization

**Required Parameters**:
- `case_ref`: Individual case reference

**Required Response**:
```json
{
  "case_ref": "FDM0001",
  "serialno": 12346,
  "last_modified": "2024-09-26T14:22:15Z",
  "status": "active",
  "has_updates": true,
  "last_activity": "2024-09-26T14:20:00Z",
  "document_count": 15,
  "history_count": 23
}
```

**Current Status**: ❌ Not Available
**Priority**: Medium - Optimization for change detection
**Workaround**: Full case fetch when change detection needed

### 4. `GET /api/tenant/{tenant_id}/cases/changed`

**Purpose**: Bulk change detection for efficient daily synchronization

**Required Parameters**:
- `tenant_id`: Law firm identifier
- `since`: ISO timestamp to check changes after
- `change_types`: Array of change types to include (optional)

**Required Response**:
```json
{
  "tenant_id": "fdm_solicitors",
  "check_period": {
    "since": "2024-09-25T14:00:00Z",
    "until": "2024-09-26T14:00:00Z"
  },
  "changes_summary": {
    "new_cases": 3,
    "updated_cases": 15,
    "closed_cases": 2
  },
  "changed_cases": [
    {
      "case_ref": "FDM0001",
      "change_type": "updated",
      "serialno": 12346,
      "last_modified": "2024-09-26T14:22:15Z"
    }
  ]
}
```

**Current Status**: ❌ Not Available
**Priority**: High - Major efficiency improvement
**Workaround**: Compare full case lists (inefficient)

## Implementation Impact

### Without Enhanced Endpoints

**Current Limitations**:
- Static YAML case lists (config/cases.yaml)
- Manual case enumeration required
- No automated discovery of new cases
- Inefficient full-case comparison for sync
- No high-watermark change detection
- Cannot scale to thousands of cases

**Performance Issues**:
- Daily sync requires full case list comparison
- ~2117 API calls needed for FDM tenant sync
- High risk of API rate limiting
- Increased session timeout risk
- Poor scalability for large law firms

### With Enhanced Endpoints

**V2 Capabilities Enabled**:
- Automatic tenant onboarding (onboard_tenant flow)
- Efficient daily synchronization (sync_tenant_daily flow)
- High-watermark change detection
- Bulk case discovery and processing
- Scalable to 10,000+ cases per tenant
- 95% reduction in sync API calls

**Performance Improvements**:
- Tenant onboarding: Single API call vs thousands
- Daily sync: Change detection vs full comparison
- API efficiency: 95% fewer calls
- Session stability: Reduced timeout risk
- Scalability: Linear vs exponential growth

## Fallback Strategies

Until CRM API extensions are available, V2 implements multiple fallback adapters:

### 1. CSVFallbackAdapter

**Data Source**: "FDM example Funded Cases.csv"
**Capabilities**:
- 2117 total cases (1037 Active, 1080 Complete)
- Case status filtering
- Simulated case discovery
- Batch processing support

**Limitations**:
- Static data (no live updates)
- No change detection
- Manual CSV updates required

### 2. YAMLFallbackAdapter

**Data Source**: config/cases.yaml
**Capabilities**:
- Legacy compatibility
- Manual case list management
- Custom case grouping

**Limitations**:
- Manual maintenance required
- No automated discovery
- Poor scalability

### 3. ProclaimCRMAdapter (Future)

**Data Source**: Enhanced Proclaim API
**Capabilities**:
- Real-time case discovery
- Automated change detection
- High-watermark synchronization
- Bulk operations

**Status**: Awaiting API provider implementation

## Migration Path

### Phase 1: Fallback Implementation (Current)
- ✅ CSV adapter for FDM tenant (2117 cases)
- ✅ YAML adapter for legacy compatibility
- ✅ Simulation for testing and development

### Phase 2: Partial API Integration (Future)
- ⏳ Basic case enumeration endpoint
- ⏳ Simple change detection
- ⏳ Migration from static data sources

### Phase 3: Full API Integration (Future)
- ⏳ Complete endpoint suite
- ⏳ High-watermark synchronization
- ⏳ Production scalability (10,000+ cases)

## Request to API Provider

**Proclaim CRM Team**: Please prioritize implementation of bulk case enumeration endpoints for CaseGuard V2 integration. Current REST API lacks critical discovery capabilities needed for production deployment.

**Business Impact**:
- Blocks automated tenant onboarding
- Forces inefficient manual case management
- Limits scalability for enterprise law firms
- Increases API usage due to workarounds

**Technical Requirements**:
- Bulk case listing with pagination
- Change detection with serial numbers
- Tenant-based filtering and isolation
- Efficient daily synchronization support

**Timeline**: Required for CaseGuard V2 production release Q1 2025.