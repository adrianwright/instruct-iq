# Instruct IQ N0 capability discovery

Owner: Platform. Evidence date: 2026-10-15.
Status: bounded discovery complete; deployment readiness **not established**.

## Boundaries and result

Only authenticated read operations were performed. No cloud resource was created
or changed, including `rg-instruct-iq`. No capacity resume, workspace creation,
deployment, seeding, consent, role assignment, provider registration, account or
default-subscription change occurred. Existing demos were not modified.

Reuse of the existing user-designated `<approved-fabric-capacity>` Fabric capacity is already approved;
no further reuse approval is requested. Its actual ARM name is normalized without
the display punctuation. The single matching Fabric API entry has an
`azureResourceId` exactly equal to the discovered ARM resource ID, not merely a
similar name. Capacity remains in its existing resource group.

Environment-specific subscription names, subscription/tenant/object/capacity IDs,
resource-group names other than the requested new group, and complete responses
are retained only under ignored `.local\instruct-iq-discovery\`.
No secret `.env` files, keys, certificates, or access-token output were read.
`az rest` acquired its own authorization internally; no tokens were printed or
persisted by the discovery scripts.

## Verified versus unverified

| Area | Actual evidence | Limitation / remaining dependency |
|---|---|---|
| Current Azure identity | `az account show` verified default subscription ID, name, tenant, Enabled state and user identity type. Final read matched subscription/name/tenant. | This is the current default, **not** an explicit Instruct IQ deployment selection. |
| Accessible subscriptions | `az account list` returned four Enabled subscriptions across two tenants. Explicit per-subscription Fabric and group-existence reads succeeded for all four without switching defaults. | Cached subscription enumeration plus successful scoped reads; not an exhaustive tenant inventory or proof of rights to every resource. |
| Approved capacity | Exactly one ARM Fabric capacity candidate matched the normalized approved name, in the default subscription and tenant; direct ARM detail read succeeded. Fabric API returned an exact ARM-ID-linked entry. | No other capacity is approved for reuse. |
| Capacity region / SKU / state | ARM: Central US, F16, provisioning Succeeded, state Paused. Fabric API: Central US, F16, state Inactive. | It is **not currently running**. No resume was attempted or authorized in N0. |
| Fabric data-plane read | `GET https://api.fabric.microsoft.com/v1/capacities` succeeded using existing CLI authorization in the capacity's subscription context; two capacities were visible, one exact approved-resource match. | Proves capacity-list access only. Does not prove workspace creation, assignment to capacity, Lakehouse/ontology/Data Agent creation or query permission, service-principal tenant settings, backend identity compatibility, or licensing/preview eligibility. |
| ARM permissions | Effective-permissions reads succeeded at subscription and capacity scope and included an unrestricted `actions: ["*"]` block. Caller-specific inherited/direct assignment queries returned Owner, User Access Administrator and Key Vault Secrets User; no assignment conditions in these returned records. | ARM roles do not imply Fabric roles or Foundry/Search data-plane access. No wildcard data-action block was returned. Role listing did not expand group membership or prove future identities' permissions. Deny assignments, policy and service-specific gates can still constrain future writes. |
| Capacity headroom | A bounded Azure Monitor metric-definitions read returned HTTP BadRequest: `Microsoft.Fabric/capacities is not a supported platform metric namespace`. | **Unverified**, not zero and not spare F16 capacity. No utilization/overload/CU headroom measurement, Fabric Capacity Metrics app access, contention assessment or workload compatibility test was obtained. |
| New RG name | `az group exists --name rg-instruct-iq --subscription <each accessible subscription>` returned false in all four. | Point-in-time noncollision is not reservation or target-subscription selection. Any later create must recheck and must not repurpose an existing group. |
| Providers | All eleven checked namespaces are Registered in the capacity/default subscription: Microsoft.Fabric, Microsoft.CognitiveServices, Microsoft.Search, Microsoft.Storage, Microsoft.ManagedIdentity, Microsoft.KeyVault, Microsoft.App, Microsoft.ContainerRegistry, Microsoft.Web, Microsoft.OperationalInsights, Microsoft.Insights. | This registration evidence applies only to that candidate subscription. It is not resource creation, policy, regional availability, quota or billing authorization. |
| Foundry management API | Provider metadata advertises Cognitive Services `accounts`, `accounts/projects`, `locations/models`, `locations/usages` in Central US, including management API `2025-06-01`. Regional model-catalogue GET succeeded. | No new Foundry parent/project exists or was selected. Agent API, project connections, model deployment, retrieval compatibility, network access and managed-identity permissions remain untested. |
| Model quota | Central US usage GET succeeded with 258 usage rows. GlobalStandard gpt-5.5: current 850, limit 1000; GlobalStandard text-embedding-3-large: current 150, limit 1000. Both report unit `Count`. | Arithmetic unallocated units: 150 and 850 respectively; **do not label these as TPM** without model/SKU conversion. Quota is subscription + region + model/SKU specific, not a reservation or real-time deployment-capacity guarantee. No final models/SKUs/versions/allocations have been selected. |
| Model catalogue | Candidate Central US catalogue includes gpt-5.5 version 2026-04-24 and text-embedding-3-large version 1, with GlobalStandard and DataZoneStandard advertised. | Catalogue visibility and quota do not prove instantaneous capacity, target model eligibility, residency suitability or successful deployment. Other catalogue entries were not exhaustively evaluated. |
| Search regional quota | Central US service-usage GET succeeded: Free 0/1; Basic 2/12; Standard 0/12. Standard2, Standard3 and storage-optimized L1/L2 limits were zero. Other advertised tiers were captured privately. | Counts are service counts, not Search units, replicas, partitions, index/vector limits or knowledge-base feature eligibility. Do not choose Free/Basic merely because quota exists. |
| Search API | Provider metadata advertises Central US Search service management APIs, including stable `2025-05-01`; that version successfully read regional usage. | The repository's **data-plane** `2026-05-01-preview` knowledge-source/knowledge-base/retrieve API is a separate requirement, not proven by ARM API metadata. No new endpoint exists to test it; no existing demo Search endpoint was repurposed. |
| Application / optional integrations | Existing identity/configuration/provisioning mechanisms inspected read-only. | Dedicated app registrations, accepted audiences/scopes, managed identity, tenant choice, browser sign-in, backend provider flow, Work OBO/certificate/consent and optional Web entitlement remain unverified. No existing identity or certificate is approved for reuse. |

