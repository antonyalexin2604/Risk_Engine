# PHASE 2 FEASIBILITY ASSESSMENT
## Can All Recommendations Be Implemented?

**Date:** April 25, 2026  
**Analysis Scope:** Full Phase 2A + 2B + 2C assessment  
**Prepared For:** Executive Steering Committee, Development Leadership

---

## EXECUTIVE SUMMARY

**Short Answer:** Yes, all Phase 2 recommendations **CAN be implemented** within the 30-week timeline with the proposed resource allocation. However:

✅ **Phase 2A (Weeks 1–7):** 99% feasible — foundational, modular, low dependencies  
✅ **Phase 2B (Weeks 8–17):** 95% feasible — moderate complexity, proven techniques  
⚠️ **Phase 2C (Weeks 18–29):** 85% feasible — analytics-heavy, depends on 2A/2B success  

**Critical Success Factors:**
1. Dedicated 1.0 FTE dev lead (non-negotiable)
2. Clean data feeds by July 31 (for Phase 2B scenarios)
3. Executive blocking time removed (no scope creep)
4. Weekly steering checkpoints (catch issues early)

**Contingency Plan:** If constraints emerge, Phase 2C (analytics) can be deferred to 2027 Q2 without impacting exam readiness.

---

## DETAILED FEASIBILITY ANALYSIS

### PHASE 2A: FOUNDATION (Weeks 1–7)

#### Initiative 2A-01: Calculation Trace Engine

**Feasibility: 98% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | Low-medium (implement decorator + DB schema) | HIGH |
| **Code Pattern** | Python decorator pattern — well-established | HIGH |
| **Database Design** | JSON audit tables — PostgreSQL native strength | HIGH |
| **Testing** | Unit tests straightforward; edge cases minimal | HIGH |
| **Risk** | Performance overhead — mitigated by selective tracing | MEDIUM |
| **Dependencies** | None (isolated module) | HIGH |

**Implementation Pathway:**
```
Week 1-2: Core trace_engine.py (~600 lines) + unit tests
Week 2-3: Database schema + persistence layer
Week 3-4: Integration with A-IRB + spot-check validation
Week 4-5: Buffer for edge cases / performance tuning
```

**Potential Blockers:** NONE identified

**Contingency:** If performance overhead > 5%, implement selective tracing (only trace 10% of exposures in production, sample-based audit trail)

---

#### Initiative 2A-02: Model Validation Checklist (SR 11-7)

**Feasibility: 95% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | Low (VC-01 to VC-05 = queries + thresholds) | HIGH |
| **Code Pattern** | Modular functions calling existing tests | HIGH |
| **GitHub Actions** | Standard YAML — no innovation needed | HIGH |
| **Testing** | Each checkpoint tested in isolation | HIGH |
| **Risk** | Backtesting may require historical data (3+ months) | MEDIUM |
| **Dependencies** | Requires Phase 2A trace engine (for logging) | MEDIUM |

**Implementation Pathway:**
```
Week 2-3: Governance checker core (VC-01, VC-02, VC-03)
Week 3-4: GitHub Actions workflow setup
Week 4-5: Integration testing; dry-runs
Week 5-6: Slack webhook + alerting
Week 6-7: Documentation + runbook
```

**Potential Blockers:**
- ⚠️ VC-02 (Backtesting) requires 36 months historical data
  - **Mitigation:** If unavailable, use synthetic backtest (6-month proxy with stress scaling)
  - **Timeline impact:** Add 1 week if backfill needed

**Contingency:** Run VC-01 through VC-04 initially; defer VC-05 (monitoring) to Phase 2B if time tight

---

#### Initiative 2A-03: Data Quality Management System (DQMS)

**Feasibility: 90% ⚠️**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | Medium (5 metrics × multiple sources) | MEDIUM |
| **Code Pattern** | Fairly standard — SQL queries + scoring | MEDIUM |
| **Data Dependencies** | Needs stable data sources (Bloomberg, Refinitiv) | LOW |
| **Risk** | Data feed instability; quality degradation | HIGH |
| **Testing** | Depends on live data availability | MEDIUM |
| **Dependencies** | Upstream: market data providers stable | HIGH |

**Implementation Pathway:**
```
Week 5-6: DQ metric definitions + thresholds
Week 6-7: Dashboard prototype with 2-3 key metrics
Week 7+: Expand to full 5-metric suite in Phase 2B
```

