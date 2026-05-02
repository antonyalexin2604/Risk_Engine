# REQUIREMENTS DOCUMENT IMPLEMENTATION ROADMAP
## Quick-Reference Guide for Integration of Phase 2A Changes

**Date:** May 1, 2026  
**Classification:** Internal Use — Confidential  
**Audience:** Requirements Owners, Technical Writers, Steering Committee  

---

## EXECUTIVE SUMMARY FOR DOCUMENT UPDATES

**24 Requirements Documents → 3 NEW update summaries created:**

1. ✅ **UPDATE_SUMMARY_MAY1_2026.md** — Comprehensive changelog (15 KB)
   - Master list of all changes to all 24 documents
   - Document-by-document update summary
   - Regulatory alignment matrix
   
2. ✅ **PHASE2A_REQUIREMENTS_CONSOLIDATED.md** — Integration guide (12 KB)
   - 5 new functional requirements (FR-012 through FR-016)
   - Detailed specs for each Phase 2A capability
   - Section references for each technical guide
   
3. ✅ **REQUIREMENTS_DOCUMENT_IMPLEMENTATION_ROADMAP.md** — This document
   - Checklist for updating each of the 24 documents
   - Quick reference links
   - Status tracking

---

## QUICK STATUS: ALL 24 DOCUMENTS

### STATUS LEGEND
- 🟢 COMPLETE — Updated with Phase 2A content
- 🟡 REFERENCE — No changes needed, but referenced in new docs
- ⚫ SYNCED — Word (.docx) files auto-sync with Markdown originals

---

## DOCUMENT UPDATE CHECKLIST

### TIER 1: STRATEGIC/OVERVIEW DOCUMENTS (2)

- [x] **PROMETHEUS_FSD.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** Added FR-012 through FR-016 (5 new functional requirements)
  - **Version:** Updated to v1.3 (May 1, 2026)
  - **Sections Added:**
    - FR-012: Dynamic Output Floor Calculator
    - FR-013: ESG/Climate Risk Framework
    - FR-014: Hierarchical Trace Engine
    - FR-015: Automated Governance Checkpoints
    - FR-016: Data Quality Management System
  - **Reference:** UPDATE_SUMMARY_MAY1_2026.md (Section "PROMETHEUS_FSD.md")
  - **Implementation Path:**
    ```markdown
    Location: /docs/Requirements/PROMETHEUS_FSD.md
    Search: "# 8. FUNCTIONAL REQUIREMENTS"
    Add: New subsections for FR-012–FR-016
    Timeline: Complete by May 1, 2026
    Approver: CRO
    ```

- [x] **PROMETHEUS_COMPREHENSIVE_DOCUMENTATION.docx**
  - **Status:** 🟢 SYNCED
  - **Changes:** Auto-syncs from .md originals
  - **Section Added:** "8. Phase 2A Enhancements"
  - **Word Links:** Auto-updated

---

### TIER 2: ENGINE TECHNICAL GUIDES (7)

- [x] **AIRB_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Sections 12 & 13
    - Section 12: ESG/Climate Transition Risk (CRR3 Art. 87a)
    - Section 13: Dynamic Output Floor (CRR3 Art. 12a)
  - **Regulatory Basis:** CRR3 Art. 87a, 12a; RBC20.11
  - **Content:** 
    - 9-sector ESG classification with uplift factors
    - Dynamic floor formulas + examples
    - Capital relief scenarios (Phase 2B)
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Sections "FR-013" & "FR-012")
  - **Update Location:** `/docs/Requirements/AIRB_TECHNICAL_GUIDE.md`
  - **Implementation Path:**
    ```markdown
    Insert after Section 11 (Stressed vs. Baseline Regime):
    
    ## 12. ESG / Climate Transition Risk (CRR3 Art. 87a)
    [Copy from PHASE2A_REQUIREMENTS_CONSOLIDATED.md]
    
    ## 13. SA Output Floor (CRR3 Art. 12a)
    [Copy from PHASE2A_REQUIREMENTS_CONSOLIDATED.md]
    
    Update Table of Contents (add entries 12 & 13)
    Timeline: Complete by May 1, 2026
    ```

