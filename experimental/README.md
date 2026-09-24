# Experimental: Power Platform API for Copilot Studio

**This is not a setup step.** Every path in this repo still loads Copilot Studio
data from the manual admin-centre export described in its own README. Nothing
here is required, and nothing here is supported yet.

This folder exists so the API work is visible and reviewable while it is still
being tested, rather than sitting in a branch.

## What it would replace

`StudioTenantDaily.csv` and `StudioPerAgent.csv` are downloaded by hand today.
The licensing API can produce both, and it carries a **daily** grain the export
does not have — the export is a month-to-date aggregate, so day-level trend is
lost before the template ever sees it.

`StudioPerUser.csv` has no API route at all and stays manual regardless.

## Status

Tested against a live tenant on 2026-09-24.

| Endpoint | Result |
|---|---|
| `GET /licensing/entitlements` | Works |
| `GET /licensing/entitlements/MCSMessages` | Works — tenant capacity totals |
| `GET /licensing/billingPolicies` | Works |
| `GET /environmentmanagement/environments` | Works |
| `GET /licensing/entitlements/MCSMessages/resources` | **403, empty body** |

That last row is the one `pull_studio.py` depends on for per-day, per-agent
figures. Until it is resolved, this script cannot complete a run.

### What the 403 is not

Worth recording, because each of these looks like the obvious answer:

- **Not the role.** The calling account was Global Administrator.
- **Not the scope.** A dedicated app registration was granted
  `Licensing.Allocations.Read`, `Licensing.BillingPolicies.Read` and
  `CopilotStudio.Licenses.Read`, admin-consented, and all three were confirmed
  present in the issued token. Still 403.
- **Not the URL.** Unknown routes on this service return a clean
  `404 RouteNotFound`. This one returns 403, so the route exists and is
  refusing.
- **Not a missing parameter.** The request matched a known-working
  implementation character for character, `includeFields` included.

The tenant used was a Microsoft demo tenant reporting `consumed.value = 0` —
no Copilot Studio credits had ever been used — so it may simply not serve this
route. That has not been confirmed either way. **If you get this working, or
get a different result, please open an issue.**

## The response contract

Two things about this API are not in the [public reference][ref], and both are
silent failures rather than errors.

**1. The envelope is nested.** The reference describes a flat `value[]`.
A tenant actually returns:

```json
{
  "value": [ { "resources": [ { "resourceId": "...", "consumed": 0 } ] } ],
  "continuationtoken": ""
}
```

Read it as flat and you get the group objects instead of rows, and every column
comes out blank without an error.

**2. `includeFields` is required for the per-agent detail.** Without
`includeFields=users,tags,asOfDate`, the rich `metadata` block is not returned
at all.

The metadata keys are PascalCase and are not documented anywhere:

| Metadata key | Column |
|---|---|
| `ResourceName` | Agent Name |
| `NonBillableQuantity` | Non-billed credit |
| `Users` | (user count) |
| `ChannelId` | Channel |
| `FeatureName` | AI Feature/Billable Feature |
| `ToolInvoked` | Tool Used |
| `LLMModel` | LLM Model |
| `KnowledgeSources` | Knowledge Sources |

The tenant entitlement response is nested too — `entitlement.capacity.entitled.value`,
not a flat `entitled`. A tenant that buys capacity by allocation reports
`entitled: 0` with the real figure under `allocated`, so read both.

Credit for all of the above goes to
[PetrosFeleskouras/copilot-credit-consumption][community], which verified this
contract against a real tenant and documented it properly. The contract is
pinned by tests in `docs/scripts/test_pull_studio.py` so it cannot quietly
regress to the documented-but-wrong shape.

### Harness detail

Agents built on the **GitHub Copilot harness** report `FeatureName` as
`Process Agent` for every row, and return no tool, model or knowledge-source
values. That is an upstream telemetry limit, not a collection bug — blank
dimensions there should not be read as missing data.

## Scheduling

There is no application role for licensing on this API. The Power Platform API
publishes exactly one app role, `CopilotStudio.Copilots.Invoke`, and every
`Licensing.*` permission is delegated-only.

So **this cannot run unattended as a service principal.** It needs a signed-in
administrator, which rules out an unattended Fabric or scheduled-task refresh
and is why the working community implementation uses Power Automate with a
delegated connection owned by an admin.

## Running it

```bash
az login
python pull_studio.py "C:\Data\ConsumptionCentral"
python pull_studio.py "C:\Data\ConsumptionCentral" --days 90
```

It takes the same folder your chosen path already reads, and writes the two
CSVs with the exact headers the templates expect. It never accepts credentials,
validates everything before publishing, and replaces files atomically, so a
failed run leaves your last good data untouched.

Expect it to fail at the 403 above.

[ref]: https://learn.microsoft.com/rest/api/power-platform/licensing/entitlement-insight/get-tenant-resources-across-environments
[community]: https://github.com/PetrosFeleskouras/copilot-credit-consumption
