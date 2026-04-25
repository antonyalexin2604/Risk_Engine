# PHASE 2 DECISION MATRIX & RISK MITIGATION
## Quick Reference for Steering Committee

**Date:** April 25, 2026  
**Prepared for:** Executive Steering Committee Meeting  
**Time to Read:** 10 minutes

---

## ONE-PAGE SUMMARY: CAN WE DO THIS?

### Executive Answer: **YES ✅**

- **Phase 2A (Weeks 1–7):** 99% feasible | Low risk | Core exam-readiness foundation
- **Phase 2B (Weeks 8–17):** 92% feasible | Medium risk | Regulatory compliance + capital efficiency
- **Phase 2C (Weeks 18–29):** 85% feasible | Medium risk | **DEFERRABLE** if needed

**Critical Success Factors:**
1. 1.0 FTE dedicated team (non-negotiable)
2. No scope creep (weekly gates enforce priorities)
3. Clean data feeds by July 31
4. ESG guidance finalized by June (likely)

**Fallback Plan:** If constraints emerge → deliver Phase 2A + 2B core (exam-ready) by Jan 2027; defer analytics (Phase 2C) to Q2 2027

---

## IMPLEMENTATION FEASIBILITY BY PHASE

### Phase 2A: Foundation (Weeks 1–7) — GREEN ✅

| Component | Effort | Risk | Technical | Data | Feasibility |
|-----------|--------|------|-----------|------|------------|
| **Trace Engine** | 40 hrs | LOW | Proven (Python decorators) | N/A | **98% ✅** |
| **Governance Checklist** | 30 hrs | LOW | Straightforward (queries) | Internal | **95% ✅** |
| **Data Quality Dashboard** | 40 hrs | MEDIUM | Standard (Streamlit) | Stream | **90% ⚠️** |
| **Phase 2A Total** | **110 hrs** | **LOW** | — | — | **95% ✅** |

**Gate 2 Success Criteria (Aug 1):**
- ✅ Trace engine: 100% RWA coverage, <5% performance overhead
- ✅ Governance checks: All 5 automated, passing
- ✅ DQ dashboard: Live (MVP with 3+ metrics)

**Go-Live Risk:** MINIMAL | Contingency: None needed (Phase 2A is modular, no dependencies)

---

### Phase 2B: Regulatory Compliance (Weeks 8–17) — YELLOW ⚠️

| Component | Effort | Risk | Dependencies | Feasibility |
|-----------|--------|------|--------------|------------|
| **Dynamic Output Floor** | 25 hrs | LOW | Phase 2A ✓ | **95% ✅** |
| **Leverage Ratio 3.6%** | 8 hrs | MINIMAL | None | **98% ✅** |
| **ESG/Climate Calibration** | 25 hrs | **HIGH** | ESG data 🔴 | **80% ⚠️** |
| **Scenario Library** | 30 hrs | MEDIUM | Market data ⚠️ | **92% ✅** |
| **Phase 2B Total** | **88 hrs** | **MEDIUM** | — | — | **92% ✅** |

**Gate 3 Success Criteria (Oct 1):**
- ✅ Dynamic floor: RWA divergence <1% vs. static
- ✅ Scenarios: 5+ regulatory, live
- ⚠️ ESG: Calibrated OR conservative assumptions (if data delayed)

**Go-Live Risk:** MEDIUM | 
- **If ESG data ready (80% likely):** Go → 92% feasible
- **If ESG data delayed (20% likely):** Use stub until Dec, update → 90% feasible

---

### Phase 2C: Market Practice (Weeks 18–29) — YELLOW ⚠️

| Component | Effort | Risk | Complexity | Feasibility |
|-----------|--------|------|-----------|------------|
| **Greeks API** | 60 hrs | MEDIUM | Numerical stability | **88% ⚠️** |
| **RWA Attribution** | 20 hrs | LOW | Straightforward | **93% ✅** |
| **Advanced Dashboards** | 25 hrs | MEDIUM | Streamlit performance | **90% ⚠️** |
| **Phase 2C Total** | **105 hrs** | **MEDIUM** | — | — | **85% ✅** |

**Gate 4 Success Criteria (Jan 15):**
- ✅ Greeks: 10+ sensitivities, <30 sec compute
- ✅ Attribution: Obligor/sector/geographic breaks
- ✅ Dashboards: 4+ pages live, UAT passed

**Go-Live Risk:** MEDIUM-LOW | **DEFERRABLE**: If time-constrained, defer Phase 2C to Q2 2027 (still exam-ready)

---

## RESOURCE FEASIBILITY

### Capacity Check: Do We Have Enough People?

**Available Capacity:**
- 1.0 FTE × 30 weeks = 1,200 hours available
- Phase 2 scope = 294 hours estimated (24.5% utilization) ✅