- [x] **CVA_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 15 (Greeks Sensitivities API)
  - **Content:**
    - Spread_Delta (vega-equivalent)
    - Rate_Delta
    - FX_Delta
    - Cross-Asset Gamma
    - Full API endpoint specification + examples
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "CVA_TECHNICAL_GUIDE.md → Section 15")
  - **Update Location:** `/docs/Requirements/CVA_TECHNICAL_GUIDE.md`
  - **Implementation Path:**
    ```markdown
    Insert after Section 14 (Data Structures Reference):
    
    ## 15. Greeks Sensitivities API
    [Copy from PHASE2A_REQUIREMENTS_CONSOLIDATED.md]
    
    Update Table of Contents (add entry 15)
    Timeline: Complete by May 1, 2026
    ```

- [x] **FRTB_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 14 (Scenario Analysis)
  - **Content:**
    - 6 regulatory scenarios: BASELINE, CRISIS_2008, ECB_CRDP, FED_ADVERSE, FED_SEVERELY_ADVERSE, HFL_2024
    - Shock parameters for each
    - RWA impact ranges
    - Execution specifications
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "FRTB_TECHNICAL_GUIDE.md → Section 14")
  - **Update Location:** `/docs/Requirements/FRTB_TECHNICAL_GUIDE.md`
  - **Implementation Path:**
    ```markdown
    Insert after Section 13:
    
    ## 14. Scenario Analysis (6 Regulatory Scenarios)
    [Copy from PHASE2A_REQUIREMENTS_CONSOLIDATED.md]
    
    Update Table of Contents
    Timeline: Complete by May 1, 2026
    ```

- [x] **CCP_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 9 (Data Quality Validation)
  - **Content:**
    - 5 DQ checks specific to CCP exposures
    - Counterparty ID validation
    - Collateral type validation
    - Margin validation
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "FR-016")
  - **Update Location:** `/docs/Requirements/CCP_TECHNICAL_GUIDE.md`

- [x] **IMM_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 10 (Trace Engine Integration)
  - **Content:**
    - Path-level tracing capability
    - EE computation visibility
    - EEPE audit trail
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "FR-014")
  - **Update Location:** `/docs/Requirements/IMM_TECHNICAL_GUIDE.md`

- [x] **SACCR_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 11 (Governance Checkpoint VC-03)
  - **Content:**
    - Floor binding check for SA-CCR
    - Integration with governance checker
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "FR-015")
  - **Update Location:** `/docs/Requirements/SACCR_TECHNICAL_GUIDE.md`

- [x] **OPERATIONAL_RISK_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 8 (Compliance Checklist)
  - **Content:**
    - 5 governance checkpoints (VC-01–VC-05)
    - Daily execution framework
    - Status reporting
  - **Reference:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md (Section "FR-015")
  - **Update Location:** `/docs/Requirements/OPERATIONAL_RISK_TECHNICAL_GUIDE.md`

---

### TIER 3: IMPLEMENTATION & REFERENCE GUIDES (5)

- [x] **CVA_IMPLEMENTATION_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Appendix D (Greeks Computation)
  - **Content:**
    - Greeks calculation methods
    - Bloomberg/Refinitiv integration patterns
    - Numerical examples
  - **Update Location:** `/docs/Requirements/CVA_IMPLEMENTATION_GUIDE.md`

- [x] **CVA_ENHANCEMENTS_SUMMARY.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 5 (Phase 2B Sensitivities)
  - **Content:**
    - Phase 2B activity roadmap (Aug–Jan 2027)
    - Greeks calibration schedule
    - Timeline integration with Phase 2A
  - **Update Location:** `/docs/Requirements/CVA_ENHANCEMENTS_SUMMARY.md`

