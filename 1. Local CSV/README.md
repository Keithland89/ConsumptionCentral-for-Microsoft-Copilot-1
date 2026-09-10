# 1. Local CSV

**The quickest way to see it working.** Download your exports, put them in a folder, open the
template.

Works with Power BI Pro — no Fabric capacity needed.

---

## You only need one product

Cowork, Copilot Studio, GitHub Copilot, Azure AI Foundry — **bring whichever you have**. Missing
products just leave their pages empty.

---

## Three steps

### 1. Make a folder

Anywhere. `C:\Consumption Central\Data` is fine.

### 2. Put your exports in it

| Product | Where to get it |
|---|---|
| **Cowork / Work IQ** | Viva Insights → Analysis → build a query → download CSV |
| **Copilot Studio** | Power Platform admin centre → Licensing → Copilot Studio |
| **GitHub Copilot** | GitHub → Billing → AI usage report |
| **Azure AI Foundry** | Azure Cost Analysis → export, or run [`pull_azure_ai.py`](pull_azure_ai.py) |

File names don't have to match exactly — the template recognises the usual variations.

**[Full click-paths and permissions →](../docs/DATA-SOURCES.md)**

### 3. Open the template

Open **`Consumption Central - Local CSV.pbit`**, paste your folder path into `DataFolder`, click
**Load**.

That's it.

---

## Try it with sample data first

The **[sample-data](sample-data/)** folder holds a synthetic dataset covering all four products.
Point `DataFolder` at it and the whole report fills in — no exports needed, no real data involved.

Worth doing before you go hunting for your own files.

---

## What you'll be asked for

| | |
|---|---|
| **`DataFolder`** | Your folder path — the only one that matters |
| Everything else | Has a sensible default. Leave it |

<details>
<summary>The optional ones, if your pricing differs</summary>

| | Default | Change it when |
|---|---|---|
| `CreditRate` | $0.01 | Your agreement isn't list price |
| `PrepaidCreditRate` | $0.008 | You bought credits up front |
| `PrepaidCreditBalance` | 0 | You have a prepaid balance |
| `GitHubBusinessSeatPrice` | $19 | Your GitHub pricing differs |
| `GitHubEnterpriseSeatPrice` | $39 | As above |
| `BillingPeriodWeeks` | 4 | Your billing period isn't monthly |

**[Where to find your real rates →](../docs/COMMERCIAL-TERMS.md)**

</details>

---

## Department breakdowns

If your Viva query includes department or job title, they appear automatically.

If it doesn't, add them to the query in Viva Insights and re-run — that's easier than supplying a
separate file.

**[More on org data →](../docs/ORG-DATA.md)**

---

## When you outgrow this

Local CSV is a storage format, not a requirement to download Azure data manually.
Use the automation below, or **[2. Fabric](../2.%20Fabric/)** to collect directly into
Lakehouse tables. Check each ingester's retention behavior: Azure replaces a rolling window.

## Automate Azure collection

The same procedure also feeds **Viva Direct's optional Azure pages**. It does not run inside
Power BI; schedule the collector first, then refresh the semantic model only on success.

### 1. Prepare a runner and read-only Azure access

Install a supported Python 3 and [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli)
on a machine that can reach Azure and write to the report's `DataFolder`.
The collector uses the Python standard library and Azure CLI.

