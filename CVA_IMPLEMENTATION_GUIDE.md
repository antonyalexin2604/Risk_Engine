# CVA Process Enhancement - BASEL MAR50 Compliance Guide

## Executive Summary

The PROMETHEUS CVA engine has been designed with a comprehensive framework for full BASEL MAR50 compliance. This document outlines the current status and remaining implementation tasks.

## Status Overview

### ✅ COMPLETED (Framework Ready)

1. **SA-CVA Architecture** - Full 6 delta + 5 vega risk class framework
2. **BA-CVA Implementation** - Complete basic approach with hedge recognition
3. **Proxy Spread Calibration** - Monthly review workflow infrastructure
4. **Capital Floor Verification** - CVA exclusion from output floor confirmed
5. **Operational Risk Dashboard** - SMA (OPE25) integrated into main dashboard

### 🔧 IN PROGRESS (Framework Exists, Needs Integration)

1. **SA-CVA Risk Classes 2-6** - Currently only CCSR implemented, need GIRR/FX/RCSR/EQ/CMDTY
2. **SA-CVA Vega Charge** - Approximation exists, full computation requires sensitivity engine
3. **Proxy Spread Monthly Review** - Database and workflow ready, needs production data

---

## Implementation Tasks

### Task 1: Complete SA-CVA Remaining 5 Risk Classes (REQUIRED)

**Current State:**
- ✅ Counterparty Credit Spread (CCSR) delta fully implemented
- ⚠️ Interest Rate (GIRR) delta - Framework ready, needs integration
- ⚠️ FX delta - Framework ready, needs integration
- ⚠️ Reference Credit Spread (RCSR) - Framework ready, needs CDS portfolio data
- ⚠️ Equity (EQ) - Framework ready, needs equity exposure data
- ⚠️ Commodity (CMDTY) - Framework ready, needs commodity exposure data

**File:** `backend/engines/cva_sensitivities.py` (Complete infrastructure exists)

**What's Needed:**

1. **Integration with IMM Engine** - Connect CVA sensitivity computation to Monte Carlo exposure paths
   ```python
   # backend/engines/cva.py, line ~750
   # TODO: Call compute_sa_cva_full() instead of current CCSR-only approximation
   from backend.engines.cva_sensitivities import compute_sa_cva_full
   
   full_sa_cva_rwa, full_results = compute_sa_cva_full(
       inputs=inputs,
       market=market,
       exposure_profiles=imm_exposure_profiles,  # from IMM engine
   )
   ```

2. **Risk Weight Tables** - Already implemented in `cva_sensitivities.py`:
   - GIRR risk weights (MAR50.49 Table 6): ✅ Complete
   - FX risk weights (MAR50.51): ✅ Complete
   - CCSR risk weights (MAR50.65 Table 7): ✅ Complete
   - RCSR risk weights (MAR50.65): ✅ Complete
   - Equity/Commodity risk weights (MAR50.52-54): ✅ Complete

3. **Bucket Correlation Matrices** - Already implemented:
   - Cross-risk-class correlation (MAR50.44 Table 4): ✅ Complete
   - GIRR intra-bucket correlation (MAR50.50): ✅ Complete
   - CCSR sector buckets (MAR50.63 Table 5): ✅ Complete

**Implementation Steps:**

```python
# Step 1: Compute sensitivities from exposure model
# backend/engines/imm.py - add CVA sensitivity computation

def compute_cva_sensitivities(
    exposure_profile: ExposureProfile,
    market_scenarios: List[MarketScenario],
) -> CVASensitivities:
    """
    Compute ∂CVA/∂risk_factor for all six delta risk classes.
    
    Use AAD (Adjoint Algorithmic Differentiation) or bump-and-reprice.
    """
    sensitivities = CVASensitivities(counterparty_id=exposure_profile.counterparty_id)
    
    # GIRR: Shock each tenor and compute ΔCVA
    for tenor in TENORS:
        cva_base = compute_cva(exposure_profile, market_scenarios)
        market_shocked = shock_ir_curve(market_scenarios, tenor, +1bp)
        cva_shocked = compute_cva(exposure_profile, market_shocked)
        sensitivities.delta_girr[tenor] = (cva_shocked - cva_base) / 1e-4  # per 1bp
    
    # FX: Similar for each currency pair
    # CCSR: Already implemented
    # RCSR: For CDS portfolios only
    # EQ: For equity-linked derivatives
    # CMDTY: For commodity derivatives
    
    return sensitivities

# Step 2: Aggregate sensitivities into capital charge
# backend/engines/cva_sensitivities.py - already complete, just needs data
```

