# 3. Viva Direct

**Consumption connects straight to Viva Insights.** Organisation breakdowns also need a
directory CSV when the query output does not supply the employee attributes.

---

## Two things to paste

In Viva Insights:

1. **Analysis** → build a query with the Copilot credit metrics → turn on **Auto-refresh**
2. **Analysis results** → your query → the **link icon**
3. Copy the two identifiers

Open **`Consumption Central - Viva Direct.pbit`**, paste them in, click **Load**.

| | |
|---|---|
| **`VivaPartitionId`** | Partition identifier |
| **`VivaQueryId`** | Query identifier |

> **Leave the GitHub Copilot credit metric out of the query.** Including it makes the query itself
> fail in Viva Insights, before Power BI is involved at all. Take GitHub usage from the GitHub
> export instead — drop `GitHubAiUsage` and `GitHubUserMap` in your `DataFolder` and the GitHub
> pages work exactly as they do on the other paths.

> **Not the Consumption Dashboard's "Connect data" dialog.** That one also hands out a partition and
> query identifier, which is why it gets used by mistake — but it points at the dashboard's own
> multi-table result, and this template sends no table name. Build your own query under **Analysis**
> and take the identifiers from **Analysis results**.

**For identified-user reporting, plan to supply a directory CSV as part of setup.**
Put `entra_org.csv` in a folder and set `DataFolder` to that folder. Include
`UserPrincipalName` and the employee attributes you want to group by, such as
`Department`, `Organisation` and `JobTitle`. The identities must match the consumption data.

You can leave `DataFolder` blank for consumption-only reporting, or when the actual Viva
output already contains the required org attributes. Selecting attributes in the query UI
does not prove that the connector returns them. Leave pricing parameters at their defaults.

---

## Policy names need one file

The connector gives you the policy **id** and the **limits**, but not the policy **name**. Verified
name by name against a live tenant: of everything the CSV download contains, only `PeopleHistorical`
answers over the API. The policy table does not.

So a policy with no name available is labelled by its id — `Policy f1a2bfe2 — name not in export` —
rather than called *(Unassigned)*, which would be untrue: the policy **is** assigned, its name just
is not readable over the connector.

**To get the real names**, download the CSV export of the same query — Viva Insights → **Analysis
results** → your query → **Download** — and drop **`M365SpendingPolicyMetaData.csv`** into your
`DataFolder`. Nothing else from that ZIP is needed. The names appear on the next refresh.

*(Only `(Unassigned)` proper remains: the all-zero id, which marks usage recorded outside any policy
window.)*

---

## Only the custom query is supported

The connector can read two shapes, and this template targets the **custom query** you build under
Analysis. That shape returns a single table, so no table name is ever sent and there is no parameter
to get wrong.

The Consumption Dashboard's own result is multi-table and needs its export name supplied with the
request. The dialog never shows you that name, so the parameter was unanswerable in practice and has
been removed. If that is all you have, build a custom query instead — it takes a couple of minutes
and gives you better data, because you choose the spending-policy and employee attributes that ride
along on the rows.

**[Full connector reference →](../docs/VIVA-CONNECTOR.md)**

---

## Department breakdowns

**Check the returned columns, not just the query settings.** With user identification enabled,
do not assume Department, Organisation or other HR fields will be returned alongside UPNs.
Use the separate directory CSV as the standard setup unless the required values are confirmed
in the actual output. Domain and Population Type alone do not provide department breakdowns.

Without user identification, selected employee attributes may be available from Viva. This is
not yet verified as a general rule: compare the identified and de-identified outputs before
relying on a query-only setup. Do not change identification or privacy settings solely as a
workaround without confirming that the resulting identity and reporting behavior is suitable.

**Organisation is separate from Department.** Both `Organisation` and `Organization` map to
the **Organisation** grouping; selecting both Department and Organisation in the query keeps
both attributes. Custom employee attributes are retained too.

