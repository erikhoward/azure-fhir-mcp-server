# Azure FHIR MCP Server - Usage Examples

This document provides practical examples of how to interact with the Azure FHIR MCP Server through chat interfaces like Claude Desktop. The server automatically maps natural language requests to FHIR API calls.

## 🩺 Patient Queries

### Basic Patient Search
**Chat Input:**
> "Find patients named Smith"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient",
  "search_params": {
    "name": "Smith"
  }
}
```

---

**Chat Input:**
> "Get 10 patients"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient", 
  "search_params": {
    "_count": 10
  }
}
```

---

**Chat Input:**
> "Show me female patients born after 1990"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient",
  "search_params": {
    "gender": "female",
    "birthdate": "gt1990-01-01"
  }
}
```

---

**Chat Input:**
> "Find patients in Boston with the last name Johnson"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient",
  "search_params": {
    "name": "Johnson",
    "address-city": "Boston"
  }
}
```

## 🧪 Observation Queries

### Lab Results and Vital Signs
**Chat Input:**
> "Show me recent blood pressure readings"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Observation",
  "search_params": {
    "code": "85354-9",
    "_sort": "-date",
    "_count": 10
  }
}
```

---

**Chat Input:**
> "Find height observations for patients"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Observation",
  "search_params": {
    "code": "8302-2",
    "_include": "Observation:subject"
  }
}
```

---

**Chat Input:**
> "Get lab results from the last month"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Observation",
  "search_params": {
    "category": "laboratory",
    "date": "gt2024-09-01"
  }
}
```

## 🏥 Clinical Data Queries

### Conditions and Diagnoses
**Chat Input:**
> "Find patients with diabetes"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Condition",
  "search_params": {
    "code": "44054006",
    "_include": "Condition:patient"
  }
}
```

---

**Chat Input:**
> "Show active conditions for patients"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Condition",
  "search_params": {
    "clinical-status": "active",
    "_include": "Condition:patient"
  }
}
```

### Medications
**Chat Input:**
> "Find patients taking insulin"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "MedicationRequest",
  "search_params": {
    "medication": "insulin",
    "status": "active",
    "_include": "MedicationRequest:patient"
  }
}
```

---

**Chat Input:**
> "Show recent prescriptions"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "MedicationRequest",
  "search_params": {
    "_sort": "-_lastUpdated",
    "_count": 20
  }
}
```

## 🔍 Advanced Queries

### Complex Searches with Multiple Criteria
**Chat Input:**
> "Find elderly patients with heart conditions in Massachusetts"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient",
  "search_params": {
    "birthdate": "lt1960-01-01",
    "address-state": "MA",
    "_has": "Condition:patient:code=56265001"
  }
}
```

---

**Chat Input:**
> "Show pregnancy-related observations with patient details"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Observation",
  "search_params": {
    "code": "77386006",
    "_include": "Observation:subject",
    "_sort": "-date"
  }
}
```

### Time-Based Queries
**Chat Input:**
> "Get all data updated today"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Patient",
  "search_params": {
    "_lastUpdated": "gt2025-10-09"
  }
}
```

---

**Chat Input:**
> "Find encounters from this week"

**Tool Called:** `search_fhir`
```json
{
  "resource_type": "Encounter",
  "search_params": {
    "date": "gt2025-10-07",
    "_include": "Encounter:patient"
  }
}
```

## 🔐 User Information (OAuth Only)

**Chat Input:**
> "Who am I logged in as?"

**Tool Called:** `get_user_info`
```json
{}
```
**Returns:** Current authenticated user's Azure AD information

## 📊 Resource Collection Examples

The server also supports direct resource access through URI patterns:

### Direct Resource Access
**Chat Input:**
> "Get patient with ID 12345"

**Resource URI:** `fhir://Patient/12345`

---

**Chat Input:**
> "Show all patients"

**Resource URI:** `fhir://Patient/{filter}` with empty filter

---

**Chat Input:**
> "Find patients with 'name=Smith&gender=male'"

**Resource URI:** `fhir://Patient/{filter}` with filter: `"name=Smith&gender=male"`

## 🎯 Pro Tips for Better Results

### Use Specific Medical Terms
❌ **Less Effective:** "Find sick people"
✅ **Better:** "Find patients with active conditions"

### Specify Time Ranges
❌ **Vague:** "Recent lab results"
✅ **Specific:** "Lab results from the last 30 days"

### Include Related Data
❌ **Basic:** "Find observations"
✅ **Enhanced:** "Find observations with patient details included"

### Use Proper FHIR Codes When Known
❌ **Generic:** "Blood pressure readings"
✅ **Precise:** "Observations with LOINC code 85354-9 (Blood pressure panel)"