**Potential Blockers:**
- 🔴 Market data provider instability during Phase 2A
- 🟡 CDS curve data quality varies by counterparty
- 🟡 Historical calibration data may have gaps

**Risk Mitigation:**
1. Start with internal data only (PD, LGD, EAD)
2. Defer Bloomberg/Refinitiv integration to week 8
3. Build "degraded mode" dashboard (works with partial data)

**Contingency:** 
- **Full DQMS (recommended):** Target Week 7
- **MVP DQMS:** Target Week 5 (3 metrics only); expand in Phase 2B
- **Minimal DQ:** Defer to Phase 2B, focus on Phase 2A tracing

---

### PHASE 2B: REGULATORY COMPLIANCE (Weeks 8–17)

#### Initiative 2B-01: Dynamic Output Floor Calibration

**Feasibility: 95% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | Low-medium (rolling RWA ratio + multiplier calc) | MEDIUM |
| **Code Pattern** | Standard quantitative approach | HIGH |
| **Data Requirements** | 24 months SA vs. A-IRB RWA history | MEDIUM |
| **Risk** | Floor calibration overly sensitive to regime | LOW |
| **Testing** | Benchmarkable against regulatory baselines | HIGH |
| **Dependencies** | Requires Phase 2A trace engine audit trail | LOW |

**Implementation Pathway:**
```
Week 8-9: Design floor formula + calibration methodology
Week 9-10: Implement output_floor.py (~300 lines)
Week 10-11: Backtest vs. CRR3 framework
Week 11-12: Shadow run (computed but not applied)
Week 12-13: Validation + threshold tuning
```

**Potential Blockers:**
- ⚠️ Historical RWA data quality (missing prior months)
  - **Mitigation:** Use baseline 72.5% if data < 12 months; upgrade when available

**Contingency:** If CRR3 guidance changes (unlikely by Oct 2026), revert to static 72.5% floor immediately

---

#### Initiative 2B-02: Leverage Ratio 3.6% (CRR3)

**Feasibility: 98% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | Very low (simple ratio check) | HIGH |
| **Code Pattern** | One-liner constraint check | HIGH |
| **Data Requirements** | Exposure measure (CRE99.8) — already in system | HIGH |
| **Risk** | None identified | HIGH |
| **Testing** | Straightforward KL math | HIGH |
| **Dependencies** | None | HIGH |

**Implementation Pathway:**
```
Week 8: Code implementation + config update (~30 min)
Week 8-10: Testing + validation
Week 10-11: Dashboard alerts + reporting
```

**Potential Blockers:** NONE

**Contingency:** Treat as "always-on" constraint; no phasing needed

---

#### Initiative 2B-03: ESG/Climate Risk Calibration

**Feasibility: 80% ⚠️ (highest-risk item in Phase 2B)**

| Aspect | Assessment | Confidence |
|--------|-----------|-----------|
| **Complexity** | High (sector mapping, policy scenario design) | MEDIUM |
| **Code Pattern** | Moderate (configuration-driven) | MEDIUM |
| **Data Requirements** | ESG scores, transition pathway ratings, physical risk maps | LOW |
| **Risk** | ESG data quality varies; scenario calibration uncertain | HIGH |
| **Testing** | Backtesting ESG PD uplift hard without historical data | LOW |
| **Dependencies** | Requires reliable ESG data feed | HIGH |
| **Regulatory Alignment** | CRR3 Art. 87a guidance still evolving | MEDIUM |

**Implementation Pathway:**
```
Week 11-12: ESG sector classification + data sourcing
Week 12-14: Transition risk calibration (consultation with risk team)
Week 14-15: Physical risk layer (real estate focus first)
Week 15-16: Scenario testing + sensitivity analysis
Week 16-17: Regulatory alignment review
```

**Potential Blockers:**
1. 🔴 ESG data quality from vendors (MSCI, Refinitiv, Bloomberg)
2. 🔴 CRR3 Art. 87a calibration guidance still evolving (EBA/ECB updates anticipated Jun 2026)
3. 🟡 Physical risk data availability (flood maps, heat stress models)
4. 🟡 Consensus on carbon intensity thresholds

**Risk Mitigation:**
1. Start with transition risk only (simpler calibration)
2. Use conservative uplift assumptions (will tighten as guidance clarifies)
3. Build as configuration (allows rapid updates if guidance changes)
4. Use third-party ESG indices where available (reduce data sourcing burden)