**Reality Adjustment:**
- Typical project actuals: +25–40% overrun
- Revised estimate: 360–410 hours (30–34% utilization) ✅ **Still feasible**

**If Constrained (0.7 FTE only):**
- Available: 840 hours
- Phase 2 needs: 360–410 hours (43–49%)
- **Action:** Defer Phase 2C analytics → 240 hours remaining for Phase 2A + 2B ✅ Exam-ready still achievable

---

## RISK REGISTER & MITIGATION

### Red Risks (Stop Work if Not Mitigated)

| Risk | Probability | Impact | Mitigation | Owner |
|------|-----------|--------|-----------|-------|
| **ESG data unavailable** | 20% | HIGH | Use conservative assumptions; defer calibration to Jul 2026 | Risk Analytics |
| **Resources pulled for urgent ops** | 30% | HIGH | Executive blocking: CRO commits 1.0 FTE protection | CRO |
| **Regulatory exam moved to Oct 2026** | 10% | HIGH | Deliver Phase 2A ONLY by Oct (trace = exam-ready) | Model Risk |
| **Market data feed instability** | 15% | MEDIUM | Use internal benchmarks for scenarios; fallback to 2007-09 data | Data Ops |

### Yellow Risks (Actively Manage)

| Risk | Probability | Impact | Mitigation | Owner |
|------|-----------|--------|-----------|-------|
| **Greeks API numerical stability** | 25% | MEDIUM | Use robust differentiation; cache results; test edge cases | Quants |
| **Scope creep** | 40% | MEDIUM | Enforce weekly gates; parking lot for Phase 3 | Project Manager |
| **ESG guidance changes (Jun 2026)** | 30% | MEDIUM | Build as configuration; rapid recalibration window 1–2 weeks | Risk Analytics |
| **Phase 2A trace overhead > 5%** | 15% | MEDIUM | Selective tracing; 10% sample audit trail in production | Lead Developer |

### Green Risks (Monitor)

| Risk | Probability | Impact | Mitigation | Owner |
|------|-----------|--------|-----------|-------|
| **Minor code bugs in Phase 2A** | 70% | LOW | Comprehensive unit tests; code review; staged rollout | Dev Lead |
| **Dashboard performance lag** | 50% | LOW | Data pre-aggregation; StreamLit caching; paginated results | UI Developer |

---

## CONTINGENCY PLAN TRIGGERS

### Trigger 1: Phase 2A Not Complete by Aug 1 (→ Slip >1 week)

**Response:**
1. Investigate root cause (resource issue? technical blocker?)
2. Decision: Compress Phase 2B timeline OR extend overall to Feb 2027
3. Exam-readiness still achievable (Phase 2A is the critical piece)

**Probability:** 15% | **Preparedness:** Well-prepared (Phase 2A is low-risk)

---

### Trigger 2: ESG Data Becomes Available Only in August (Instead of June)

**Response:**
1. Use **simplified 0.5% fixed uplift** for ESG in Phase 2B (Week 16)
2. Gate 3 (Oct 1): Swap in data-driven calibration
3. Complete by Oct 15

**Probability:** 20% | **Impact:** +2 weeks, absorbed in Phase 2B slack

---

### Trigger 3: Greeks API Technical Issues Prevent 95%+ Coverage

**Response:**
1. Deliver **simplified Greeks** (Delta + Gamma only; defer Vega/Curvature to Phase 3)
2. Reduces Greeks effort from 60 → 40 hours
3. Phase 2C timeline absorbs impact (deliver Week 28 instead of 29)

**Probability:** 25% | **Preparedness:** Pre-planned contingency

---

### Trigger 4: Regulatory Exam Moved to December 2026

**Response:**
1. **Accelerate Phase 2A** to Week 6 (parallel tracking + governance)
2. **Deliver stripped-down Phase 2B** by Nov 30:
   - ✅ Dynamic floor (critical)
   - ✅ Leverage ratio (quick)
   - ❌ ESG detailed (stub only)
   - ✅ Scenarios (2007-09 baseline)
3. **Defer Phase 2C** to 2027 Q1
4. Exam-ready status: **ACHIEVED** (Phase 2A + core 2B = trace + governance + floor)

**Probability:** 10% | **Preparedness:** Pre-defined acceleration plan

---

## STEERING COMMITTEE DECISION TEMPLATE

### MOTION FOR APPROVAL

**Title:** Approve PROMETHEUS Phase 2 Implementation Plan

**Proposed Decision:**

The Steering Committee **authorizes** commencement of PROMETHEUS Phase 2 enhancements, contingent upon the following conditions:

1. **Budget:** Approve $56,272 investment ($35.3K dev + $8K audit + $3K training + $2K infra + $7.9K contingency)

2. **Resources:** Confirm 1.0 FTE team allocation (30 weeks) with protection from other project demands:
   - Lead Developer/Quant: 30% FTE
   - Risk Analytics: 25% FTE
   - Data Engineer: 20% FTE
   - UI/Reporting: 15% FTE
   - Model Risk (part-time): 10% FTE

3. **Timeline:** Target implementation Jan 15, 2027 (30-week delivery)
   - Phase 2A: Weeks 1–7 (Foundation)
   - Phase 2B: Weeks 8–17 (Regulatory)
   - Phase 2C: Weeks 18–29 (Analytics)

4. **Governance:** Establish Weekly Steering Committee meetings with 4 decision gates:
   - Gate 1 (May 1): Executive approval + resource confirmation
   - Gate 2 (Aug 1): Phase 2A completion + go/no-go Phase 2B
   - Gate 3 (Oct 1): Phase 2B validation + ESG sign-off
   - Gate 4 (Jan 15): Phase 2C rollout or phased delivery

5. **Contingency Plan:** Authorize deferral of Phase 2C (Analytics) to Q2 2027 if resources/timeline constrained; Phase 2A + 2B (exam-readiness) is non-deferrable

6. **Success Metrics:**
   - Phase 2A: 100% RWA traceability, 5 automated governance checks live
   - Phase 2B: 50–100 bps capital efficiency, 5+ scenario library, ESG PD uplift calibrated
   - Phase 2C: Greeks API (10+ sensitivities), RWA attribution (50+ obligors), 4+ dashboards
   - Audit-ready: Exam team can review full calculation traces in <1 day

**Expected Benefits:**
- ✅ Regulatory exam readiness (Q2 2027)
- ✅ 50–100 bps capital efficiency ($2.5M freed capital)
- ✅ Best-in-class risk governance framework
- ✅ Industry-leading open-source model positioning
- ✅ 5-year NPV: $14.3M (ROI: 4,961%)

**Risks & Mitigations:** [Reference contingency plan above]

**Vote:**
- [ ] **APPROVE** — Proceed with Phase 2 as proposed
- [ ] **APPROVE WITH MODIFICATIONS** — [Specify changes]
- [ ] **DEFER** — Request additional analysis [Specify area]

---

## SIGN-OFF

| Role | Name | Signature | Date |
|------|------|-----------|------|
| **Chief Risk Officer** | | | |
| **Head of Technology** | | | |
| **Head of Model Risk** | | | |

---

## NEXT STEPS IF APPROVED

### Immediate (Within 1 Week)

1. **Nominate Lead Developer** for Phase 2 (critical-path resource)
2. **Confirm 1.0 FTE availability** with department heads
3. **Schedule Phase 2A kickoff** (May 1 detailed planning session)
4. **Create GitHub project board** with issue tracking

### May 1 Steering Committee

1. **Review Phase 2A charter** (detailed week-by-week plan)
2. **Confirm resource assignment** (intro lead dev, risk lead, data lead)
3. **Set weekly meeting cadence** (Thursdays, 30 min sync)
4. **Establish communication protocol** (escalation, blockers, decisions)

### May 6 Development Kickoff

1. Create feature branches: `feature/audit-trace`, `feature/gov-checks`, `feature/dq-dashboard`
2. Set up test database environment
3. Initial architecture review
4. Weekly standup schedule

---

## FAQ FOR STEERING COMMITTEE

**Q: Is 294 hours realistic?**
A: Conservative estimate; likely 360–410 with contingency. Still <35% of 1.0 FTE capacity. ✅

**Q: What if we lose the developer to another project?**
A: Phase 2 timeline slips to Feb/Mar, but audit-ready still achievable (Phase 2A is 70% of value). Recommend CRO blocking commitment.

**Q: Can we defer Phase 2C?**
A: Yes, without impacting exam readiness. Phase 2A + 2B = audit-ready by Jan 2027; Phase 2C (analytics) is "nice-to-have" for competitive advantage.

**Q: What's the biggest risk?**
A: ESG data availability (80% likely ready by Jul 2026). Mitigation: use conservative assumptions if delayed.

**Q: When do we get capital relief?**
A: Dynamic floor goes live Oct 2026 (shadow run); 50–100 bps benefit realized by year-end.

**Q: What if regulatory exam moves up to Nov 2026?**
A: Still achievable. Deliver Phase 2A by Sep 30 + stripped-down Phase 2B by Nov 30 (exam-ready).

---

**Document Prepared By:** Strategic Planning + Feasibility Assessment  
**Distribution:** Steering Committee, CRO, Development Leadership  
**Classification:** Confidential