A query-only setup needs no org file **only when the source supplies the attributes and
resolvable identities**. A `PersonId`, Entra/AAD object id or `PeopleHistoricalId` can identify
a person; it cannot manufacture missing HR attributes. Identity keys are trimmed and case-normalised.
Repeated rows are reconciled before calculating usage intensity; conflicting explicit person
ids produce a `VivaIdentityConflict` refresh error rather than silently double-counting.
An identity-free consumption row produces `VivaMissingIdentity`.

People with no org values remain in **Usage Intensity (Cowork)**. For a populated attribute,
missing values appear as **(Not set)**. Attributes populated for less than 5% of the combined
population are hidden unless none clear that threshold. Buckets describe the loaded billing
period snapshot; changing a report period does not recalculate their membership.

When attributes do arrive with consumption, the template uses them. Missing source attributes
require enrichment; refreshing the same query cannot create them.

<details>
<summary>Supplying the directory CSV</summary>

Drop a directory export from the Microsoft Entra admin centre (Users → Download users) into your
`DataFolder`. Where both sources describe a person, the directory wins per nonblank attribute
and Viva fills its gaps. A shared UPN or person/object identifier is required to match a file
to consumption; the template cannot infer a link between unrelated identifiers.

**[More on org data →](../docs/ORG-DATA.md)**

</details>

---

## Adding the other products

Optional. Set **`DataFolder`** to a folder holding whatever exports you have and drop the files in —
they're found by name, so nothing needs renaming and anything you don't have is skipped.

| Product | Files it looks for |
|---|---|
| Copilot Studio | `StudioTenantDaily`, `StudioPerAgent`, `StudioPerUser` |
| GitHub Copilot | `GitHubAiUsage`, `GitHubUserMap` |
| Azure AI Foundry | `AzureAiSpendDaily`, `AzureAiTokensDaily` |
| Org attributes | `entra` / `orgdata` / `users` — required for org breakdowns when Viva omits the attributes |

Leave `DataFolder` blank only if no file enrichment is needed. Cowork consumption works without
it, but department breakdowns require attributes from Viva or the directory CSV. Other product
pages remain empty when their exports are not supplied.

> Azure AI Foundry files live in `DataFolder` alongside everything else. The separate
> `AzureAiSpendCsvPath` / `AzureAiTokensCsvPath` parameters have been removed — one product having
> its own path parameters while the other three were found by name was inconsistent, and the folder
> lookup already handles them.

**[Where to get each one →](../docs/DATA-SOURCES.md)**

---

## If the refresh fails

**`(500) Internal Server Error`** means the connector was asked for a multi-table export without a
table name. This template only issues single-table custom-query requests, so if you see it, check
that `VivaPartitionId` and `VivaQueryId` point at a **custom query** built in Analysis rather than at
a Consumption Dashboard export.

**[Connector detail and what was tested →](../docs/VIVA-CONNECTOR.md)**

---

## Offline regression and rebuild

From the repository root, using Python 3.12 and no additional packages:

```powershell
python -B docs\scripts\check_viva_query_org.py
python -B docs\scripts\fix_viva_query_org.py --dry-run
```

The shipped Viva template already contains the fix. The patcher can also reproduce it from
the `ee6927c` Viva template; running without `--dry-run` writes it back. It refuses unknown
source versions. Editable M sources live beside it in `docs\scripts\viva_query_org`.
Only `DataModelSchema` and `UnappliedChanges` (including cached formulas) change. This export
has **no DataMashup part**; a package containing one is rejected, not partially patched.

These checks cover package/source contracts and synthetic Python reference fixtures, **not
execution of M or DAX**. Complete the query-only refresh checks in
[TEST-PROCEDURE.md](TEST-PROCEDURE.md) before distributing a tenant-validated build.

---

## Worth knowing

Microsoft ships its own Power BI template from the same dialog. It covers Cowork consumption with
first-party support.

This is a different proposition: four products in one report, with cost, optimisation and forecast
across all of them. Download both and see which you'd rather have.