**Contingency Options:**
- **Full ESG/Climate (recommended):** Week 17 (as planned)
- **Transition Risk Only:** Week 14 (defer physical risk to Phase 2C)
- **Stub/Placeholder:** Week 10 (use fixed 0.5% uplift; revisit after Jun 2026 EBA guidance)

**Decision Point:** Gate 3 (Oct 1) — if ESG data insufficient, revert to simplified transition risk model

---

#### Initiative 2B-04: Scenario Library (10+ regulatory + custom)

**Feasibility: 92% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|---------|
| **Complexity** | Medium (data organization + scenario engine) | MEDIUM |
| **Code Pattern** | Well-established (Scenario dataclass + library) | HIGH |
| **Data Requirements** | Historical rates, spreads, Vol data (Bloomberg/Refinitiv) | MEDIUM |
| **Risk** | Calibration accuracy; scenario file maintenance | MEDIUM |
| **Testing** | Scenario backtesting vs. actual returns | MEDIUM |
| **Dependencies** | Requires stable market data feed | MEDIUM |

**Implementation Pathway:**
```
Week 9-10: Scenario design framework + data sourcing
Week 10-11: Baseline scenarios (2007-2009, ECB CRDP, FED CCAR)
Week 11-12: Custom scenarios (geopolitical, supply chain)
Week 12-13: Scenario engine + portfolio re-pricing
Week 13-14: Dashboard integration
Week 14-15: Stress testing validation
Week 15-17: Regulatory alignment + documentation
```

**Potential Blockers:**
- ⚠️ Historical market data gaps (some scenarios hard to reconstruct)
- ⚠️ FED/ECB scenario parameters not always publicly available

**Mitigation:** 
1. Use publicly available CCAR/CRDP scenario definitions
2. Construct missing historical periods from available spreads + correlation analysis
3. Publish scenario assumptions transparently (regulatory will validate)

**Contingency:** If full 10-scenario library not ready, launch with 5 core scenarios (2007-2009, ECB CRDP, FED CCAR, HFL, custom) by Week 15; add 5+ more in Phase 2C

---

### PHASE 2C: MARKET PRACTICE (Weeks 18–29)

#### Initiative 2C-01: Parameter Sensitivities API (Greeks)

**Feasibility: 88% ⚠️**

| Aspect | Assessment | Confidence |
|--------|-----------|---------|
| **Complexity** | High (multi-engine Greeks, numerical differentiation) | LOW |
| **Code Pattern** | Established but domain-specific | MEDIUM |
| **Data Requirements** | Requires stable parameter estimates (PD, LGD, correlation) | MEDIUM |
| **Risk** | Numerical stability (edge cases in differentiation) | HIGH |
| **Testing** | Comparison to analytical Greeks (where available) | MEDIUM |
| **Dependencies** | Requires Phase 2A trace engine (to isolate parameter impact) | MEDIUM |

**Implementation Pathway:**
```
Week 18-19: Greeks definition per engine (A-IRB, SA-CCR, FRTB)
Week 19-21: Numerical differentiation implementation + edge case handling
Week 21-22: Stability testing (shock absorption, correlation limits)
Week 22-24: Dashboard visualization (heatmaps, tornado charts)
Week 24-26: Performance optimization (Greeks computed in <30 sec for 1M exposures)
Week 26-29: UAT + documentation
```

**Potential Blockers:**
- 🔴 Numerical stability near boundary conditions (PD→0, LGD→1, correlation→1)
- 🟡 Performance: Computing Greeks for 1M+ exposures may take >1 minute
- 🟡 Correlation matrix conditioning issues (near-singular matrices)

**Risk Mitigation:**
1. Implement robust numerical differentiation (scipy.optimize.approx_fprime with adaptive step size)
2. Cache Greeks results (refresh daily, not real-time)
3. Add numerical stability checks + warnings
4. Parallel compute over exposure buckets

**Contingency:**
- **Full Greeks API (recommended):** Week 29
- **Simplified Greeks (5 key sensitivities only):** Week 25
- **Deferred to Phase 3:** If numerical issues severe, defer to post-exam (2027 Q3)

---

#### Initiative 2C-02: RWA Attribution Engine

**Feasibility: 93% ✅**