For the first interactive run, use `az login --tenant <tenant-id>`, then select the subscription
with `az account set --subscription <subscription-id>`. Grant the collecting identity
**Cost Management Reader** on the subscription and **Monitoring Reader** on the AI resources.
Resource/tag and deployment discovery also requires resource read permissions; **Reader**
on the subscription is a straightforward read-only setup. Billing-agreement charge visibility
may require an additional administrator setting; see
[Cost Management access](https://learn.microsoft.com/en-us/azure/cost-management-billing/costs/assign-access-acm-data).

For unattended runs, authenticate **as the scheduled job's identity**, not your personal
interactive login. Prefer `az login --identity` on an Azure host with a configured managed
identity, or a properly secured
[service-principal certificate login](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-service-principal).
Give that identity the Azure roles above and local folder write access. Do not put secrets
in a task's arguments, notebook, source control or logs. Personal cached logins can expire
or require MFA and are not a reliable unattended authentication design.

### 2. Run once and inspect the outputs

From the repository root, after authentication:

```powershell
python ".\1. Local CSV\pull_azure_ai.py" "C:\Consumption Central\Data" --subscription "<subscription-id>" --days 7
if ($LASTEXITCODE -ne 0) { throw "Azure collection failed; do not refresh Power BI." }
```

Replace `<subscription-id>` with the subscription UUID. `--days` accepts 1-90 complete UTC
days before today (default 90). After accepting the first short run, choose the desired
rolling window. The original `python pull_azure_ai.py <folder>` command still works;
without `--subscription` it uses the current Azure CLI account subscription.
Run `python ".\1. Local CSV\pull_azure_ai.py" --help` for the command reference.

Keep the folder dedicated to the selected subscription. Do not mix sample Azure files,
old renamed copies or output from another subscription into the same folder.

| File | Shipped template usage |
|---|---|
| `AzureAiSpendDaily.csv` | Resource/meter daily cost and billing quantities |
| `AzureAiTokensDaily.csv` | Daily Monitor token/request/utilisation metrics |
| `AzureAiDeployments.csv` | Inventory export only; **not loaded** by the shipped templates |

Use the canonical names. Both Local CSV and Viva Direct find the first eligible file by
filename pattern, folder depth and modification date; these two Azure readers do not union
every matching file. Put the current outputs directly in `DataFolder`.

Set `DataFolder` in the template and refresh in Desktop. Compare the selected dates and
currency with Azure, and follow the [acceptance checks](../docs/TESTING.md#azure-automation-acceptance).
Read the [shipped model's unit, currency and service limitations](../docs/DATA-SOURCES.md#important-limits-of-the-shipped-azure-page)
before treating cost-per-million as a reconciled billing metric.

### 3. Schedule collection and then report refresh

Use Windows Task Scheduler or your existing job runner. Configure a daily job under the
identity tested above; use absolute executable/script/output paths, an explicit subscription,
and a non-overlap policy. Authenticate in that run context before launching the collector.
Record exit status and output freshness; configure bounded retry/backoff for transient failures.
Collection failure must block downstream report refresh, not masquerade as an empty source.
The collector retries recognized transient CLI failures four times with 2/4/8-second
backoff. Azure CLI does not reliably expose `Retry-After` to it; a longer throttle fails
the job. Configure bounded runner-level retries with a longer delay rather than repeatedly
restarting immediately. Authentication and validation errors are not retried.

The output files form one collection batch. Avoid refresh while files are being published:
per-file replacement is not a transaction across the whole batch. After any interrupted
publication, rerun collection successfully before refreshing.
All queries must succeed before publication begins. A successful empty result writes
headers rather than retaining stale rows. Real numeric zero metrics are kept; missing
telemetry is not converted to zero. Equivalent current/legacy metric aliases are not
collected together, and deployment dimensions are retained where advertised.

Power BI Desktop does not provide unattended refresh of an open local report.
For Power BI Service, publish the model and configure an
[on-premises data gateway](https://learn.microsoft.com/en-us/power-bi/connect-data/service-gateway-onprem)
on an always-on machine that can access the **same folder path**. Configure its data-source
credentials and permissions; the gateway identity must be able to read the files.
A OneDrive-synced local folder is still a local filesystem source, not a cloud connection.
Viva Direct additionally needs its separate Viva cloud credentials.

Trigger semantic-model refresh after successful collection using your orchestrator, or allow
adequate time between separate schedules and monitor both jobs. Clock ordering alone is not
a success dependency. Refresh frequency and availability depend on your Power BI licence.