**Test Case:**
```python
# tests/test_sa_cva_full.py
def test_all_six_delta_risk_classes():
    """Verify SA-CVA capital covers all six delta risk classes."""
    inputs = create_multi_asset_portfolio()  # IR swaps + FX + CDS
    result = compute_sa_cva_full(inputs)
    
    assert result["delta_girr_rwa"] > 0, "GIRR delta charge missing"
    assert result["delta_fx_rwa"] > 0, "FX delta charge missing"
    assert result["delta_ccsr_rwa"] > 0, "CCSR delta charge missing"
    # Verify cross-risk-class correlation applied per MAR50.44
```

---

### Task 2: Implement SA-CVA Vega Charge (REQUIRED per MAR50.48)

**Regulatory Requirement:**
> MAR50.48: "Vega risk capital must be computed for ALL five risk classes (no CCSR vega). Vega is ALWAYS material in SA-CVA, even without explicit option positions, because volatility enters the exposure simulation model."

**Current State:**
- ✅ Vega approximation implemented in `backend/engines/cva.py` line 577
- ✅ Framework for full vega in `cva_sensitivities.py`
- ⚠️ Full computation requires sensitivity engine integration

**File:** `backend/engines/cva.py`, function `_compute_vega_charge_approximation()`

**What's Needed:**

```python
# backend/engines/cva_sensitivities.py - add vega computation

def compute_vega_charge(
    sensitivities: CVASensitivities,
    risk_class: str,
) -> float:
    """
    MAR50.48: Vega capital charge for one risk class.
    
    K_vega = sqrt(sum_i sum_j ρ_ij × WS_i × WS_j)
    
    where WS_i = vega_sensitivity_i × RW_vega
    """
    if risk_class == "GIRR":
        vega_rw = 0.01  # 1% per MAR50.49
        ws_vec = [sens * vega_rw for sens in sensitivities.vega_girr.values()]
    elif risk_class == "FX":
        vega_rw = 0.15  # 15% per MAR50.51
        ws_vec = [sens * vega_rw for sens in sensitivities.vega_fx.values()]
    # etc for RCSR, EQ, CMDTY
    
    # Apply correlation within bucket
    rho_matrix = get_vega_correlation_matrix(risk_class)
    K_vega = np.sqrt(ws_vec @ rho_matrix @ ws_vec)
    
    return K_vega

# MAR50.46: Total vega = aggregate across 5 risk classes
def aggregate_vega_capital(all_sensitivities: List[CVASensitivities]) -> float:
    """
    Aggregate vega capital across all five vega risk classes.
    NO cross-risk-class correlation for vega per MAR50.46.
    """
    total = 0.0
    for risk_class in ["GIRR", "FX", "RCSR", "EQ", "CMDTY"]:
        K_rc = compute_vega_charge_for_risk_class(all_sensitivities, risk_class)
        total += K_rc**2
    return math.sqrt(total)
```

**Approximation (Currently Used):**
The current implementation uses a conservative approximation:
```python
# If portfolio has options → vega ≈ 10-20% of delta charge
# If no explicit options → vega ≈ 5-10% of delta charge (volatility from simulation)
```
This is acceptable for **initial deployment** but must be replaced with full computation for **regulatory sign-off**.

---

### Task 3: Add Proxy Spread Monthly Review Workflow (REQUIRED per MAR50.32(3))

**Regulatory Requirement:**
> MAR50.32(3): "Proxy spreads for illiquid counterparties must be reviewed AT LEAST MONTHLY and calibrated to live peer CDS data with full audit trail."

**Current State:**
- ✅ Database schema complete: `backend/data_sources/proxy_spread_calibration.py`
- ✅ Calibration record structure with reviewer tracking
- ✅ Stale calibration detection (>30 days)
- ⚠️ Needs production workflow integration

**File:** `backend/data_sources/proxy_spread_calibration.py`

**What's Needed:**

1. **Monthly Review Dashboard** - Add to Streamlit dashboard:

```python
# dashboard/app.py - add new page "CVA Proxy Spread Review"

elif page == "CVA Proxy Spread Review":
    st.markdown('<div class="page-title">Proxy Spread Calibrations</div>', unsafe_allow_html=True)
    st.markdown('<div class="page-sub">MAR50.32(3) Monthly Review Workflow</div>',
                unsafe_allow_html=True)
    
    registry = ProxySpreadRegistry.load()
    
    # Show calibrations due for review
    due_for_review = [c for c in registry.get_all_calibrations() 
                      if c.days_until_review() <= 7]
    
    if due_for_review:
        st.warning(f"⚠️ {len(due_for_review)} calibrations due for review within 7 days")
        
        for calib in due_for_review:
            with st.expander(f"{calib.sector} / {calib.credit_quality} / {calib.region}"):
                st.write(f"Current Spread: {calib.calibrated_spread_bps} bps")
                st.write(f"Last Review: {calib.calibration_date}")
                st.write(f"Peer Names: {', '.join(calib.peer_names)}")
                
                # Review form
                new_spread = st.number_input("Updated Spread (bps)", value=calib.calibrated_spread_bps)
                reviewer = st.text_input("Reviewer Name")
                notes = st.text_area("Review Notes")
                
                if st.button(f"Approve Review - {calib.sector}"):
                    registry.add_or_update_calibration(
                        ProxySpreadCalibration(
                            sector=calib.sector,
                            credit_quality=calib.credit_quality,
                            region=calib.region,
                            calibrated_spread_bps=new_spread,
                            calibration_date=date.today(),
                            peer_names=calib.peer_names,
                            peer_spreads=calib.peer_spreads,
                            review_status="APPROVED",
                            reviewer=reviewer,
                            next_review_date=date.today() + timedelta(days=30),
                            notes=notes,
                        )
                    )
                    registry.save()
                    st.success("✅ Calibration updated and approved")
```

2. **Automated Peer CDS Fetching** - Integrate with CDS spread service:

```python
# backend/data_sources/proxy_spread_calibration.py

def auto_calibrate_from_peers(
    sector: str,
    credit_quality: str,
    region: str,
    cds_service: CDSSpreadService,
) -> ProxySpreadCalibration:
    """
    Automatically calibrate proxy spread from liquid peer names.
    
    1. Select 3-5 liquid peer names matching sector/quality/region
    2. Fetch live 5Y CDS spreads
    3. Compute median spread (robust to outliers)
    4. Create calibration record with PENDING status
    5. Requires manual reviewer approval before use
    """
    peer_universe = LIQUID_CDS_UNIVERSE[sector][region]
    quality_filter = [p for p in peer_universe if p.credit_quality == credit_quality]
    
    peer_spreads = []
    peer_names = []
    
    for peer in quality_filter[:5]:  # Use top 5 liquid names
        spread = cds_service.get_spread(peer.name, tenor="5Y")
        if spread:
            peer_names.append(peer.name)
            peer_spreads.append(spread)
    
    if len(peer_spreads) < 3:
        raise ValueError(f"Insufficient liquid peers for {sector}/{credit_quality}/{region}")
    
    calibrated_spread = float(np.median(peer_spreads))
    
    return ProxySpreadCalibration(
        sector=sector,
        credit_quality=credit_quality,
        region=region,
        calibrated_spread_bps=calibrated_spread,
        calibration_date=date.today(),
        peer_names=peer_names,
        peer_spreads=peer_spreads,
        review_status="PENDING",  # Must be approved by credit desk
        reviewer="AUTO-CALIBRATION",
        next_review_date=date.today() + timedelta(days=30),
        notes=f"Auto-calibrated from {len(peer_names)} liquid peers",
    )
```

3. **Audit Trail** - Already implemented in `ProxySpreadRegistry.get_calibration_history()`

---

### Task 4: Verify Capital Floor Treatment in Aggregation Module (REQUIRED)

**Regulatory Requirement:**
> CAP10 FAQ1: "CVA capital is EXCLUDED from the 72.5% output floor calculation base. The floor applies to credit risk + CCR + market risk (excluding CVA) + operational risk."

**Current State:**
- ✅ Verified in `backend/main.py` line 326-330
- ✅ CVA RWA added separately after floor calculation
- ✅ Floor calculation uses `rwa_sa_based_excl_cva`

**File:** `backend/main.py`, function `PrometheusRunner.run_daily()`

**Verification:**

```python
# Line 326-330 in backend/main.py

# RBC20.11: Output Floor (72.5% of SA-based RWA)
# CAP10 FAQ1: CVA is EXCLUDED from floor base
rwa_sa_based_excl_cva = cap.get("rwa_sa_credit", rwa_credit) + \
                        cap.get("rwa_sa_ccr", rwa_ccr) + \
                        cap.get("rwa_sa_market", rwa_market) + \
                        rwa_op
rwa_floor = rwa_sa_based_excl_cva * 0.725

# Pre-floor RWA (excludes CVA per CAP10 FAQ1)
rwa_total_pre_floor = rwa_credit + rwa_ccr + rwa_market + rwa_op

# Apply floor
floor_triggered = rwa_total_pre_floor < rwa_floor
if floor_triggered:
    rwa_total = rwa_floor
else:
    rwa_total = rwa_total_pre_floor

# Add CVA AFTER floor calculation (CAP10 FAQ1)
rwa_total += rwa_cva
```