Central US was probed **only because it is the observed capacity region**. It has
not been selected as the region for all new Azure services. GlobalStandard model
catalogue/quota evidence is not a data-residency approval. No region sweep,
tenant-wide principal scan, existing Search/Foundry content query or paid model
invocation was performed.

## RG decision: planned, not created

The exact missing deployment decision is:

> Confirm the intended Instruct IQ subscription and tenant (the discovered
> capacity/default subscription is a candidate, not an approved target), the
> `rg-instruct-iq` metadata location, and the allowed service-region/residency
> matrix for Foundry/models, Search, storage and application hosting.

The plan names the new group and approves capacity reuse, but neither the plan,
directives nor nonsecret infrastructure parameters unambiguously select those
coordinates. Legacy provisioning defaults to East US 2 in one script, while the
capacity is in Central US; neither establishes the intended new-resource
location. Therefore the narrow conditional RG-create exception did **not** apply.
Name was checked read-only before this decision. No capacity-reuse approval is
missing. All future noncapacity Azure resources must use the new dedicated group;
the future new Fabric workspace must use only the verified approved capacity.
Later paid resources/deployment/seeding still require separate authorization.

## Repository mechanism implications for G0 / N1

Inspected `infra\main.bicep`, parameters, `azure.yaml`, modules and hooks;
`agent\provisioning\isv\` Fabric, ontology/OneLake, Foundry/Search and M365
provisioners; and backend `config.py`, `fabric_client.py`, `fabric_status.py`,
`isv_sources.py`, auth and related provider mechanisms. No provisioner was run.

- Existing Bicep is commercial-demo infrastructure, not ready-to-run Instruct IQ
  IaC. It references an existing Search service across groups and existing vault
  secrets, and does not create the required new Foundry/Search/Storage stack.
  Do not point it at existing demo resources or simply change its names.
- Existing hosting modules cover Container Apps, ACR, Static Web Apps, monitoring,
  managed identity and Key Vault. Existing public role constants are useful
  mechanisms, **not** evidence that a future identity has those assignments.
- The capacity-status configuration currently shares the application's
  subscription setting. N1 must separate capacity coordinates from new-resource
  coordinates if deployment targets a different subscription.
- Fabric retrieval uses `https://api.fabric.microsoft.com/.default` and a
  workspace/Data Agent MCP endpoint. Seeding additionally uses Fabric REST and
  OneLake. Capacity-list success cannot satisfy those workspace/item/API checks.
- Foundry IQ in the existing source implementation is Search knowledge-base
  retrieval (`POST /knowledgebases/{name}/retrieve`) with
  `https://search.azure.com/.default` and preview `2026-05-01-preview`.
  Provisioning expects an AIServices parent, chat and embedding deployments,
  Blob storage and Search identity permissions. Validate the exact selected
  retrieval path and Search-to-model authorization before committing contracts.
- Existing scripts can switch defaults, write roles/resources/items, fetch
  account keys, seed M365, and publish agents. They were read, not invoked.
  N1 must build explicit-target, isolated utilities instead of executing them.
- Existing Work integration requires a dedicated confidential registration and
  OBO permission path; optional Web has distinct endpoint/entitlement or Search
  knowledge-base requirements. CLI capacity access proves none of these.
- New workspace creation/assignment, active-capacity availability and measured
  shared headroom, dedicated application identity and provider grants, and
  preview/API validation against new resources are explicit live prerequisites,
  not development-test assumptions.

