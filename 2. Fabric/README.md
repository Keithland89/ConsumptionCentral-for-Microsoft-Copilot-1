# 2. Fabric

**Set it up once, then it refreshes itself.** Data lands in a Lakehouse; the report reads it on a
schedule.

Needs a workspace on a capacity that supports Fabric notebooks and Lakehouses
(for example, Fabric F capacity or an eligible trial); **PPU alone is not Fabric capacity**.
Only have Power BI Pro?
Use **[1. Local CSV](../1.%20Local%20CSV/)**.

---

## Why bother

The Viva Insights export only reaches back **6 months**. Every week you don't capture is gone.

This path accumulates history in a table that outlives the export window — a year from now you have
a year of trend, not the same rolling six months.

---

## You only need one product

Load Cowork alone and its pages work. Studio only, or GitHub only — same. **Skip the notebooks for
products you don't have.**

---

## Setup

### 1. Create a Lakehouse

Fabric portal → your workspace → **New** → **Lakehouse**.

### 2. Import the notebooks

**Viva does not need one.** It has a certified **Dataflow Gen2** connector that writes query
results straight into your Lakehouse on a schedule — see [The Viva half needs no
notebook](#the-viva-half-needs-no-notebook) below. Set that up instead of
`Ingest_Viva_Consumption`, which exists as a fallback for downloaded CSVs.

For everything else: **[notebooks/](notebooks/)** — one per product. Import the ones you need, set
the workspace and Lakehouse at the top of each, run.

| Notebook | Reads | Writes |
|---|---|---|
| `Ingest_GitHub_API` | GitHub REST API | `github_*` |
| `Ingest_Azure_AI` | Azure Cost Management + Monitor | `azure_ai_spend`, `azure_ai_tokens` |
| `Ingest_CommercialTerms` | Azure Cost Management | `commercial_terms` |
| `Ingest_Studio` | Power Platform exports | `studio_*` |
| `Ingest_Org` | Entra export | `org_attributes` |
| `Ingest_Viva_Consumption` | *Fallback only* — Viva CSV export | `viva_credits_weekly`, `viva_spending_policy` |

**[Where each export comes from →](../docs/DATA-SOURCES.md)**


### 2b. Azure AI Foundry tables *(optional)*

The Foundry page reads two tables. Both are optional — leave them out and the page is simply empty,
which is a supported state, not a failure.

| Table | From | Columns |
|-------|------|---------|
| `azure_ai_spend` | Cost Management Query API | `UsageDate`, `ServiceName`, `MeterCategory`, `Meter`, `ResourceId`, `ResourceName`, `ResourceGroup`, `Cost`, `UsageQuantity`, `Currency`, `DepartmentTag` |
| `azure_ai_tokens` | Azure Monitor metrics | `Date`, `ResourceName`, `ResourceGroup`, `Deployment`, `Metric`, `Value` |

Use [`Ingest_Azure_AI.ipynb`](notebooks/Ingest_Azure_AI.ipynb) for both tables without manual
exports. It reads one subscription and overwrites a rolling window of **1–90 complete UTC days**
(`DAYS = 90` by default), not an accumulating archive. Keep these tables dedicated to that
subscription: independent runs for different subscriptions would replace each other's data.
A Cost Management export to storage is another automated source, but needs transformation to
this schema and does not contain Azure Monitor metrics.

The shipped Fabric template reads these exact **`dbo` tables**, not views, through
`Sql.Database(FabricSQLEndpoint, LakehouseName)`. Its readers match the canonical columns
above and derive model/token direction from `Meter`; `ResourceId` and `MeterCategory`
are not retained in the model. Missing tables are optional, but connection/authentication
failures still need fixing. The existing template does not load deployment inventory
or the expanded Azure prototype's three feeds.
Read the [unit/currency/service limitations](../docs/DATA-SOURCES.md#important-limits-of-the-shipped-azure-page)
and complete the [acceptance checks](../docs/TESTING.md#azure-automation-acceptance).

#### Authentication and permissions

The notebook does **not** automatically run as a managed identity. Microsoft's
[NotebookUtils credentials documentation](https://learn.microsoft.com/en-us/fabric/data-engineering/notebookutils/notebookutils-credentials)
lists `storage`, `pbi`, `keyvault`, and `kusto` audiences, **not ARM**. Do not rely on
`notebookutils.credentials.getToken("https://management.azure.com/")`, a `pbi` token for ARM,
or an implicit `DefaultAzureCredential` chain in Fabric.

This notebook instead uses an explicit Entra application's **client-credentials** token with
scope `https://management.azure.com/.default`, following Microsoft's
[Azure Monitor authentication guidance](https://learn.microsoft.com/en-us/azure/azure-monitor/platform/rest-api-walkthrough)
and [OAuth protocol documentation](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-client-creds-grant-flow).
It renews the token before expiry. No additional authentication package is required.

1. Register an Entra application in the subscription's tenant. Store its client secret **value**
   in Azure Key Vault; never paste it into notebook code, parameters, logs, or source control.
   Assign **Cost Management Reader** at subscription scope and **Monitoring Reader** on the
   AI accounts. Subscription-wide inventory/tag discovery also needs resource read access:
   **Reader** at subscription scope is a straightforward read-only setup (overlapping read
   roles can instead be replaced with reviewed least-privilege custom permissions).
   Cost visibility still depends on the billing agreement's charge policies, including EA
   **AO view charges** or MCA **Azure charges** where applicable; see
   [Cost Management access](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/assign-access-acm-data).
2. Give the **notebook execution identity** permission to read that Key Vault secret
   (for example, Key Vault Secrets User with Azure RBAC, or secret **Get** under access policies).
   It separately needs permission to run the notebook and write to the Lakehouse
   (workspace Contributor is a common setup). The ARM application and execution identity
   are distinct: assigning Azure roles to one does not grant the other's access.
3. Import the notebook and attach/pin the intended Lakehouse as its default. Set
   `SUBSCRIPTION_ID`, `TENANT_ID`, `CLIENT_ID`, `KEY_VAULT_URL`, `CLIENT_SECRET_NAME`, and `DAYS`.
   Leave the shipped table names unchanged. Ensure Fabric can reach Key Vault, Entra login,
   and ARM endpoints under your network policy. Rotate the stored credential before expiry.
4. Run interactively once, then validate the **actual scheduled/pipeline identity**.
   [Fabric documents](https://learn.microsoft.com/en-us/fabric/data-engineering/how-to-use-notebook)
   interactive runs under the current user, notebook schedules under the schedule creator/last
   updater, and default pipeline runs under the pipeline's last modifying user.
   A [Notebook activity connection](https://learn.microsoft.com/en-us/fabric/data-factory/notebook-activity)
   can explicitly select another supported identity, including a configured workspace identity.
   Workspace identity requires its documented tenant/workspace setup; merely enabling one does
   not switch existing runs or make an ARM `getToken` audience available. Verify secret retrieval
   and Lakehouse writes in the selected run context, not just your interactive session.

#### Collection and refresh behavior

- Cost queries follow every continuation URL using POST with the same body and each page's column
  metadata. They use at most two aggregation/grouping clauses: discover service/category pairs,
  then query meter/resource detail per pair. Missing aggregations, malformed rows and duplicate
  daily grains fail instead of becoming zero spend. Currencies remain separate.
- Monitor queries use only the shipped metric families and advertised definitions. Counters request
  `Total`, provisioned utilisation requests `Average`. One name per equivalent family is preferred
  (new names before legacy names); `TotalTokens` is used only if neither input nor output is
  available. `TotalCalls` is not used on OpenAI-kind accounts. These different metrics must not
  be summed indiscriminately.
- Queries use daily UTC buckets in at most 30-day windows. Where available, the deployment
  dimension is requested and other dimensions are aggregated by Azure; otherwise `Deployment`
  stays blank for resource-level data. There is no additional resource-total row alongside
  deployment rows and no local summing/averaging of utilisation. Unexpected dimension splits,
  changed time grains, duplicate points, or reaching the explicit series limit fail visibly.
- Numeric zero points are retained. Null/missing telemetry is omitted, not converted to zero or
  described as proof of no traffic. HTTP, authentication and per-metric errors propagate. A
  successful empty collection replaces old rows with empty, explicitly typed tables.
- All Azure reads and validation finish before writes begin. The two Delta overwrites are
  individually atomic, **not a cross-table transaction**; a second-write failure can leave a
  mixed snapshot. Retry the entire notebook and gate report refresh on whole-run success.
  ARM throttling and transient 502/503/504 responses retry the same request up to five attempts,
  honoring `Retry-After` and Cost Management retry headers without replaying prior pages.
  Delays over 300 seconds defer the job with an error; exhausted retries also fail visibly.
  Configure bounded pipeline retries/backoff for those failures and avoid overlapping runs.
  Costs can arrive late or be revised; later rolling-window runs pick up those changes.

### 3. Get the SQL connection string

Lakehouse → **Settings** → **SQL analytics endpoint** → copy it.

### 4. Open the template

Open **`Consumption Central - Fabric.pbit`** and paste in:

| | |
|---|---|
| **`FabricSQLEndpoint`** | The string you just copied |
| **`LakehouseName`** | Your Lakehouse name |

Everything else has a default.

### 5. Publish and schedule

Publish to your workspace, then schedule **ingestion before semantic-model refresh**.
For Azure, use a Fabric pipeline Notebook activity to run `Ingest_Azure_AI`; only its **success**
dependency should trigger refresh. Verify both tables are visible through the SQL analytics
endpoint before the first refresh. Do not refresh on notebook failure or overlap writers.
If using separate schedules, leave time for ingestion and SQL endpoint synchronization and
monitor failures; clock ordering alone is not a success dependency.

**Tuesday morning** works well for Viva — after its weekend refresh and the Dataflow Gen2 load.
A daily Azure ingestion schedule can run independently, with refresh after all required sources
for that refresh have completed. A Power BI refresh alone does not call Azure or run notebooks.

---

## Try it with sample data first

**[seed_sample_data.py](seed_sample_data.py)** loads the synthetic dataset straight into your
Lakehouse — no exports, no waiting.

```
pip install pandas deltalake requests
az login --tenant <your-tenant>
python seed_sample_data.py --workspace <guid> --lakehouse <guid>
```

Both GUIDs are in the Fabric portal URL with the Lakehouse open. It only touches the Consumption
Central tables.

---

## The Viva half needs no notebook

Viva Insights ships a certified **Dataflow Gen2** connector that writes query results straight into a
Lakehouse on a schedule — no download, no notebook. **This is the preferred route on this path.**

1. Viva Insights → **Analysis** → build a query with the Copilot credit metrics → **Analysis
   results** → your query → the **link icon**. Copy the **Partition identifier** and **Query
   identifier**.
2. Fabric workspace → **New** → **Dataflow Gen2** → **Get data** → search *Viva Insights* under
   **Online Services**.
3. Paste both identifiers. Leave *Query Name* blank. Under **Advanced options** set **Schema Type =
   Pivoted** and **Data Granularity = Row-level data**. Authenticate with an **Organizational
   account**.
4. Set the Lakehouse as the data destination, then schedule the refresh for **Tuesday ~8am PST** —
   after Viva's weekend refresh.

> Leaving *Query Name* blank only works against a **custom query**, which returns a single table.
> Identifiers taken from the Consumption Dashboard's own export point at a multi-table result and
> need a table name supplied, which is why the credit query has to be one you built in Analysis.

> **Also turn on auto-refresh for the query itself**, in Viva Insights → Analysis results. Without
> it the Dataflow refreshes happily against a result that never changes — which looks exactly like
> everything working.

`Ingest_Viva_Consumption` remains for working from downloaded CSVs, or when Dataflow Gen2 capacity
cost is not worth it.

**[Microsoft's guide →](https://learn.microsoft.com/en-us/viva/insights/advanced/analyst/export-query-data-microsoft-fabric)**

---

## Reference

| | |
|---|---|
| [Table contracts](docs/DATA-DICTIONARY.md) | Every table and column the model expects |
| [Automating the landing step](flows/) | Power Automate, if you'd rather not use notebooks |
