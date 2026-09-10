<div align="center">

# 💳 Consumption Central

### *for Microsoft Copilot* — one Power BI template for **Copilot credit consumption and cost**

[![Built by Microsoft](https://img.shields.io/badge/BUILT_BY-MICROSOFT-4F73B8?style=for-the-badge&labelColor=1F1F1F)](https://microsoft.com)
[![Power BI Template](https://img.shields.io/badge/POWER_BI-TEMPLATE-F2C811?style=for-the-badge&logo=powerbi&logoColor=black&labelColor=1F1F1F)](https://powerbi.microsoft.com)

**What you're consuming · what it costs · where to trim · what next year looks like**

![Consumption Central](Images/ConsumptionCentral-Preview.gif)

</div>

## Watch first

Both play here in the page — no download.

**Demo — what the report covers, page by page** *(1m 51s)*

https://github.com/user-attachments/assets/702d94f7-74fc-43ad-a259-d00695f76a9c

**Setup guide — getting your own data in, every source, start to finish** *(10m 49s)*

https://github.com/user-attachments/assets/480af64f-53ab-4f4c-b5d2-6f35546fdcfb

---

## What is it

A Power BI report covering Copilot spend across **Cowork/Work IQ**, **Copilot Studio**,
**GitHub Copilot** and **Azure AI Foundry**.

Fifteen pages: each product gets consumption, cost, optimisation and forecast, plus a combined
overview.

---

## You don't need all of it

> ### **No product is required. One is enough.**

Load whatever you have. The rest of the pages come up empty and nothing breaks.

| I have… | I get |
|---|---|
| **One product** | That product's four pages |
| **Two or more** | Those, plus the combined overview |

Department breakdowns are optional too. Without them you still get every credit and cost figure —
you just can't split them by team.

---

## One admin setting connects everything

> ### **Without it, each product is an island.**

Viva Insights ships Copilot data **de-identified by default** — the person arrives as a hashed
`PersonId`, not an email address. Every other source (Copilot Studio, GitHub Copilot, your Entra
export) is keyed on **UserPrincipalName**. So until identification is on, there is nothing to join
them with.

| | Cowork / Work IQ totals | Per-person view across products | Department breakdowns |
|---|---|---|---|
| **De-identified** *(default)* | ✅ Correct | ❌ | ❌ |
| **Identified** | ✅ Correct | ✅ | ✅ |

**Turning it on** — a **Global Administrator** or **AI Administrator**, about two minutes:

1. [Microsoft 365 admin center](https://admin.cloud.microsoft/?#/viva/featureAccessManagement) →
   **Settings → Viva → Feature access management**
2. **Create a policy** — App **Viva Insights**, Feature **Identification**
3. Access **On**, applied to everyone or to a named analyst group
4. Allow **up to 24 hours** to take effect

Then re-run your export, or point the connector at the identified query.
**[Full steps and the two query names →](docs/DATA-SOURCES.md#identified-vs-de-identified)**

**Before you switch it on:** this processes personal data. Check whether per-person reporting needs
works-council consent or employee notification where you operate — your organisation is the data
controller, not Microsoft. The Power BI connector also **does not enforce Viva's minimum group
size**, so any privacy threshold you rely on has to be applied in the report yourself.

---

## Pick a path

| | Best when | Setup |
|---|---|---|
| **[1. Local CSV](1.%20Local%20CSV/)** | You want to see it working today | ~10 minutes |
| **[2. Fabric](2.%20Fabric/)** | You want it refreshing weekly on its own | An afternoon |
| **[3. Viva Direct](3.%20Viva%20Direct/)** | You want Cowork data with no files at all | ~10 minutes |

**Not sure?** Start with **Local CSV**. It tells you whether the numbers are worth automating before
you automate anything.

Each folder has its own short guide with the exact steps.

**Azure can be automated on all three paths.** Schedule the Python collector for Local CSV
and Viva Direct, or the Azure notebook for Fabric, then refresh the report after ingestion
succeeds. No manual Azure export is required. Start with the
[Azure automation and template compatibility guide](docs/DATA-SOURCES.md#automated-setup-and-template-compatibility).
The current templates read the existing spend/metrics feeds, not the expanded Azure prototype.
If the recorded walkthrough differs, use these written setup instructions.

---

## Two things you'll be asked for

When the template opens it asks for a few values. Almost all have sensible defaults — these are the
two worth thinking about:

| | |
|---|---|
| **Where your data is** | A folder path, a Lakehouse name, or two IDs from Viva — depends on your path |
| **What a credit costs you** | List price is **$0.01**. Change it only if your agreement differs |

Everything else can stay as it is.

---

## Try it before you commit

Every path ships with a **synthetic sample dataset**. Point the template at it and the whole report
fills in — no exports, no waiting for a billing cycle, no real data.

**[1. Local CSV/sample-data](1.%20Local%20CSV/sample-data/)**

### Narrated walkthroughs

Both are at the [top of this page](#watch-first) and play inline.

- **Demo** *(1m 51s)* — a tour of the fifteen pages and what each one answers.
- **Setup guide** *(10m 49s)* — every data source: which ones automate, which need a download, and the admin consent Viva needs before it will name a user. Then the Fabric path in full — the notebooks, the permission grants, and the Dataflow Gen2 route for Viva.

---

## More detail, when you want it

| | |
|---|---|
| **[How to read the dashboard](docs/INTERPRETING.md)** | **What every page and figure means — start here if a number looks odd** |
| [Where the data comes from](docs/DATA-SOURCES.md) | Click-paths and permissions for every export |
| [Department breakdowns](docs/ORG-DATA.md) | How org attributes get in, and what happens without them |
| [Rates and pricing](docs/COMMERCIAL-TERMS.md) | What to set and where to find it |
| [Every measure explained](docs/MEASURES.md) | Reference — for when a number surprises you |

---

## Status

Built and tested end to end against live tenant data on all three paths. The sample dataset is
synthetic; no customer data is in this repo.

That historical report validation is **not** a live-tenant certification of the revised Azure
collectors or your scheduled identity/gateway. Complete the
[Azure acceptance procedure](docs/TESTING.md#azure-automation-acceptance) in your environment.

Not supported through Microsoft support channels — **[open an issue](../../issues)** instead.

<details>
<summary><strong>Usage &amp; compliance</strong></summary>

This template helps you understand your own Copilot consumption and cost. Microsoft has no
visibility into the data you load, nor control over how the template is used. You are responsible
for ensuring your use complies with applicable law, including data privacy and employment law.
Microsoft disclaims all liability arising from use of this template.

Several underlying exports are **in preview**, and the identifiable variant of the Viva Insights
export processes personal data. Review the "Previews" section of the Microsoft Products and Services
Data Protection Addendum before enabling it, and consult your works council or privacy office where
per-person reporting requires it.

</details>

---

## Contributing

Issues and pull requests welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of
Microsoft trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of third-party trademarks or logos is subject to those third-parties' policies.