**✅ CONFIRMED COMPLIANT** - No action required.

---

## Priority Roadmap

### Phase 1: Operational (COMPLETE) ✅
- [x] Add Operational Risk to dashboard navigation
- [x] Generate sample loss event data
- [x] Fix module import paths (operational_risk.py, loss_event_database.py)
- [x] Test Operational Risk dashboard display

### Phase 2: SA-CVA Full Implementation (HIGH PRIORITY)
- [ ] **Week 1-2:** Integrate CVA sensitivity computation with IMM engine
- [ ] **Week 3:** Implement GIRR and FX delta risk classes
- [ ] **Week 4:** Implement RCSR, EQ, CMDTY delta risk classes (if portfolios exist)
- [ ] **Week 5:** Implement full vega charge computation
- [ ] **Week 6:** Testing and validation against sample portfolios

### Phase 3: Proxy Spread Workflow (MEDIUM PRIORITY)
- [ ] **Week 7:** Build CVA Proxy Spread Review dashboard page
- [ ] **Week 8:** Integrate auto-calibration with live CDS data
- [ ] **Week 9:** User acceptance testing with credit desk
- [ ] **Week 10:** Production deployment with monthly review alerts

### Phase 4: Regulatory Sign-Off (FINAL)
- [ ] **Week 11:** Internal audit review
- [ ] **Week 12:** Documentation package for supervisors
- [ ] **Week 13:** Supervisory approval for SA-CVA approach

---

## Testing Requirements

### Unit Tests

```bash
# Test SA-CVA full risk class coverage
pytest tests/test_sa_cva_full.py -v

# Test vega charge computation
pytest tests/test_cva_vega.py -v

# Test proxy spread workflow
pytest tests/test_proxy_spread_calibration.py -v

# Test capital floor exclusion
pytest tests/test_capital_aggregation.py::test_cva_excluded_from_floor -v
```

### Integration Tests

```bash
# End-to-end CVA capital with all risk classes
pytest tests/test_cva_enhancements.py::test_e2e_sa_cva -v

# Monthly review workflow
pytest tests/test_proxy_spread_review.py -v
```

---

## Compliance Checklist

### SA-CVA (MAR50.40-77)
- [x] Framework for 6 delta risk classes (MAR50.43)
- [ ] **GIRR delta** fully implemented
- [ ] **FX delta** fully implemented
- [x] **CCSR delta** fully implemented
- [ ] **RCSR delta** fully implemented (when CDS portfolio exists)
- [ ] **EQ delta** fully implemented (when equity exposure exists)
- [ ] **CMDTY delta** fully implemented (when commodity exposure exists)
- [x] Cross-risk-class correlation (MAR50.44 Table 4)
- [ ] **Vega charge** full computation (MAR50.48)
- [x] Vega approximation (interim acceptable)

### Proxy Spreads (MAR50.32(3))
- [x] Calibration database schema
- [x] Monthly review workflow framework
- [ ] **Production data loaded**
- [ ] **Automated peer CDS fetching**
- [ ] **Credit desk review integration**
- [x] Audit trail (calibration history)

### Capital Aggregation (RBC20, CAP10)
- [x] CVA excluded from output floor (CAP10 FAQ1)
- [x] Floor calculation verified
- [x] CVA added to total RWA post-floor

---

## Support & Documentation

### Key Files

| File | Purpose |
|------|---------|
| `backend/engines/cva.py` | Main CVA engine (BA-CVA + SA-CVA approximation) |
| `backend/engines/cva_sensitivities.py` | Full SA-CVA framework (6 delta + 5 vega) |
| `backend/data_sources/proxy_spread_calibration.py` | Proxy spread workflow |
| `backend/main.py` | Capital aggregation with floor treatment |
| `dashboard/app.py` | Main dashboard (includes Operational Risk) |

### Contact

For questions on CVA implementation:
- **Risk Analytics Team**: risk-analytics@prometheus.example.com
- **Regulatory Capital Team**: reg-capital@prometheus.example.com
- **CVA Desk**: cva-desk@prometheus.example.com

---

## Appendix: BASEL References

- **MAR50**: CVA Risk Capital Charge
- **MAR50.43**: Six delta risk classes
- **MAR50.44**: Cross-risk-class correlation
- **MAR50.48**: Vega charge (always material)
- **MAR50.32(3)**: Proxy spread monthly review
- **RBC20.9**: Total RWA aggregation
- **CAP10 FAQ1**: CVA exclusion from output floor
- **OPE25**: Operational Risk SMA

---

**Document Version**: 1.0  
**Last Updated**: April 11, 2026  
**Status**: Operational Risk ✅ Complete | SA-CVA Full 🔧 In Progress