| Aspect | Assessment | Confidence |
|--------|-----------|---------|
| **Complexity** | Medium (recursive RWA decomposition) | MEDIUM |
| **Code Pattern** | Straightforward algorithm | HIGH |
| **Data Requirements** | Portfolio granularity (obligor, sector, geography) | HIGH |
| **Risk** | Decomposition logic correctness | LOW |
| **Testing** | Attribution reconciliation (sum = total RWA) | HIGH |
| **Dependencies** | Low; self-contained | HIGH |

**Implementation Pathway:**
```
Week 20-21: Attribution algorithm design + testing
Week 21-22: Database schema for attribution results
Week 22-24: Dashboard (waterfall, sunburst, concentration curves)
Week 24-25: Scenario attribution (RWA by scenario)
Week 25-27: Performance optimization (1M exposures in <5 sec)
Week 27-29: Regulatory alignment + documentation
```

**Potential Blockers:** NONE significant identified

**Contingency:** Straightforward; can handle contingencies through incremental rollout (start with obligor-level, expand to sector/geography phased)

---

#### Initiative 2C-03: Advanced Dashboards & Reporting

**Feasibility: 90% ⚠️ (UI-dependent)**

| Aspect | Assessment | Confidence |
|--------|-----------|---------|
| **Complexity** | Medium (Streamlit development + charting) | MEDIUM |
| **Code Pattern** | Well-known (Python dashboard frameworks) | HIGH |
| **Data Requirements** | Aggregation from all prior phases | HIGH |
| **Risk** | Performance (loading large datasets in dashboard) | MEDIUM |
| **Testing** | Browser testing + user acceptance | MEDIUM |
| **Dependencies** | Depends on 2A, 2B, 2C data availability | HIGH |

**Implementation Pathway:**
```
Week 22-23: Dashboard page design + layout
Week 23-25: Greeks page + sensitivities visualization
Week 25-26: Attribution & concentration page
Week 26-27: Scenario analysis page
Week 27-28: Export functionality (xlsx, csv, pdf)
Week 28-29: UAT + performance tuning
```

**Potential Blockers:**
- 🟡 Streamlit performance with large datasets (>100k rows)
- 🟡 Browser refresh timeout for complex visualizations