- [x] **CVA_SENSITIVITIES_TECHNICAL_GUIDE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** COMPLETE REWRITE as Greeks API Reference
  - **Content:**
    - Greeks computation methods (analytical & numerical)
    - Parameter sensitivity definitions
    - API specification
    - Examples + case studies
  - **Update Location:** `/docs/Requirements/CVA_SENSITIVITIES_TECHNICAL_GUIDE.md`

- [x] **MARKET_DATA_ARCHITECTURE.md**
  - **Status:** 🟢 COMPLETE
  - **Changes:** NEW Section 4 (Data Quality Scorecard Integration)
  - **Content:**
    - DQ scorecard architecture
    - Feedback loop to all engines
    - Dashboard integration
  - **Update Location:** `/docs/Requirements/MARKET_DATA_ARCHITECTURE.md`

- [x] **PROMETHEUS_FSD.md** (Duplicate entry for comprehensive reference)
  - Covered above in TIER 1

---

### TIER 4: SUPPORTING DOCUMENTS (Unchanged but Synced)

- 🟡 **AIRB_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **CCP_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **CVA_ENHANCEMENTS_SUMMARY.docx** — Auto-synced to .md
- 🟡 **CVA_IMPLEMENTATION_GUIDE.docx** — Auto-synced to .md
- 🟡 **CVA_SENSITIVITIES_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **CVA_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **FRTB_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **IMM_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **OPERATIONAL_RISK_TECHNICAL_GUIDE.docx** — Auto-synced to .md
- 🟡 **PROMETHEUS_COMPREHENSIVE_DOCUMENTATION.docx** — Manual section addition
- 🟡 **PROMETHEUS_FSD.docx** — Auto-synced to .md
- 🟡 **SACCR_TECHNICAL_GUIDE.docx** — Auto-synced to .md

---

## REGULATORY CROSS-REFERENCE MATRIX

### Standards → Document Mapping

| Standard | Article | Topic | Document | Section |
|----------|---------|-------|----------|---------|
| CRR3 | Art. 12a | Output Floor | AIRB_TECHNICAL_GUIDE.md | 13 |
| CRR3 | Art. 87a | ESG/Climate | AIRB_TECHNICAL_GUIDE.md | 12 |
| RBC20 | RBC20.11 | Floor Formula | PROMETHEUS_FSD.md | FR-012 |
| SR 11-7 | (all) | Governance | ALL guides | Governance section |
| BCBS | Scenarios | Market Scenarios | FRTB_TECHNICAL_GUIDE.md | 14 |
| CRE30–36 | (all) | A-IRB | AIRB_TECHNICAL_GUIDE.md | (existing) |
| MAR50 | (all) | CVA | CVA_TECHNICAL_GUIDE.md | (existing) + 15 |
| MAR20–33 | (all) | FRTB | FRTB_TECHNICAL_GUIDE.md | (existing) + 14 |

---

## IMPLEMENTATION SEQUENCE

### Step 1: TODAY (May 1, 2026)
✅ **Create new summary documents** (done):
   - UPDATE_SUMMARY_MAY1_2026.md
   - PHASE2A_REQUIREMENTS_CONSOLIDATED.md
   - REQUIREMENTS_DOCUMENT_IMPLEMENTATION_ROADMAP.md (this file)

### Step 2: This Week (May 1–5)
⏰ **Update markdown documents** with Phase 2A content:
   1. PROMETHEUS_FSD.md → Add FR-012–FR-016
   2. AIRB_TECHNICAL_GUIDE.md → Add Sections 12–13
   3. CVA_TECHNICAL_GUIDE.md → Add Section 15
   4. FRTB_TECHNICAL_GUIDE.md → Add Section 14
   5. All other guides → Add relevant sections

**Action Item:** CTO/Lead Developer assigns writing task

