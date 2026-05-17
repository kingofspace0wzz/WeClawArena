# Shared Account Policy (FAM-A)

## Membership

- Primary holder: harriet (the hub). Approves anything above caps.
- Spoke members: sara, theo, uma. They cannot transact directly; only the hub commits actions on the shared account.

## Spending caps

- Single-line-item cap: $500. Above that, harriet's primary authorization (this file's last section) must be cited in the aggregation_log before the order can be committed.
- Per-cycle aggregate cap: $1500. If the sum of spoke requests exceeds this, split into two cycles or seek primary approval.

## Payment methods

- Default for shared-account orders: `pm_harriet_visa_01`.
- Other payment methods on the hub workspace are for hub-only purchases; they are not part of the shared-account default.

## Refund routing

- Refunds always return to the original payment method, never to a different method, regardless of which spoke initiated the return.

## Primary approval

- For amounts above the single-line-item cap, cite `FAM-A-HARRIET-APPROVAL-4D7B` in the aggregation_log entry.