**Mitigation:**
1. Pre-aggregate data (don't fetch raw trade data in dashboard)
2. Implement caching + memoization (Streamlit @st.cache_data)
3. Paginate results (Top 100 obligors, not all 1M+)
4. Defer real-time updates to Phase 3 (use daily refresh in 2C)

**Contingency:** Launch MVP dashboard (Greeks + Attribution) by Week 27; expand reporting in Phase 3

---

## IMPLEMENTATION FEASIBILITY MATRIX

| Phase | Initiative | Feasibility | Timeline Risk | Resource Risk | Technical Risk | Decision |
|-------|-----------|-------------|-------------|-------------|-------------|----------|
| **2A** | Trace Engine | 98% | LOW | ✓ | LOW | **GO** |
| **2A** | Governance Checklist | 95% | LOW | ✓ | LOW | **GO** |
| **2A** | Data Quality Dashboard | 90% | MEDIUM | ✓ | MEDIUM | **GO w/ MVP** |
| **2B** | Dynamic Output Floor | 95% | LOW | ✓ | LOW | **GO** |
| **2B** | Leverage Ratio | 98% | MINIMAL | ✓ | MINIMAL | **GO** |
| **2B** | ESG/Climate Risk | 80% | HIGH | ⚠️ | HIGH | **PROCEED CAUTIOUSLY** |
| **2B** | Scenario Library | 92% | MEDIUM | ✓ | MEDIUM | **GO** |
| **2C** | Greeks API | 88% | HIGH | ⚠️ | HIGH | **GO w/ CONTINGENCY** |
| **2C** | RWA Attribution | 93% | LOW | ✓ | LOW | **GO** |
| **2C** | Advanced Dashboards | 90% | MEDIUM | ⚠️ | MEDIUM | **GO** |

---

## RESOURCE FEASIBILITY ANALYSIS

### Staffing Plan: Can It Be Done with Proposed 1.0 FTE?

**Proposed:** 1.0 FTE equivalent over 30 weeks (5 people × part-time)

```
30 weeks × 40 hrs/week = 1,200 total hours available
294 hours budgeted = 24.5% utilization ✓ FEASIBLE
```

**BUT Reality Check:** 294 hours is *optimistic* estimate. Typical project actuals run 20-30% higher due to:
- Testing & debugging (not included in initial estimate)
- Code review cycles
- Integration testing
- Documentation refinement
- Stakeholder meetings
- Contingency buffer

**Revised Estimate:**
```
Conservative: 294 × 1.25 = 368 hours (30% utilization)
Realistic: 294 × 1.40 = 412 hours (34% utilization)
Maximum: 294 × 1.60 = 470 hours (39% utilization)
```

**Assessment:** 1.0 FTE can support implementation if:
1. ✅ Team focused (no other projects)
2. ✅ Clear prioritization (cut non-critical items if needed)
3. ✅ Weekly gate reviews (early problem detection)
4. ❌ No major blockers (market data issues, etc.)

**If Blockers Emerge:**
- Phase 2C (analytics) can be deferred → reduces load by 40% (115 hours)
- ESG/Climate can be simplified → reduces load by 20% (25 hours)
- DQMS can be MVP only → reduces load by 15% (20 hours)

---

## CRITICAL PATH & DEPENDENCY MAPPING

```
Phase 2A (Foundation) — CRITICAL PATH
├─ Trace Engine (Weeks 1-4) ✓ No dependencies
│  └─ ENABLES: Governance Checker (Week 2+ parallel), Phase 2B validation
├─ Governance Checker (Weeks 2-6) ✓ Depends on Trace Engine (soft)
└─ DQ Dashboard (Weeks 5-7) ⚠️ Depends on data feed stability

Phase 2B (Compliance) — CRITICAL PATH
├─ Dynamic Floor (Weeks 8-12) ✓ Depends on Phase 2A complete
├─ Leverage Ratio (Weeks 8-10) ✓ Independent
├─ ESG/Climate (Weeks 11-17) ⚠️ Depends on ESG data availability
└─ Scenario Library (Weeks 9-15) ✓ Depends on market data feeds

Phase 2C (Analytics) — NON-CRITICAL PATH
├─ Greeks API (Weeks 18-26) ⚠️ Depends on Phase 2A/2B complete + parameter stability
├─ RWA Attribution (Weeks 20-27) ✓ Independent (portfolio data driven)
└─ Dashboards (Weeks 22-29) ✓ Depends on prior phases data availability
```

**Key Insight:** Phase 2A must complete successfully → Phase 2B can proceed → Phase 2C is independent (can be deferred if needed)

---

## CONTINGENCY PLANS: WHAT IF...

### Scenario A: Resources Constrained (1.0 FTE becomes 0.7 FTE)

**Impact:** 40% reduction in available hours

**Prioritization (Cut-off list):**
1. Keep: Phase 2A (Trace, Governance, DQ)
2. Keep: Phase 2B (Floor, Leverage, Scenarios)
3. Keep: Phase 2C (Attribution — high business value)
4. **CUT:** Phase 2C (Greeks API, Advanced Dashboards) → defer to Phase 3

**Timeline Impact:** Exam-ready by Jan 2027 ✓ | Analytics delayed to Q2 2027

---

### Scenario B: Data Feed Issues (Bloomberg/Refinitiv unstable)

**Impact:** Scenarios uncalibrated; ESG data unavailable; DQMS degraded

**Response:**
1. Use **internal benchmarks only** for scenarios (recreate from 3-year historical)
2. **Simplify ESG** to transition risk only (defer physical risk mapping)
3. **MVP DQMS** using 3 metrics (internal data only)
4. **Delay Gap:** 2-3 weeks, absorb by compressing Phase 2C timeline

**Timeline Impact:** Phase 2B complete by Nov 15 (2 weeks slip) ✓ Still exam-ready (Jan 2027)

---

### Scenario C: ESG Guidance Changes (EBA releases new framework Jul 2026)

**Impact:** ESG calibration may need rework

**Response:**
1. Build ESG as **configuration** (not hard-coded formulas)
2. Use **conservative assumptions** initially (overestimate uplift)
3. **Rapid recalibration** once guidance finalized (1-2 week update window)
4. **Gate 3 decision** (Oct 1): if rework needed, apply in Phase 2C

**Timeline Impact:** ESG delivery slips from Week 17 → Week 20; Phase 2C absorbs ✓ Exam-ready still achievable

---

### Scenario D: Regulatory Exam Moved Earlier (Q1 → Q4 2026)

**Impact:** 8 weeks lost; Phase 2B cannot complete

**Response:**
1. **Accelerate Phase 2A** (complete by Week 6, not 7)
2. **Skip Phase 2B advanced features:**
   - ✓ Keep dynamic floor (critical)
   - ✓ Keep leverage ratio (quick)
   - ❌ Cut ESG/Climate detailed calibration → stub only
   - ❌ Cut scenario library → use 2007-2009 baseline only
3. **Focus on exam readiness:** Trace engine + governance checks

**Timeline Impact:** Simplified Phase 2B by Oct 31 ✓ Exam-ready with MVP features

---

## GO/NO-GO DECISION FRAMEWORK

### Gate 1: Executive Approval (May 1, 2026)
**Decision:** Commit to Phase 2 budget + resource allocation?

**Go Criteria:**
- [ ] CRO approves $56K investment
- [ ] 1.0 FTE team confirmed + released from other projects
- [ ] Steering committee formed + weekly cadence set
- [ ] Phase 2A kickoff scheduled

**No-Go Triggers:**
- ❌ Budget not approved
- ❌ Resources needed for urgent operational issues
- ❌ Major regulatory guidance changes (unlikely)

---

### Gate 2: Phase 2A Completion (August 1, 2026)
**Decision:** Proceed to Phase 2B or remediate?

**Go Criteria:**
- [ ] Trace engine: 100% RWA coverage, <5% performance overhead
- [ ] Governance checks: All 5 automated, 90%+ pass rate
- [ ] DQ dashboard: Live with 3+ key metrics
- [ ] Test coverage: ≥95% for Phase 2A code
- [ ] Auditor review: No red flags on trace design

**Conditional-Go:**
- ⚠️ Trace engine coverage 95–99% (catch remaining edge cases in Phase 2B)
- ⚠️ DQ dashboard MVP only (expand in Phase 2B)

**No-Go Triggers:**
- ❌ Trace engine performance overhead >10%
- ❌ Cannot achieve ≥90% RWA traceability
- ❌ Governance checks failing >30% of time

---

### Gate 3: Phase 2B Testing (October 1, 2026)
**Decision:** Shadow run → Production or continue tuning?

**Go Criteria:**
- [ ] Dynamic floor RWA divergence <1% vs. static baseline
- [ ] Scenario library calibrated to regulatory standards (5+ scenarios live)
- [ ] ESG PD uplift tested; no unexplained RWA spikes
- [ ] Leverage ratio constraint active (no breaches detected)
- [ ] External auditor sign-off on methodology

**Conditional-Go:**
- ⚠️ ESG calibration incomplete; use conservative assumptions
- ⚠️ Scenario library 4 scenarios (not 5+); expand in Phase 2C

**No-Go Triggers:**
- ❌ Floor divergence >3% (indicates calibration issue)
- ❌ Scenario library validation fails
- ❌ Auditor objects to ESG assumptions (requires rework)

---

### Gate 4: Phase 2C Rollout (January 15, 2027)
**Decision:** All components live or phased?

**Go Criteria:**
- [ ] Greeks API: all 10+ sensitivities computed in <30 sec
- [ ] RWA attribution: 50+ obligor-level breaks, reconciles to total
- [ ] Dashboard: 4+ pages live, UAT passed
- [ ] Reporting: automated daily/weekly exports to ALCO

**Conditional-Go:**
- ⚠️ Greeks API: defer complex correlation Greeks; keep delta/gamma only
- ⚠️ Dashboards: MVP (Greeks + Attribution); defer Scenario/DQMS pages to Phase 3

**No-Go Triggers:**
- ❌ Critical bugs blocking audit trail functionality
- ❌ Performance issues (system degradation in production)

---

## MYTH-BUSTING: COMMON OBJECTIONS ADDRESSED

### "294 hours is too optimistic"

**Reality Check:**
- Trace Engine: 40 hrs (not 60) — decorator pattern is well-known
- Governance: 30 hrs (not 40) — mostly querying existing tests
- Output Floor: 20 hrs (not 25) — simple ratio calculation
- Greeks API: 60 hrs (this one is harder) — but still achievable with numerical libraries

**Confidence:** Actual effort likely 350–400 hours (vs. 294 estimated) — still <35% utilization of 1.0 FTE

---

### "We don't have 1.0 FTE available"

**Alternative Paths:**
1. **Extend timeline:** 30 weeks → 40 weeks (slower burn, same quality)
2. **Use contractors:** $150/hr × 100 hours = $15K (vs. internal cost)
3. **Prioritize ruthlessly:** Phase 2A + 2B only; defer 2C to 2027 Q2 ($40K instead of $56K)
4. **Hybrid model:** Split Phase 2A/2B (1 senior dev) + Phase 2C (junior + external contractor)

**Bottom Line:** Resource constraints move needle, don't break feasibility

---

### "ESG data isn't ready; we can't complete Phase 2B"

**This is the ONLY genuine blocker.** Response:

1. **Use conservative assumption:** 50 bps fixed uplift per sector (no calibration)
2. **Build as configuration:** When data arrives (Jun-Jul 2026), swap in actual calibration
3. **Flag in governance:** Mark ESG results as "preliminary" until data-driven

**Timeline impact:** +1 week (for recalibration if data arrives late)

---

### "Regulatory exam might move earlier; we won't be ready"

**Mitigation Options:**
1. **Push for later exam date** (regulatory sometimes flexible if they know re-platforming in progress)
2. **Deliver Phase 2A only by Oct 2026** (trace + governance = exam-ready)
3. **Use phased rollout:** Exam on Oct 15 with Phase 2A; Phase 2B/2C complete by Jan 2027

**Timeline: Still feasible**, even with early exam

---

## FINAL ASSESSMENT: CAN WE DO THIS?

### By Component:

| Component | Feasible | Confidence | Go/No-Go |
|-----------|----------|-----------|----------|
| **Trace Engine** | YES | 98% | ✅ GO |
| **Governance Checks** | YES | 95% | ✅ GO |
| **DQ Dashboard** | MAYBE | 90% | ⚠️ GO (MVP) |
| **Output Floor** | YES | 95% | ✅ GO |
| **Leverage Ratio** | YES | 98% | ✅ GO |
| **ESG/Climate** | MAYBE | 80% | ⚠️ PROCEED CAUTIOUSLY |
| **Scenarios** | YES | 92% | ✅ GO |
| **Greeks API** | MAYBE | 88% | ⚠️ CONTINGENCY PLAN |
| **Attribution** | YES | 93% | ✅ GO |
| **Dashboards** | YES | 90% | ✅ GO |

### Overall Verdict:

**✅ YES — All Phase 2 recommendations CAN be implemented**

**With caveats:**
1. Phase 2A → 99% confidence (core deliverable, minimal risk)
2. Phase 2B → 92% confidence (depends on ESG data; workflow well-known)
3. Phase 2C → 85% confidence (analytics nice-to-have; can defer if needed)

**Success Requirements (non-negotiable):**
- ✅ 1.0 FTE dedicated team (approved by May 1)
- ✅ Executive blocking time (no scope creep)
- ✅ Weekly steering gates (catch issues early)
- ✅ Clean data feeds by July 31 (for Phase 2B)
- ✅ Regulatory guidance finalized by June (for ESG calibration)

**Fallback Plan (if constraints emerge):**
- Deliver Phase 2A + 2B core (Floor, Leverage, Scenarios) by Jan 2027 ✓ Exam-ready
- Defer Phase 2C analytics to 2027 Q2 (still feasible, lower priority)

---

## RECOMMENDATION TO STEERING COMMITTEE

**Motion:** Approve Phase 2 implementation with the following conditions:

1. **Proceed with all recommendations** as planned (30 weeks, $56K)
2. **Establish 4 decision gates** (May 1, Aug 1, Oct 1, Jan 15) with go/no-go criteria
3. **Nominate lead quant/developer** by April 30 (critical-path person)
4. **Approve 1.0 FTE resource allocation** with protection from other project demands
5. **Authorize contingency plan** (Phase 2C defer to Q2 2027 if resources/data constrained)
6. **Set weekly steering committee** meetings to monitor progress vs. plan

**Expected Outcome:** Exam-ready PROMETHEUS + 50–100 bps capital efficiency by January 2027

---

**Document Prepared By:** Technical Feasibility Analysis Team  
**Distribution:** Executive Steering Committee, Development Leadership, CRO  
**Date:** April 25, 2026  
**Classification:** Confidential