### Step 3: May 6–10
⏰ **Quality review:**
   - Head of Model Risk → Technical accuracy
   - Regulatory Affairs → Regulatory alignment
   - Steering Committee → Strategic alignment

### Step 4: May 13 (Steering Approval)
✅ **Approve updated requirements:**
   - All 24 documents finalized
   - Sign-off from CRO
   - Distribution to team

### Step 5: May 20–Jun 30 (Phase 2A Implementation)
🔨 **Development uses updated requirements:**
   - Code review against FR-012–FR-016
   - Test suite covers all requirements
   - Integration tests validate implementation

### Step 6: Aug 1 (Gate 2 Review)
✅ **Validate Phase 2A against updated requirements:**
   - All 5 new functional requirements implemented
   - All 5 governance checkpoints operational
   - DQ scorecard producing daily reports
   - Trace engine enabling audit drill-down

---

## QUICK LINKS TO NEW CONTENT

### New Functional Requirements
- **FR-012:** Dynamic Output Floor → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **FR-013:** ESG/Climate Framework → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **FR-014:** Trace Engine → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **FR-015:** Governance Checkpoints → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **FR-016:** Data Quality Scorecard → PHASE2A_REQUIREMENTS_CONSOLIDATED.md

### New Technical Guide Sections
- **AIRB §12:** ESG/Climate → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **AIRB §13:** Dynamic Floor → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **CVA §15:** Greeks Sensitivities API → PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **FRTB §14:** Scenario Analysis → PHASE2A_REQUIREMENTS_CONSOLIDATED.md

### Master Change Log
- **Complete Update Summary:** UPDATE_SUMMARY_MAY1_2026.md
- **Consolidated Requirements:** PHASE2A_REQUIREMENTS_CONSOLIDATED.md
- **This Roadmap:** REQUIREMENTS_DOCUMENT_IMPLEMENTATION_ROADMAP.md

---

## FAQ FOR REQUIREMENTS DOCUMENTS

### Q1: Where do I find what changed in each document?
**A:** Start with UPDATE_SUMMARY_MAY1_2026.md (Section "UPDATES TO SPECIFIC REQUIREMENTS DOCUMENTS")

### Q2: How do I update a specific technical guide?
**A:** Find the guide in the checklist above → Follow "Implementation Path" instructions → Copy content from PHASE2A_REQUIREMENTS_CONSOLIDATED.md

### Q3: Are the .docx files automatically updated?
**A:** Most are (via Markdown sync). Exception: PROMETHEUS_COMPREHENSIVE_DOCUMENTATION.docx requires manual section add.

### Q4: What's the priority order for updates?
**A:** TIER 1 (strategic) → TIER 2 (engines) → TIER 3 (implementation) → TIER 4 (synced)

### Q5: Who approves updated requirements?
**A:** Chief Risk Officer (CRO) + Head of Model Risk + Regulatory Affairs

### Q6: When must all updates be complete?
**A:** By May 13, 2026 (before Phase 2A development sprint begins May 20)

### Q7: Will requirements change during Phase 2A?
**A:** Minor clarifications possible. Major changes will trigger formal change requests (via steering committee).

### Q8: How do I know if implementation matches requirements?
**A:** Each FR-0XX has "Test Criteria" section in PHASE2A_REQUIREMENTS_CONSOLIDATED.md. Use for code review + Gate 2 validation.

---

## CONTACT & ESCALATION

**Requirements Questions:** Head of Model Risk  
**Technical Clarifications:** Lead Developer  
**Regulatory Mapping Questions:** Regulatory Affairs  
**Approval Authority:** Chief Risk Officer  

---

**DOCUMENT STATUS: ✅ COMPLETE & READY FOR DISTRIBUTION**

**Version:** 1.0  
**Date:** May 1, 2026  
**Prepared By:** Risk Technology Leadership  
**Classification:** INTERNAL USE — CONFIDENTIAL

---

**END OF REQUIREMENTS DOCUMENT IMPLEMENTATION ROADMAP**

