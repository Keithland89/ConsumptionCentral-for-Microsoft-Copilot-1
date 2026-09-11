# Testing the Viva Insights connector — ten minutes

The one open question on this path: **does the certified Viva Insights connector expose Consumption
Dashboard credit data, or only Analyst Workbench collaboration queries?**

This page makes that test decisive. Follow it, record the outcome in the table at the bottom, and
open an issue either way — a firm answer helps everyone.

---

## What you need

- **Viva Insights Analyst** role
- Power BI Desktop, December 2022 or newer
- A query in Viva Insights whose results you believe contain credit consumption

---

## Step 1 — Get the identifiers

1. Open the Viva Insights web app → **Analysis results**
2. Find the query whose results you want
3. Click the **Link** icon next to it
4. Copy both:
   - **Partition Identifier**
   - **Query Identifiers**

> If the Link icon is absent, the query has not finished, or its results are not exposed to the
> connector. That is itself a finding — note it.

## Step 2 — Connect

Power BI Desktop → **Get Data** → **Online Services** → **Viva Insights** → **Connect** → **Continue**

| Field | Value |
|---|---|
| Partition Identifier | *(from step 1)* |
| Query Name | **leave blank** |
| Query Identifiers | *(from step 1)* |
| **Advanced** → Schema type | **Pivoted** — Unpivoted is no longer supported |
| **Advanced** → Data granularity | **Row-level data** — Aggregated is no longer supported |
| **Advanced** → Table name | only for multi-table queries |
| Data Connectivity mode | **Import** — DirectQuery is no longer supported |

Get any of the three Advanced settings wrong and the connector may load something that looks
plausible but is not row-level. Check them before clicking Load.

## Step 3 — Read the column list

**Do not click Load yet.** The Navigator preview is enough to answer the question.

### ✅ It works — you see something like

| Column | Or |
|---|---|
| `PersonId` | `UserPrincipalName` |
| `ServiceName` | values `Cowork`, `Work IQ API` |
| `SpendingPolicyId` | |
| `MetricDate` | |
| `Total Copilot Credits used` | any credits column |
| `Spending policy limit` | `User limit` |

Any two or three of those together means the connector carries consumption data. **That is the good
outcome** — this becomes the best of the three paths: no files, no notebooks, native scheduled
refresh.

### ❌ It does not — you see only

`Meeting_hours`, `Email_hours`, `After_hours_collaboration`, `Internal_network_size`,
`Focus_hours`, `Chats_sent`, `Collaboration_hours`…

Collaboration metrics with **no credits, no spending policy, no service name** means the connector
covers Analyst Workbench queries only and this path is a dead end for Consumption Central. Use
**[2. Fabric](../2.%20Fabric/)** for automation, or **[1. Local CSV](../1.%20Local%20CSV/)** to get
going today.

### 🤔 Ambiguous

Credit-ish columns but not the ones above — capture the **full column list** and put it in the issue.
A different-but-usable shape is worth adapting the template for.

---

## Step 4 — If it worked, check the grain

Load it and run this in a blank query to confirm it is row-level rather than pre-aggregated:

```
EVALUATE
ROW(
    "rows",        COUNTROWS( 'YourVivaTable' ),
    "people",      DISTINCTCOUNT( 'YourVivaTable'[PersonId] ),
    "dates",       DISTINCTCOUNT( 'YourVivaTable'[MetricDate] ),
    "earliest",    MIN( 'YourVivaTable'[MetricDate] ),
    "latest",      MAX( 'YourVivaTable'[MetricDate] ),
    "credits",     SUM( 'YourVivaTable'[Total Copilot Credits used] )
)
```

Two things to check:

**Is it row-level?** `rows` should be roughly `people × dates`. If `rows` equals `people`, or equals
`dates`, you have an aggregate and the Advanced settings did not take.

**Does it go back further than the download?** The file export gives 6 months weekly. If the
connector reaches further, that is a significant advantage — it would remove the main reason to run
the Fabric path at all.

