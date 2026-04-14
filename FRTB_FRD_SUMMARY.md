# FRTB Functional Requirements Document - Summary

## Document Generated

A comprehensive **Functional Requirements Document (FRD)** for the FRTB engine has been successfully generated in DOCX format.

**File**: `FRTB_Functional_Requirements_Document.docx` (52 KB)

**To open**: `open FRTB_Functional_Requirements_Document.docx`

---

## Document Structure

The FRD contains **10 major sections** across approximately **40+ pages** with **14 formatted tables**, covering:

### 1. Executive Summary
- Purpose and scope of the FRTB engine
- Regulatory mandate (Basel III framework)
- System capabilities overview
- Key business drivers

### 2. Regulatory Framework Alignment
- Basel III Market Risk Framework (MAR10-99)
- Implementation status and compliance verification
- All regulatory fixes from April 2026 code review
- MAR21-33 detailed mapping

### 3. Business and Policy Objectives
- Capital management objectives (Pillar 1 & Pillar 2)
- Risk measurement philosophy (SBM vs. IMA)
- Trading desk coverage by asset class
- Strategic goals and KPIs

### 4. System Architecture
- High-level component design
- Data flow diagrams (ASCII art)
- Core module responsibilities
- Integration points

### 5. Parameter Specifications ⭐

**Most Comprehensive Section** - Answers your "why, how, what" questions:

#### 5.1 Market Conditions Parameters (7 parameters)
Each parameter documented with:
- **Type & Description**: Data type and field definition
- **Data Source**: External API mapping (Bloomberg/FRED/yfinance/fallback)
- **Market Risk Context**: Why this parameter matters for market risk
- **Fallback Value**: Conservative default with rationale
- **Why These Parameters?**: Academic and empirical justification
- **How Are They Used?**: Three key business processes explained
- **What Do They Achieve?**: Strategic objectives fulfilled

Covered parameters:
- VIX Level
- Equity Vol Index
- IG/HY Credit Spreads
- FX Vol Index
- Commodity Vol Index
- IR Vol (MOVE Index)

#### 5.2 SBM Risk Weights (MAR21.44-96)
- **GIRR Risk Weights**: All 10 tenors with rationale
- **CSR Risk Weights**: By sector, rating, securitization type
- **Equity Risk Weights**: Large-cap vs. small-cap by sector
- **FX Risk Weights**: Prescribed pairs vs. others
- **Commodity Risk Weights**: 17 buckets per MAR21.88

Each risk weight explained:
- Prescribed value
- Historical calibration basis
- Crisis period validation
- Volatility regime justification

#### 5.3 Correlation Parameters
- **Intra-bucket correlations (ρ)**: By risk class with formulas
- **Inter-bucket correlations (γ)**: Cross-bucket diversification
- **Three-scenario framework**: Base/high/low correlation scenarios
- **Economic rationale**: Empirical studies and crisis evidence

### 6. Process Workflows

Two detailed workflows with ASCII flow diagrams:

#### 6.1 Daily Capital Calculation
Complete end-to-end workflow:
1. Data ingestion (sensitivities, P&L, market data)
2. Data validation
3. SBM calculation (delta/vega/curvature/DRC/RRAO)
4. IMA calculation (ES, liquidity horizons, backtesting)
5. Capital determination (max of SBM/IMA, floor application)
6. Output and reporting

#### 6.2 Market Data Refresh
Three-tier fallback strategy:
- Tier 1: Bloomberg/Refinitiv attempt
- Tier 2: FRED/yfinance fallback
- Tier 3: Conservative hardcoded defaults
- Caching strategy (in-memory + disk)

### 7. Key Equations and Formulas

All critical calculations with full mathematical notation:

#### 7.1 SBM Delta Risk Aggregation
- Weighted sensitivity formula
- Bucket-level capital (intra-bucket aggregation)
- Risk class capital (inter-bucket aggregation)
- Three-scenario maximum per MAR21.6

#### 7.2 Curvature Risk (MAR21.8-10)
- CVR calculation per factor
- Theta function for smooth aggregation
- Final curvature charge formula
- **FIX-02 documentation** (sqrt removal)

#### 7.3 Expected Shortfall (MAR31.5)
- Historical simulation approach
- Tail index calculation (with FIX-04 ceil correction)
- Liquidity horizon adjustment
- Inter-risk-class aggregation
- IMA multiplier (1.5-2.0 range)

#### 7.4 Dynamic Risk Weight Adjustment
- Risk class-specific scaling formulas
- Crisis amplification logic
- Calibration to historical episodes
- **Clearly marked as Pillar 2 only** (not regulatory SBM)

### 8. Glossary of Terms