## Commands, status and time

All times below are UTC on 2026-10-15. Environment values in commands are
placeholders; exact commands, scoped identifiers, start/end timestamps and
nonsecret output are in local evidence records.

| Evidence record / command family | Time (UTC) | Result |
|---|---|---|
| Mandatory Foundry skill dependency script `<skills-directory>\microsoft-foundry\scripts\check-and-setup-dependencies.ps1` | First operation after skill load, before references/probes; exact second not captured | Exit 0; dependencies ready: azd and microsoft.foundry extension. No subsequent azd command. |
| `default-account.json`: `az account show --query <nonsecret selected fields>` | Before subscription list / capacity probes; exact start retained locally | Exit 0 |
| `subscriptions.json`: `az account list --query <subscription fields>` | Before 15:45:39; completion retained locally, start not separately captured | Exit 0 |
| `capacity-list-1..4`: `az rest GET /subscriptions/<sub>/providers/Microsoft.Fabric/capacities?api-version=2023-11-01` | 15:45:39–15:46:14, interleaved with name checks | All four exit 0 |
| `rg-collision-1..4`: `az group exists --subscription <sub> --name rg-instruct-iq` | 15:45:43–15:46:19, interleaved with capacity reads | All four exit 0; false |
| `capacity-detail`: ARM GET approved capacity, API `2023-11-01` | 15:47:01–15:47:05 | Exit 0 |
| `subscription-permissions`, `capacity-permissions`: ARM GET `<scope>/providers/Microsoft.Authorization/permissions?api-version=2022-04-01` | 15:47:05–15:47:13 | Both exit 0 |
| `current-user-object`: `az ad signed-in-user show --query {id:id}` | 15:47:13–15:47:17 | Exit 0; current user only |
| `subscription-direct-roles`, `capacity-direct-roles`: `az role assignment list --assignee-object-id <caller> --scope <scope> --include-inherited --fill-principal-name false` | 15:47:17–15:47:43 | Both exit 0 |
| `fabric-capacities`: `az rest --subscription <capacity-sub> --resource https://api.fabric.microsoft.com --method get --url https://api.fabric.microsoft.com/v1/capacities` | 15:47:43–15:47:52 | Exit 0; no consent/tenant error |
| `provider-metadata`: `az provider list --subscription <candidate> --query <selected namespaces/types>` | 15:47:52–15:48:07 | Exit 0 |
| `cognitive-quota-centralus`: ARM GET CognitiveServices `locations/centralus/usages?api-version=2023-05-01` | 15:48:07–15:48:14 | Exit 0 |
| `cognitive-models-centralus`: ARM GET CognitiveServices `locations/centralus/models?api-version=2025-06-01` with selected model query | 15:48:14–15:48:21 | Exit 0 |
| `default-account-after`: selected `az account show` | 15:48:21–15:48:26 | Exit 0 |
| `search-quota-centralus`: ARM GET Search `locations/centralus/usages?api-version=2025-05-01` | 15:49:13–15:49:20 | Exit 0 |
| `insights-provider`: `az provider show --namespace Microsoft.Insights --subscription <candidate>` | 15:49:20–15:49:27 | Exit 0; namespace response uses lowercase `microsoft.insights` |
| `capacity-metric-definitions`: ARM GET `<capacity>/providers/microsoft.insights/metricDefinitions?api-version=2018-01-01` | 15:49:27–15:49:34 | Exit 1 / BadRequest, unsupported namespace; **not an authorization denial** |
| `default-account-final`: selected `az account show` | 15:49:34–15:49:39 | Exit 0; unchanged |
| `capacity-linkage`: ARM GET approved capacity with properties, API `2023-11-01` | 15:50:20–15:50:26 | Exit 0; exact Fabric `azureResourceId` linkage independently checked |

The Foundry skill's `quota\quota.md` and `rbac\rbac.md` were read before the
related probes. Foundry MCP is unavailable; the skill's Azure CLI management-plane
fallback was used. No install/provision workflow was entered.

## Durable evidence and next gate

- `.local\instruct-iq-discovery\default-account.json`, `subscriptions.json`:
  scoped account evidence (identifiers private).
- `.local\instruct-iq-discovery\evidence\*.json`: command/status/time/output,
  including the nonauthorization monitoring error.
- `.local\instruct-iq-discovery\resolved-coordinates.json`,
  `approved-capacity-candidate.json`: capacity coordinates and current default;
  these are observations, not authorized deployment selections.
- `.local\instruct-iq-discovery\command-index.json`, `verification.json`:
  execution index, exact ARM/Fabric linkage and unchanged-default checks.

G0 may review capability-aware contracts now; N0 is not evidence of live
integration readiness. N1 remains gated on G0. N2 requires explicit target
coordinates and deployment/cost authorization. Live capacity, headroom,
workspace/item permissions, dedicated identities and query-ready ingestion must
be verified before S1/G1 can pass.
