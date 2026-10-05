# Refund Reconciliation and Control Opportunity

**To:** Arjun Mehta, Finance Controller  
**From:** Vireo Audio Support Analysis  
**Date:** 5 October 2026  
**Subject:** Why the refund export does not reconcile, and where to investigate next

## The number to use

The raw export contains 12,238 rows and sums to **₹230,124,081** when every value in `refund_amount_inr` is added as if it were comparable. That is not a valid cash-refund total: the export includes 638 migration re-import rows and mixes current rupees with larger legacy-native values.

After retaining one authoritative row per ticket ID and converting the retained `legacy_fd` amounts by 100, the dataset records **₹6,709,932 in refunds across 2,340 tickets** from January 2025 through June 2026. That is an average of **₹1,118,322 per observed quarter**, consistent in scale with the helpdesk's approximate ₹11 lakh quarterly report. The 100x conversion is supported by all 125 duplicate pairs that have amounts in both systems; the policy itself does not name the legacy unit.

## What is driving the recorded value

`GW-OTHER` is the largest reason-code bucket: **₹2,907,036 across 991 tickets**, or 43.3% of normalized refund value. The policy defines this as “Goodwill / Other”; it is not a clean goodwill measure. The next largest buckets are `RETURN-QC-OK` at ₹1,181,386 and `DUP-PAYMENT` at ₹884,586.

The dashboard breaks monthly refunds down by reason and resolving agent. Treat those agent figures as workload context, not a league table: Returns Desk is expected to process many refunds, and the policy says Tier 2 work should not be compared with Tier 1 by volume. Ticket exports alone do not establish why a decision was made or whether it was avoidable.

## Control opportunity

There are **166 tickets** with both a positive refund and a replacement flag. Their recorded refund component is ₹574,191; policy planning cost for replacement hardware and shipping is ₹296,970. Together, **₹871,161 is a candidate exposure over 18 months**, not confirmed loss: eight records have no usable order ID, and the pack contains no dispatch, settlement, or approval ledger.

A practical first goal is to **reduce these recorded refund-plus-replacement flags from 166 to about 125 per comparable 18-month period**. If the same average candidate exposure per case holds, that corresponds to reducing candidate exposure from ₹871,161 to about ₹653,371, or approximately **₹36,298 per quarter** across the six observed quarters. This is a control target to validate, not booked savings.

Separately, 879 `GW-OTHER` refunds exceed ₹500. The policy cap applies to goodwill credits, but this dropdown also means “Other,” and approval records were not supplied. These require reason and approval review before they can be called violations. The SLA calculation finds 1,060 first-response misses; 998 are resolved or closed, implying ₹349,300 in policy-derived credits. Actual credit issuance also needs Finance's ledger.

## Recommended next step

Reconcile the duplicate and legacy conversion rule with IT; then have Finance and Operations inspect the 166 refund-plus-replacement tickets against payment and shipment records, starting with the eight without order IDs. In parallel, classify the high-value `GW-OTHER` cases and match SLA misses to actual credit transactions. Only book leakage after those checks establish a real, preventable outflow.