**Cross-check against a file export** covering the same window. The totals should match. If they do
not, say so in the issue — a silent discrepancy between two Microsoft surfaces is worth knowing
about.

---

## Step 5 — Record it

| | |
|---|---|
| Date tested | |
| Tenant type | production / demo |
| Identifiable export enabled? | yes / no |
| Link icon present? | yes / no |
| **Credit columns present?** | **yes / no** |
| Columns seen | *(paste the list)* |
| Row-level confirmed? | yes / no |
| History depth | *(earliest → latest)* |
| Matches file export? | yes / no / not checked |

Please [open an issue](../../issues) with this table filled in, whichever way it went. A confirmed
"no" is as useful as a "yes" — it stops the next person spending an afternoon on it.

---

## If it works, what happens next

We build a proper `.pbit` for this path with the connector wired in, and the folder gets a real
README instead of a caveat.

The model needs no changes: the loader already normalises whatever person key it is given, so
connector output would be wired in exactly like the CSV path. It is the connection, not the model,
that is in question.

---

## One thing to be aware of either way

The connector **does not enforce Viva Insights privacy rules**, including minimum group size. It
returns raw row-level data.

> *"The connector doesn't enforce privacy rules, including Minimum group size."*
> — [Viva Insights Power BI connector](https://learn.microsoft.com/en-us/viva/insights/advanced/analyst/power-bi-connector),
> checked 2026-04-25

Consumption Central shows per-person consumption deliberately — that is what a chargeback report is for — but
check whether per-person reporting needs works-council consultation or similar where you operate
before publishing it.
# Query-only org regression

**Precondition:** inspect the source output for populated employee attributes and a usable
identity key. A query with only consumption, Domain and PopulationType is not expected to
produce Department/Organisation. For identified-user reporting without those attributes,
test the standard directory-CSV setup instead.

Compare otherwise equivalent identified and de-identified queries to establish which fields
each returns. Record missing columns, populated coverage and usable identity keys separately.
Do not treat the identification setting alone as proof that org fields are available.

For the Viva Direct template, verify these checks in a **fresh Desktop import** with only
`VivaPartitionId` and `VivaQueryId` configured and no directory file. Offline source/package
checks alone do not prove a successful Desktop refresh.

1. Use a custom consumption query with Department and Organisation employee attributes.
   Both should appear separately in Group By; `Organization` is also accepted as Organisation.
2. Refresh with a PersonId/AAD-only query, then an identifiable UPN query if available.
   Org keys, CoworkBilling keys and CreditsWeekly keys must agree. No identity may occur in
   multiple Cowork intensity buckets. Repeated weeks must not multiply people.
3. Compare ungrouped credits with summed Department, Organisation and Usage Intensity (Cowork)
   groups. Missing attributes belong in `(Not set)`; the totals must agree. Membership is
   calculated at refresh, not dynamically for a slicer-selected period.
4. Remove employee attributes from the query. Consumption and intensity must still work.
   A real populated attribute is normally offered only at 5% coverage; when no attributes
   meet that threshold, any populated attribute remains eligible.
5. Add a synthetic optional org file with mixed-case/whitespace keys, an extra attribute,
   a directory-only person and a blank attribute. Directory nonblank values win; Viva fills
   gaps; directory-only people remain. AAD-to-UPN matching requires a shared identifier.
6. Confirm all report pages still render and optional Studio/GitHub/Foundry pages remain empty
   rather than failing. Check that no pending query changes appear on opening.
7. With only Domain/PopulationType inline and Department/Organisation in PeopleHistorical,
   confirm historical attributes still appear. Inline nonblank attributes take precedence;
   historical values fill blanks, and a nonblank optional directory value overrides both.
   A historical row must share a resolvable identifier with consumption; unmatched HR rows
   must not be assigned to the one person with usage.

Do not commit tenant data, identifiers, exports or screenshots from this verification.

---