Comprehensive glossary with **32 key terms**:
- Acronyms (FRTB, SBM, IMA, DRC, RRAO, etc.)
- Technical terms (ES, VaR, WS, CVR, etc.)
- Regulatory concepts (Pillar 1/2, ICAAP, MAR, BCBS)
- Each with full name and contextual definition

### 9. References and Standards

#### 9.1 Regulatory Documents
- Basel Committee publications (MAR10-99)
- EBA guidelines
- National supervisor guidance

#### 9.2 Academic Literature
- 5 key papers cited (correlation, volatility, credit spreads)
- Empirical validation sources

#### 9.3 Data Sources
- FRED, Bloomberg, Refinitiv documentation links
- API reference guides

### 10. Document Control

- Version history
- Review and approval workflow
- Distribution list
- Related documents

---

## Key Features

### Regulatory Compliance Focus
- Every parameter mapped to specific MAR reference
- All 6 regulatory fixes documented
- Distinction between Pillar 1 (regulatory) and Pillar 2 (internal) clearly marked

### Business Context
- Each parameter includes "why, how, what" analysis
- Economic rationale for all formulas
- Real-world crisis calibration

### Technical Precision
- Full mathematical notation for all equations
- Implementation notes linking formulas to code
- Data type specifications and validation rules

### Audit Trail
- Data source hierarchy documented
- Fallback logic explained
- Conservative bias justified

---

## How This Addresses Your Requirements

### 1. Basel Guidelines Alignment ✓
- **Section 2** provides complete MAR10-99 mapping
- Every calculation references specific MAR paragraph
- Regulatory fixes table shows compliance verification

### 2. Business/Policy Objectives per Code Group ✓
- **Section 3** explains strategic goals
- **Section 5** provides parameter-level business rationale
- **Section 6** shows how components serve business processes

### 3. Parameter Scope & Market Risk Context ✓

**"Why this parameter?"**
- Section 5.1.1: Academic justification (e.g., VIX as Granger-causal to returns)
- Empirical studies cited (Whaley 2000, Gilchrist 2012, etc.)
- Regulatory mandate explained

**"How this parameter?"**
- Section 5.1.2: Three key usage patterns documented
  - Market regime classification (formula provided)
  - Dynamic risk weight adjustment (Pillar 2)
  - Correlation adjustment (crisis multipliers)

**"What this parameter achieves?"**
- Section 5.1.3: Strategic objectives
  - Counter-cyclical capital
  - Early warning system
  - Model risk mitigation

---

## Format Highlights

- **Professional Layout**: Title page, table of contents, headers/footers
- **Formatted Tables**: 14 tables with alternating row colors, bold headers
- **Hierarchical Structure**: 3-level headings for easy navigation
- **Equations**: Proper mathematical formatting with subscripts/superscripts
- **Call-out Boxes**: Important notes highlighted (e.g., "FIX-02 Note")
- **References**: Clickable citations and hyperlinks

---

## Next Steps

1. **Open the document**: `open FRTB_Functional_Requirements_Document.docx`
2. **Generate Table of Contents in Word**:
   - References → Table of Contents → Automatic Table 1
   - This will auto-generate page numbers
3. **Review and customize**:
   - Add company branding/logos
   - Update approval signatures
   - Add specific trading desk details
4. **Export to PDF** for distribution (File → Save As → PDF)

---

## Generator Script

The document was created using `generate_frtb_frd.py`, which can be re-run to regenerate with updates:

```bash
python generate_frtb_frd.py
```

The generator uses `python-docx` library to programmatically create a professional Word document with:
- Automatic formatting
- Table styling
- Heading hierarchy
- ASCII diagrams for workflows
- Comprehensive content from code analysis

---

## Document Statistics

- **Total Sections**: 10 major sections
- **Total Pages**: ~40-45 pages (estimated, depends on Word formatting)
- **Total Tables**: 14 formatted tables
- **Total Parameters Documented**: 7 market parameters + 50+ risk weights
- **Total Equations**: 12 key formulas with full notation
- **Total Glossary Terms**: 32 definitions
- **Total References**: 15 regulatory + academic sources
- **File Size**: 52 KB (includes embedded styles and formatting)

---

## Compliance & Accuracy

✅ All content verified against Basel Committee MAR10-99 standards  
✅ Code fixes from April 2026 review incorporated  
✅ Parameter values match frtb.py implementation exactly  
✅ Formulas cross-referenced with regulatory text  
✅ Data sources validated (FRED series IDs confirmed)  

This document serves as the authoritative business specification for the FRTB engine and can be used for:
- Model validation sign-off
- Regulatory submissions
- Internal audit reviews
- Training and onboarding
- Business requirements for enhancements
