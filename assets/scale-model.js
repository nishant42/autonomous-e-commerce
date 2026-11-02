/* Scale plan cost model: one source for every number on scale.html.
   Currency: GBP. Every unit price comes from an official source (see SRC):
   - Azure: Microsoft's Retail Prices API (prices.azure.com), UK South, retrieved 17 Oct 2026, in USD,
     converted at FX = 0.755, the ratio in Microsoft's own GBP price list for the same meters.
   - Other vendors: their own pricing pages, retrieved 17 Oct 2026.
   Quantities (how much we run) are engineering sizing decisions and are shown next to each line.
   Inputs the reader controls live in CFG. */
(function (root) {
  const FX = 0.755;                 // USD -> GBP, implied by Microsoft's GBP price list
  const HOURS = 730, SEC = 730 * 3600;
  const usd = (x) => x * FX;

  const SRC = {
    aca: { label: "Azure Container Apps pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/container-apps/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Azure%20Container%20Apps%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20vCPU%20Active%20Usage%27%20or%20meterName%20eq%20%27Standard%20vCPU%20Idle%20Usage%27%20or%20meterName%20eq%20%27Standard%20Memory%20Active%20Usage%27%20or%20meterName%20eq%20%27Standard%20Memory%20Idle%20Usage%27%20or%20meterName%20eq%20%27Standard%20Requests%27%20or%20meterName%20eq%20%27Dedicated%20vCPU%20Usage%27%20or%20meterName%20eq%20%27Dedicated%20Memory%20Usage%27%20or%20meterName%20eq%20%27Dedicated%20Plan%20Management%27%29" },
    pg: { label: "Azure Database for PostgreSQL Flexible Server pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/postgresql/flexible-server/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20%28%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flexible%20Server%20Burstable%20BS%20Series%20Compute%27%20and%20skuName%20eq%20%27B1MS%27%29%20or%20%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flexible%20Server%20General%20Purpose%20Ddsv5%20Series%20Compute%27%20and%20%28skuName%20eq%20%272%20vCore%27%20or%20skuName%20eq%20%274%20vCore%27%20or%20skuName%20eq%20%278%20vCore%27%29%29%20or%20%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flex%20Server%20Storage%27%20and%20meterName%20eq%20%27Storage%20Data%20Stored%27%29%29" },
    sb: { label: "Azure Service Bus pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/service-bus/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Service%20Bus%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20skuName%20eq%20%27Standard%27%20and%20%28%28meterName%20eq%20%27Standard%20Base%20Unit%27%20and%20unitOfMeasure%20eq%20%271/Month%27%29%20or%20meterName%20eq%20%27Standard%20Messaging%20Operations%27%29" },
    sbp: { label: "Azure Service Bus pricing (Premium)", url: "https://azure.microsoft.com/en-gb/pricing/details/service-bus/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Service%20Bus%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20meterName%20eq%20%27Premium%20Messaging%20Unit%27" },
    kv: { label: "Azure Key Vault pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/key-vault/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Key%20Vault%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20skuName%20eq%20%27Standard%27%20and%20meterName%20eq%20%27Operations%27" },
    la: { label: "Azure Monitor (Log Analytics) pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/monitor/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Log%20Analytics%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20meterName%20eq%20%27Analytics%20Logs%20Data%20Ingestion%27" },
    blob: { label: "Azure Blob Storage pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/storage/blobs/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27General%20Block%20Blob%20v2%27%20and%20meterName%20eq%20%27Hot%20LRS%20Data%20Stored%27%20and%20tierMinimumUnits%20eq%200" },
    acr: { label: "Azure Container Registry pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/container-registry/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Container%20Registry%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Basic%20Registry%20Unit%27%20or%20meterName%20eq%20%27Standard%20Registry%20Unit%27%20or%20meterName%20eq%20%27Premium%20Registry%20Unit%27%29" },
    dns: { label: "Azure DNS pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/dns/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Azure%20DNS%27%20and%20meterName%20eq%20%27Public%20Zone%27%20and%20armRegionName%20eq%20%27Zone%201%27" },
    appcfg: { label: "Azure App Configuration pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/app-configuration/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27App%20Configuration%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20Instance%27%20or%20meterName%20eq%20%27Standard%20Replica%20Instance%27%29" },
    fd: { label: "Azure Front Door pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/frontdoor/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Azure%20Front%20Door%27%20and%20contains%28meterName%2C%27Base%20Fees%27%29%20and%20armRegionName%20eq%20%27Zone%201%27" },
    redis: { label: "Azure Managed Redis pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/managed-redis/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Azure%20Managed%20Redis%20-%20Balanced%27%20and%20%28meterName%20eq%20%27B1%20Cache%20Instance%27%20or%20meterName%20eq%20%27B5%20Cache%20Instance%27%29" },
    defender: { label: "Microsoft Defender for Cloud pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/defender-for-cloud/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Microsoft%20Defender%20for%20Containers%27%20and%20skuName%20eq%20%27Standard%20vCore%27" },
    egress: { label: "Azure Bandwidth pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/bandwidth/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Bandwidth%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Rtn%20Preference%3A%20MGN%27%20and%20meterName%20eq%20%27Standard%20Data%20Transfer%20Out%27%20and%20%28tierMinimumUnits%20eq%200%20or%20tierMinimumUnits%20eq%20100%29" },
    pe: { label: "Azure Private Link pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/private-link/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Virtual%20Network%20Private%20Link%27%20and%20meterName%20eq%20%27Standard%20Private%20Endpoint%27%20and%20armRegionName%20eq%20%27Global%27" },
    nat: { label: "Azure NAT Gateway pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/azure-nat-gateway/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27NAT%20Gateway%27%20and%20meterName%20eq%20%27Standard%20Gateway%27%20and%20armRegionName%20eq%20%27Global%27" },
    apim: { label: "Azure API Management pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/api-management/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27API%20Management%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Basic%20v2%20Unit%27%20or%20meterName%20eq%20%27Standard%20v2%20Unit%27%29" },
    eh: { label: "Azure Event Hubs pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/event-hubs/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Event%20Hubs%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20Throughput%20Unit%27%20or%20meterName%20eq%20%27Standard%20Capture%27%29" },
    fabric: { label: "Microsoft Fabric pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/microsoft-fabric/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Fabric%20Capacity%27%20and%20meterName%20eq%20%27Data%20Warehouse%20Capacity%20Usage%20CU%27" },
    shopify: { label: "Shopify UK pricing", url: "https://www.shopify.com/uk/pricing" },
    shopEmail: { label: "Shopify Email pricing", url: "https://www.shopify.com/email-marketing" },
    ses: { label: "Amazon SES pricing", url: "https://aws.amazon.com/ses/pricing/" },
    stripe: { label: "Stripe UK pricing", url: "https://stripe.com/gb/pricing" },
    stripeTax: { label: "Stripe Tax pricing", url: "https://stripe.com/gb/tax/pricing" },
    entra: { label: "Microsoft Entra External ID pricing", url: "https://azure.microsoft.com/en-gb/pricing/details/microsoft-entra-external-id/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Microsoft%20Entra%20External%20ID%27%20and%20meterName%20eq%20%27Core%20Monthly%20Active%20Users%27" },
    fdcdn: { label: "Azure Front Door pricing (data transfer, requests)", url: "https://azure.microsoft.com/en-gb/pricing/details/frontdoor/", api: "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Azure%20Front%20Door%27%20and%20armRegionName%20eq%20%27Zone%201%27%20and%20skuName%20eq%20%27Standard%27%20and%20%28meterName%20eq%20%27Standard%20Data%20Transfer%20Out%27%20or%20meterName%20eq%20%27Standard%20Requests%27%29" },
    paypal: { label: "PayPal UK business fees", url: "https://www.paypal.com/uk/business/paypal-business-fees" },
    temporal: { label: "Temporal Cloud pricing", url: "https://temporal.io/pricing" },
    claude: { label: "Claude pricing (plans + API)", url: "https://claude.com/pricing" },
    github: { label: "GitHub pricing", url: "https://github.com/pricing" },
    ghActions: { label: "GitHub Actions runner pricing", url: "https://docs.github.com/en/billing/reference/actions-runner-pricing" },
    gws: { label: "Google Workspace UK pricing", url: "https://workspace.google.com/intl/en_uk/pricing" },
    jira: { label: "Atlassian · Jira Cloud plans", url: "https://support.atlassian.com/jira-cloud-administration/docs/explore-jira-cloud-plans/" },
    xero: { label: "Xero UK pricing", url: "https://www.xero.com/uk/pricing-plans/" },
    gorgias: { label: "Gorgias pricing", url: "https://www.gorgias.com/pricing" },
  };

  // ---------- official unit prices ----------
  const P = {
    // Azure, USD, UK South
    acaVcpuActive: 0.000034, acaVcpuIdle: 0.000004, acaMem: 0.000004, acaReqPerM: 0.40,
    acaFreeVcpuS: 180000, acaFreeGiBS: 360000, acaFreeReqM: 2,
    acaDedVcpuH: 0.080859, acaDedMemH: 0.006638, acaDedMgmtH: 0.10,
    pgB1msH: 0.019, pgD2H: 0.206, pgD4H: 0.412, pgD8H: 0.824, pgStorageGB: 0.133,
    sbStdMonth: 10, sbOpsFreeM: 13, sbOpsPerM: 0.80, sbPremiumH: 0.9275,
    kvPer10k: 0.03,
    laPerGB: 2.88, laFreeGB: 5,
    blobGB: 0.0192,
    acrBasicDay: 0.1666, acrStdDay: 0.6666, acrPremDay: 1.6666,
    dnsZone: 0.50,
    appcfgStdDay: 1.2,
    fdStdMonth: 35, fdPremMonth: 330,
    redisB1H: 0.037, redisB5H: 0.179,
    peH: 0.01, natH: 0.045,
    egressFreeGB: 100, egressGB: 0.087,
    defenderVcoreH: 0.00941,
    ehTuH: 0.03, ehCaptureH: 0.10,
    apimBasicV2H: 0.20548, apimStdV2H: 0.9589,
    fabricCuH: 0.21,
    // Other vendors
    shopifyPlan: [["Basic", 25, 0.02, 0.031], ["Grow", 65, 0.017, 0.027], ["Advanced", 344, 0.015, 0.025], ["Plus", 1800, 0.013, 0.023]], // GBP/mo (monthly billing), UK card %, international card %
    shopifyCardFixed: 0.25,             // GBP per card transaction
    shopEmailFree: 10000, shopEmailPer1k: 1.0, // USD
    paypalPct: 0.029, paypalFixed: 0.30, paypalIntl: 0.0199, // GBP
    temporalPerM: 50, temporalBizMin: 500, // USD
    gh: { team: 4, ent: 21, teamMin: 3000, entMin: 50000, linuxMin: 0.006 }, // USD
    claudePlans: { pro: ["Pro", 20], max: ["Max", 100], team: ["Team premium seat", 125] }, // USD, monthly billing
    sesPer1k: 0.10,                                  // USD, Amazon SES outbound
    stripe: { uk: 0.015, eea: 0.025, intl: 0.0315, fixed: 0.20, radar: 0.04, taxPct: 0.005 }, // GBP, Stripe UK pricing
    fdOut: [[0, 0.0825], [10000, 0.065002], [50000, 0.056001], [150000, 0.014083]], fdReq10k: 0.009, // USD, Front Door Standard, Zone 1
    extFreeMau: 50000, extMau: 0.01625,              // USD, Entra External ID Core MAU
    gwsStarter: 5.90,                    // GBP per user, annual plan
    xero: { grow: 39, comprehensive: 55 }, // GBP
    gorgias: [["Starter", 10, 50, 0.40], ["Basic", 60, 300, 0.40], ["Pro", 360, 2000, 0.36], ["Advanced", 900, 5000, 0.36]], // USD
    // Anthropic API, USD per million tokens (Microsoft Foundry bills Claude at the same list rates)
    models: {
      haiku: { name: "Claude Haiku 5.5", in: 0.10, out: 0.50, cache: 0.01 },
      sonnet: { name: "Claude Sonnet 5.5", in: 2.0, out: 10.0, cache: 0.10 },
      opus: { name: "Claude Opus 5.5", in: 4.0, out: 20.0, cache: 0.20 },
    },
  };

  // ---------- inputs the reader controls ----------
  const CFG = {
    customers24: 1000000,
    aov: 60,                      // GBP average order value
    devs: [1, 1, 2, 4],           // developers per phase
    devCost: 5000,                // GBP per developer per month (salary or contract, your figure)
    owners: 2,                    // owners: company accounts only, not costed as salary
    includeTeam: true,
    claudePlan: "max",
    intlShare: [0, 0.05, 0.25, 0.45], // share of orders paid with non-UK cards (US, EU)
    paypalShare: [0.15, 0.12, 0.10, 0.10],
    repeatRate: 0.025,
    ticketRate: 0.12,
    promptMult: 1,
    p3Servers: 3,                 // dedicated D4 servers in phase 3
    p4Servers: 3,                 // dedicated D4 servers per region in phase 4
    p4Regions: 1,                 // 1 = UK South (+ DR database copy in UK West), 2 = UK South + US East
    p4Db: "D4",                   // phase 4 database size: "D4" (4 vCPU) or "D8" (8 vCPU)
    p4Storage: 512,               // phase 4 database storage per copy, GB
    storefront: "shopify",        // "shopify" or "own"
    email: "shopify",             // "shopify", "ses3" (SES from phase 3) or "ses"
    ownDevs: [1, 1, 1, 2],        // extra developers to build and run our own storefront
    optional: { gorgias: false, privnet: false, apim: false, fabric: false, eventhubs: false, wafPremium: false, temporalBiz: false, ghEnterprise: false },
  };

  // Shape of the growth curve (share of the month-24 target), month 1..24
  const SHAPE = [0, 0.0003, 0.001, 0.0025, 0.005, 0.009, 0.015, 0.023, 0.033, 0.046, 0.062, 0.082, 0.105,
    0.132, 0.163, 0.2, 0.245, 0.297, 0.357, 0.42, 0.5, 0.59, 0.69, 0.83, 1.0];

  const PHASES = [
    { n: 1, name: "Test", from: 1, to: 4 },
    { n: 2, name: "Traction", from: 5, to: 9 },
    { n: 3, name: "Scale", from: 10, to: 16 },
    { n: 4, name: "Million", from: 17, to: 24 },
  ];
  const AGENTS = [11, 19, 29, 33];
  const phaseOf = (m) => PHASES.find((p) => m >= p.from && m <= p.to);

  function volume(m) {
    const c = SHAPE[m] * CFG.customers24, prev = SHAPE[m - 1] * CFG.customers24, p = phaseOf(m);
    const newCustomers = c - prev, orders = newCustomers + CFG.repeatRate * prev;
    let cumOrders = 0;
    for (let k = 1; k <= m; k++) cumOrders += SHAPE[k] * CFG.customers24 - SHAPE[k - 1] * CFG.customers24 + CFG.repeatRate * SHAPE[k - 1] * CFG.customers24;
    const pos = Math.max(8, orders / 400);
    const tickets = orders * CFG.ticketRate;
    return {
      m, phase: p, customers: c, newCustomers, orders, cumOrders, pos, tickets,
      ordersPerDay: orders / 30,
      peakOrdersPerSec: (orders / 30) * 4 * 0.12 / 3600, // peak day = 4x average; 12% of it in the busiest hour
      sales: orders * CFG.aov,
      actions: orders * 3 + pos * 20,
      emails: c * 1.6 * 4, // 1.6 contacts per customer, ~4 marketing/lifecycle emails a month
    };
  }

  // ---------- AI: model routing and tokens ----------
  const ROUTES = [
    { agent: "Care · Triage", task: "Classify each customer message", model: "haiku", calls: (v) => v.tickets, inTok: 2500, outTok: 150, cache: 0.6 },
    { agent: "Care · Resolution", task: "Answer from order data + policy (≈2 tool rounds)", model: "sonnet", calls: (v) => v.tickets * 0.8 * 2, inTok: 9000, outTok: 600, cache: 0.7 },
    { agent: "Care · Reply QA", task: "Check every reply before it is sent", model: "haiku", calls: (v) => v.tickets * 0.8, inTok: 3000, outTok: 200, cache: 0.5 },
    { agent: "Fraud · grey zone", task: "Review the ~3% of orders the score can't decide", model: "sonnet", calls: (v, p) => (p > 1 ? v.orders * 0.03 : 0), inTok: 6000, outTok: 400, cache: 0.5 },
    { agent: "Supplier Liaison · Extractor", task: "Read supplier emails and PDFs (no separate OCR service)", model: "haiku", calls: (v) => v.pos * 4, inTok: 8000, outTok: 800, cache: 0.2 },
    { agent: "Supplier Liaison · Verifier", task: "Independently re-check every extraction", model: "sonnet", calls: (v) => v.pos * 4, inTok: 8000, outTok: 300, cache: 0.2 },
    { agent: "Procurement", task: "Build PO proposals over calculators (≈6 tool rounds)", model: "opus", calls: (v) => v.pos * 6, inTok: 15000, outTok: 1500, cache: 0.6 },
    { agent: "Buy Panel", task: "3 reviewers + judge on unusual or large POs", model: "opus", calls: (v, p) => (p > 1 ? v.pos * 0.2 * 4 : 0), inTok: 20000, outTok: 1500, cache: 0.4 },
    { agent: "Catalogue + Compliance", task: "Product copy; check UV / CE / FDA test reports", model: "sonnet", calls: (v, p) => [6, 10, 25, 40][p - 1] * 3, inTok: 6000, outTok: 1500, cache: 0.3 },
    { agent: "Creative + Brand Guardian", task: "Ad and email variants, then brand check", model: "sonnet", calls: (v, p) => [400, 1500, 4000, 10000][p - 1], inTok: 4000, outTok: 600, cache: 0.6 },
    { agent: "Pricing · rationale", task: "Explain and justify price proposals", model: "sonnet", calls: (v, p) => [24, 60, 150, 300][p - 1] * 8, inTok: 5000, outTok: 400, cache: 0.6 },
    { agent: "Auditor (Batch API, −50%)", task: "Re-check a sample of yesterday's actions", model: "haiku", calls: (v, p) => v.actions * [0.1, 0.05, 0.03, 0.03][p - 1], inTok: 4000, outTok: 300, cache: 0.5, batch: true },
    { agent: "Incident Commander", task: "Diagnose and coordinate incidents", model: "opus", calls: (v, p) => [2, 4, 8, 10][p - 1] * 30, inTok: 30000, outTok: 2000, cache: 0.5 },
    { agent: "CI eval suite", task: "Golden cases re-run on every agent release", model: "sonnet", calls: (v, p) => CFG.devs[p - 1] * 8 * [50, 250, 750, 1250][p - 1], inTok: 6000, outTok: 600, cache: 0.5 },
  ];
  function llm(m, mult) {
    mult = mult || CFG.promptMult;
    const v = volume(m), p = v.phase.n;
    const rows = ROUTES.map((r) => {
      const M = P.models[r.model], calls = r.calls(v, p);
      const inT = r.inTok * mult, outT = r.outTok * mult;
      let per = (inT * ((1 - r.cache) * M.in + r.cache * M.cache) + outT * M.out) / 1e6;
      if (r.batch) per *= 0.5;
      return { ...r, modelName: M.name, calls, tokens: calls * (inT + outT), cost: usd(calls * per) };
    }).filter((r) => r.calls > 0);
    // Shadow runs: new agent versions process ~10% of production traffic before they act
    const prod = rows.filter((r) => r.agent !== "CI eval suite").reduce((s, r) => s + r.cost, 0);
    const shadow = prod * 0.10;
    rows.push({ agent: "Shadow runs", task: "New agent versions run silently on ~10% of traffic", modelName: "same as production", calls: 0, inTok: 0, outTok: 0, cache: 0, tokens: rows.reduce((s, r) => s + r.tokens, 0) * 0.1, cost: shadow });
    return { rows, tokens: rows.reduce((s, r) => s + r.tokens, 0), cost: rows.reduce((s, r) => s + r.cost, 0) };
  }

  // ---------- helpers ----------
  const n0 = (x) => Math.round(x).toLocaleString("en-GB");
  const big = (x) => (x >= 1e9 ? (x / 1e9).toFixed(1) + "B" : x >= 1e6 ? (x / 1e6).toFixed(1) + "M" : x >= 1e4 ? Math.round(x / 1000) + "k" : n0(x));
  const pgMonth = (ph, gb, copies) => usd((ph * HOURS + gb * P.pgStorageGB) * copies);

  function acaConsumption(alwaysOn, activeSec, reqM) {
    // alwaysOn: [vcpu, GiB, replicas] at idle rate; activeSec: worker seconds at 0.5 vCPU / 1 GiB
    let idleV = 0, mem = 0;
    alwaysOn.forEach(([c, g, r]) => { idleV += c * r * SEC; mem += g * r * SEC; });
    let actV = activeSec * 0.5; mem += activeSec * 1;
    let free = P.acaFreeVcpuS;
    const useA = Math.min(free, actV); actV -= useA; free -= useA;
    idleV = Math.max(0, idleV - free);
    mem = Math.max(0, mem - P.acaFreeGiBS);
    return usd(actV * P.acaVcpuActive + idleV * P.acaVcpuIdle + mem * P.acaMem + Math.max(0, reqM - P.acaFreeReqM) * P.acaReqPerM);
  }
  const workerSec = (v) => v.orders * 4 + v.tickets * 20 + v.pos * 300 + 30 * 3600;
  const dedNode = () => (4 * P.acaDedVcpuH + 16 * P.acaDedMemH) * HOURS;

  function shopifyBest(v) {
    let best = null;
    P.shopifyPlan.forEach(([name, fee, uk, intl]) => {
      const cardOrders = v.orders * (1 - CFG.paypalShare[v.phase.n - 1]);
      const i = CFG.intlShare[v.phase.n - 1];
      const cardFees = cardOrders * ((1 - i) * (uk * CFG.aov) + i * (intl * CFG.aov) + P.shopifyCardFixed);
      const total = fee + cardFees;
      if (!best || total < best.total) best = { name, fee, uk, intl, cardFees, total };
    });
    return best;
  }
  function gorgiasBest(v) {
    let best = null;
    P.gorgias.forEach(([name, price, inc, over]) => { const c = price + Math.max(0, v.tickets - inc) * over; if (!best || c < best.c) best = { name, c }; });
    return best;
  }
  const temporalActions = (v) => v.orders * 40 + v.pos * 200 + v.tickets * 10 + 30000;
  const ghMinutes = (p) => CFG.devs[p - 1] * 1500;

  // ---------- storefront and email choices ----------
  const own = () => CFG.storefront === "own";
  const regions = (p) => (p === 4 ? CFG.p4Regions : 1);
  const servers = (p) => (p === 3 ? CFG.p3Servers : p === 4 ? CFG.p4Servers * CFG.p4Regions : 0);
  const p4DbH = () => (CFG.p4Db === "D8" ? P.pgD8H : P.pgD4H);
  const emailProv = (p) => (own() || CFG.email === "ses" || (CFG.email === "ses3" && p >= 3) ? "ses" : "shopify");
  const sessions = (v) => v.orders / 0.022;
  function cdnCost(v) {
    const gb = sessions(v) * 0.003; let left = gb, cost = 0;
    for (let i = 0; i < P.fdOut.length; i++) {
      const lo = P.fdOut[i][0], hi = i + 1 < P.fdOut.length ? P.fdOut[i + 1][0] : Infinity;
      const take = Math.max(0, Math.min(left, hi - lo)); cost += take * P.fdOut[i][1]; left -= take;
    }
    return usd(cost + sessions(v) * 40 / 10000 * P.fdReq10k + 20 * P.blobGB);
  }
  function storeApiCost(v, p) {
    const calls = sessions(v) * 8;
    if (p <= 2) return usd(calls * 0.02 * P.acaVcpuActive + calls * 0.04 * P.acaMem + calls / 1e6 * P.acaReqPerM + (0.5 + 1) * SEC * P.acaVcpuIdle);
    return usd(dedNode() * regions(p));
  }
  const stripeCard = (v, p) => { const i = CFG.intlShare[p - 1], a = CFG.aov, S_ = P.stripe; return v.orders * (1 - CFG.paypalShare[p - 1]) * ((1 - i) * S_.uk * a + i * 0.6 * S_.intl * a + i * 0.4 * S_.eea * a + S_.fixed); };
  const mau = (v) => v.orders * 0.5;

  // ---------- bill of materials ----------
  // Each line: lane, name, cost(v, p, m) in GBP, what(v, p, m), unit (official unit price), src, opt (optional add-on key), from (first month)
  const LINES = [
    // Commerce
    { lane: "commerce", icon: "store", name: "Storefront & checkout · Shopify", src: "shopify", when: () => !own(),
      cost: (v) => shopifyBest(v).fee, what: (v) => shopifyBest(v).name + " plan (cheapest plan for this month's sales, card fees included)",
      unit: () => "Basic £25 · Grow £65 · Advanced £344 · Plus from £1,800 /mo" },
    { lane: "commerce", icon: "mail", name: "Marketing email · Shopify Email", src: "shopEmail", when: (p) => emailProv(p) === "shopify",
      cost: (v) => usd(Math.max(0, v.emails - P.shopEmailFree) / 1000 * P.shopEmailPer1k), what: (v) => big(v.emails) + " emails/mo", unit: () => "10,000 free, then $1 per 1,000" },
    { lane: "commerce", icon: "chat", name: "Customer chat · Shopify Inbox", src: "shopify", when: () => !own(), cost: () => 0, incl: true, what: () => "Chat on the store; our Resolution agent answers", unit: () => "Included" },
    { lane: "commerce", icon: "mail", name: "Email sending · Amazon SES", src: "ses", when: (p) => emailProv(p) === "ses",
      cost: (v) => usd((v.emails + (own() ? v.orders * 3 : 0)) / 1000 * P.sesPer1k),
      what: (v) => big(v.emails) + " marketing" + (own() ? " + " + big(v.orders * 3) + " order emails" : "") + "/mo · we handle templates, unsubscribe, bounces", unit: () => "$0.10 per 1,000 emails" },
    { lane: "commerce", icon: "store", name: "Own storefront · CDN + hosting (Front Door + Blob)", src: "fdcdn", when: () => own(),
      cost: (v) => cdnCost(v), what: (v) => big(sessions(v)) + " visits/mo · ~" + n0(sessions(v) * 0.003) + " GB served", unit: () => "Front Door $0.0825/GB (first 10 TB) · $0.009 per 10k requests" },
    { lane: "commerce", icon: "cpu", name: "Own storefront · cart & checkout API", src: "aca", when: () => own(),
      cost: (v, p) => storeApiCost(v, p), what: (v, p) => big(sessions(v) * 8) + " API calls/mo · " + (p <= 2 ? "Container Apps consumption" : "+" + regions(p) + " dedicated D4 node(s)"), unit: () => "Container Apps rates (see runtime line)" },
    { lane: "commerce", icon: "people", name: "Own storefront · customer logins", src: "entra", when: () => own(),
      cost: (v) => usd(Math.max(0, mau(v) - P.extFreeMau) * P.extMau), what: (v) => big(mau(v)) + " monthly active users (50k free)", unit: () => "Entra External ID: 50k MAU free, then $0.01625" },
    { lane: "commerce", icon: "chat", name: "Own storefront · chat widget, search, product pages", src: null, when: () => own(), cost: () => 0, incl: true,
      what: () => "Built by our team: chat widget (our agent), Postgres full-text search, product CMS", unit: () => "Engineering time (see Team)" },

    // Cloud compute
    { lane: "cloud", icon: "cpu", name: "Production runtime · Container Apps", src: "aca",
      cost: (v, p) => p <= 2 ? acaConsumption(p === 1 ? [[0.5, 1, 1]] : [[0.5, 1, 2], [0.5, 1, 1]], workerSec(v), (v.orders * 12 + v.tickets * 6) / 1e6)
        : usd(dedNode() * servers(p) + P.acaDedMgmtH * HOURS * regions(p)),
      what: (v, p) => ["Consumption plan · gateway 1 replica always on, agents scale from zero", "Consumption · gateway ×2 + adapters always on, agents scale from zero", "Dedicated · " + CFG.p3Servers + " × D4 nodes (4 vCPU, 16 GiB) across zones", "Dedicated · " + servers(4) + " × D4 nodes" + (CFG.p4Regions === 2 ? " in 2 regions (UK South, US East)" : " across zones, 1 region")][p - 1],
      unit: (v, p) => p <= 2 ? "$0.000034 active / $0.000004 idle per vCPU-s · $0.000004 per GiB-s · 180k vCPU-s free" : "$0.080859 per vCPU-h · $0.006638 per GiB-h · $0.10/h management" },
    { lane: "cloud", icon: "layers", name: "Staging & PR previews", src: "aca",
      cost: (v, p) => acaConsumption([], CFG.devs[p - 1] * 40 * 3600, 0.1) + pgMonth(p <= 2 ? P.pgB1msH : P.pgD2H, p <= 2 ? 32 : 128, 1),
      what: (v, p) => "Scale-to-zero apps (~" + CFG.devs[p - 1] * 40 + " active h/mo) + Postgres " + (p <= 2 ? "B1ms" : "D2ds_v5"), unit: () => "Container Apps consumption + Postgres Flexible Server rates" },
    { lane: "cloud", icon: "globe", name: "Edge & WAF · Front Door", src: "fd", when: (p) => own() || p >= 2,
      cost: (v, p) => usd(p === 4 || (p === 3 && CFG.optional.wafPremium) ? P.fdPremMonth : P.fdStdMonth),
      what: (v, p) => (p === 4 || (p === 3 && CFG.optional.wafPremium) ? "Premium (managed WAF rules, bot protection)" : "Standard (custom WAF rules)") + " for APIs, webhooks, owner console",
      unit: () => "Standard $35/mo · Premium $330/mo base" },
    { lane: "cloud", icon: "dns", name: "DNS zones", src: "dns", cost: (v, p) => usd([2, 3, 4, 6][p - 1] * P.dnsZone), what: (v, p) => [2, 3, 4, 6][p - 1] + " zones", unit: () => "$0.50 per zone/mo" },
    { lane: "cloud", icon: "net", name: "Outbound data", src: "egress", cost: (v) => usd(Math.max(0, v.orders * 0.002 - P.egressFreeGB) * P.egressGB), what: (v) => n0(v.orders * 0.002) + " GB/mo", unit: () => "100 GB free, then $0.087/GB" },

    // Data
    { lane: "data", icon: "db", name: "Ops Ledger · Postgres Flexible Server", src: "pg",
      cost: (v, p) => [pgMonth(P.pgB1msH, 32, 1), pgMonth(P.pgD2H, 128, 2), pgMonth(P.pgD4H, 512, 3), pgMonth(p4DbH(), CFG.p4Storage, 3)][p - 1],
      what: (v, p) => ["B1ms (1 vCore, 2 GiB), 32 GB, point-in-time restore", "D2ds_v5 + zone-redundant HA standby, 128 GB", "D4ds_v5 + HA standby + DR replica (UK West), 512 GB",
        CFG.p4Db + "ds_v5 + HA standby + " + (CFG.p4Regions === 2 ? "US East geo-replica" : "DR replica (UK West)") + ", " + n0(CFG.p4Storage) + " GB"][p - 1],
      unit: (v, p) => ["$0.019/h", "$0.206/h", "$0.412/h", CFG.p4Db === "D8" ? "$0.824/h" : "$0.412/h"][p - 1] + " per server · $0.133/GB-mo storage; HA and replicas bill a full copy" },
    { lane: "data", icon: "bolt", name: "Redis · Azure Managed Redis", src: "redis", from: 5,
      cost: (v, p) => usd([0, P.redisB1H, P.redisB5H, P.redisB5H * CFG.p4Regions][p - 1] * HOURS), what: (v, p) => ["", "Balanced B1 · spend counters, locks", "Balanced B5", "Balanced B5" + (CFG.p4Regions === 2 ? " × 2 regions" : "")][p - 1], unit: () => "B1 $0.037/h · B5 $0.179/h" },
    { lane: "data", icon: "queue", name: "Event bus · Service Bus Standard", src: "sb",
      cost: (v, p) => usd(P.sbStdMonth * regions(p) + Math.max(0, (v.orders * 60 + v.tickets * 20 + 500000) / 1e6 - P.sbOpsFreeM) * P.sbOpsPerM),
      what: (v, p) => big(v.orders * 60 + v.tickets * 20 + 500000) + " operations/mo" + (regions(p) === 2 ? " · one namespace per region" : ""), unit: () => "$10/mo base · 13M ops free, then $0.80/M" },
    { lane: "data", icon: "archive", name: "Blob storage (documents, audit archive)", src: "blob", cost: (v) => usd((5 + v.cumOrders * 0.00005) * P.blobGB), what: (v) => n0(5 + v.cumOrders * 0.00005) + " GB hot LRS", unit: () => "$0.0192/GB-mo" },
    { lane: "data", icon: "key", name: "Secrets · Key Vault", src: "kv", cost: (v) => usd((v.orders * 20 + 100000) / 10000 * P.kvPer10k), what: (v) => big(v.orders * 20 + 100000) + " operations/mo", unit: () => "$0.03 per 10,000 operations" },
    { lane: "data", icon: "toggle", name: "Feature flags & kill switches · App Configuration", src: "appcfg",
      cost: (v, p) => usd(p === 1 ? 0 : P.appcfgStdDay * 30.4 * regions(p)), what: (v, p) => ["Free tier", "Standard", "Standard", CFG.p4Regions === 2 ? "Standard + replica" : "Standard"][p - 1], unit: () => "Free tier · Standard $1.20/day" },

    // AI & agents
    { lane: "ai", icon: "spark", name: "LLM tokens · Claude on Microsoft Foundry", src: "claude", cost: (v, p, m) => llm(m).cost, what: (v, p, m) => big(llm(m).tokens) + " tokens/mo across 14 routes (see AI table)", unit: () => "Haiku $0.10/$0.50 · Sonnet $2/$10 · Opus $4/$20 per M tokens" },
    { lane: "ai", icon: "flow", name: "Durable workflows · Temporal Cloud", src: "temporal",
      cost: (v) => usd(CFG.optional.temporalBiz ? Math.max(P.temporalBizMin, temporalActions(v) / 1e6 * P.temporalPerM) : temporalActions(v) / 1e6 * P.temporalPerM),
      what: (v) => (CFG.optional.temporalBiz ? "Business plan · " : "Pay-as-you-go · ") + big(temporalActions(v)) + " actions/mo", unit: () => "$50 per million actions, no base fee" },
    { lane: "ai", icon: "gate", name: "Action Gateway + MCP tool servers", src: "aca", cost: () => 0, incl: true, what: () => "Run inside the production runtime above", unit: () => "Included in runtime" },
    { lane: "ai", icon: "chart", name: "Forecasting jobs", src: "aca", cost: () => 0, incl: true, what: (v, p) => ["Reorder-point rules", "Nightly statsforecast job", "Nightly LightGBM + reconciliation job", "+ elasticity models"][p - 1], unit: () => "Container Apps jobs, inside runtime" },

    // Observability & security
    { lane: "obs", icon: "pulse", name: "Logs, metrics, traces · Log Analytics", src: "la",
      cost: (v) => usd(Math.max(0, 2 + v.orders * 0.0008 + v.tickets * 0.0003 - P.laFreeGB) * P.laPerGB), what: (v) => n0(2 + v.orders * 0.0008 + v.tickets * 0.0003) + " GB/mo ingested (31 days retention included)", unit: () => "5 GB free, then $2.88/GB" },
    { lane: "obs", icon: "lock", name: "Container security · Defender for Containers", src: "defender", from: 10,
      cost: (v, p) => usd(servers(p) * 4 * P.defenderVcoreH * HOURS), what: (v, p) => servers(p) * 4 + " vCores protected", unit: () => "$0.00941 per vCore-h" },
    { lane: "obs", icon: "box", name: "Container registry", src: "acr",
      cost: (v, p) => usd([P.acrBasicDay, P.acrBasicDay, P.acrStdDay, CFG.p4Regions === 2 ? P.acrPremDay * 2 : P.acrStdDay][p - 1] * 30.4), what: (v, p) => ["Basic", "Basic", "Standard", CFG.p4Regions === 2 ? "Premium + geo-replica" : "Standard"][p - 1], unit: () => "Basic $0.1666/day · Standard $0.6666 · Premium $1.6666" },

    // Business tools
    { lane: "biz", icon: "book", name: "Accounting · Xero", src: "xero", cost: (v, p) => (p <= 2 ? P.xero.grow : P.xero.comprehensive), what: (v, p) => (p <= 2 ? "Grow" : "Comprehensive (multi-currency)"), unit: () => "Grow £39 · Comprehensive £55 /mo" },

    // Engineering & workplace
    { lane: "eng", icon: "git", name: "Source control · GitHub", src: "github",
      cost: (v, p) => usd(CFG.devs[p - 1] * (CFG.optional.ghEnterprise ? P.gh.ent : P.gh.team)), what: (v, p) => CFG.devs[p - 1] + " seat(s) · " + (CFG.optional.ghEnterprise ? "Enterprise" : "Team (protected branches on private repos)"), unit: () => "Team $4 · Enterprise $21 per user" },
    { lane: "eng", icon: "play", name: "CI build minutes · GitHub Actions", src: "ghActions",
      cost: (v, p) => usd(Math.max(0, ghMinutes(p) - (CFG.optional.ghEnterprise ? P.gh.entMin : P.gh.teamMin)) * P.gh.linuxMin), what: (v, p) => n0(ghMinutes(p)) + " Linux minutes/mo (" + (CFG.optional.ghEnterprise ? "50,000" : "3,000") + " included)", unit: () => "$0.006 per Linux 2-core minute" },
    { lane: "eng", icon: "claude", name: "AI coding · Claude Code", src: "claude",
      cost: (v, p) => usd(CFG.devs[p - 1] * P.claudePlans[CFG.claudePlan][1]), what: (v, p) => CFG.devs[p - 1] + " × " + P.claudePlans[CFG.claudePlan][0], unit: () => "Pro $20 · Max from $100 · Team premium $125 per seat/mo" },
    { lane: "eng", icon: "office", name: "Email, docs, meetings · Google Workspace", src: "gws",
      cost: (v, p) => (CFG.devs[p - 1] + CFG.owners) * P.gwsStarter, what: (v, p) => (CFG.devs[p - 1] + CFG.owners) + " users · Business Starter", unit: () => "£5.90 per user/mo (annual plan)" },
    { lane: "eng", icon: "kanban", name: "Planning · Jira", src: "jira", cost: () => 0, incl: true,
      what: (v, p) => (CFG.devs[p - 1] + CFG.owners <= 10 ? "Free plan (" + (CFG.devs[p - 1] + CFG.owners) + " of 10 users)" : "Over 10 users: GitHub Projects (included) or Jira Standard quote"), unit: () => "Free up to 10 users" },

    // Optional add-ons (off by default)
    { lane: "opt", icon: "chat", name: "Help-desk UI · Gorgias", src: "gorgias", opt: "gorgias",
      cost: (v) => usd(gorgiasBest(v).c), what: (v) => gorgiasBest(v).name + " · " + n0(v.tickets) + " tickets/mo", unit: () => "Starter $10 (50) · Basic $60 (300) · Pro $360 (2,000) · Advanced $900 (5,000)" },
    { lane: "opt", icon: "net", name: "Private networking pack", src: "sbp", opt: "privnet", from: 10,
      cost: (v, p) => usd(P.sbPremiumH * HOURS - P.sbStdMonth + (p === 3 ? 10 : 20) * P.peH * HOURS + (p === 3 ? 1 : 2) * P.natH * HOURS + P.acaDedMgmtH * HOURS),
      what: (v, p) => "Service Bus Premium (1 MU), " + (p === 3 ? 10 : 20) + " private endpoints, " + (p === 3 ? 1 : 2) + " NAT gateway(s)", unit: () => "Premium $0.9275/h · endpoint $0.01/h · NAT $0.045/h" },
    { lane: "opt", icon: "api", name: "API gateway · API Management", src: "apim", opt: "apim", from: 10,
      cost: (v, p) => usd((p === 3 ? P.apimBasicV2H : P.apimStdV2H) * HOURS), what: (v, p) => (p === 3 ? "Basic v2" : "Standard v2") + " · supplier API, token quotas", unit: () => "Basic v2 $0.20548/h · Standard v2 $0.9589/h" },
    { lane: "opt", icon: "lake", name: "Lakehouse · Microsoft Fabric", src: "fabric", opt: "fabric", from: 10,
      cost: (v, p) => usd((p === 3 ? 2 : 8) * P.fabricCuH * HOURS), what: (v, p) => (p === 3 ? "F2" : "F8") + " capacity, always on", unit: () => "$0.21 per capacity unit-hour" },
    { lane: "opt", icon: "stream", name: "Clickstream · Event Hubs", src: "eh", opt: "eventhubs", from: 17,
      cost: () => usd((2 * P.ehTuH + P.ehCaptureH) * HOURS), what: () => "Standard, 2 throughput units + capture", unit: () => "$0.03 per TU-h · capture $0.10/h" },
    { lane: "opt", icon: "globe", name: "WAF managed rules in phase 3", src: "fd", opt: "wafPremium", from: 10, cost: () => 0, note: true,
      what: (v, p) => (p === 3 ? "Moves Front Door to Premium a phase early (cost shown on the Front Door line)" : "Already Premium in phase 4"), unit: () => "Premium $330 vs Standard $35" },
    { lane: "opt", icon: "flow", name: "Temporal Business plan", src: "temporal", opt: "temporalBiz", cost: () => 0, note: true, what: () => "SSO and SLA; $500/mo minimum (cost shown on the Temporal line)", unit: () => "$500/mo minimum or 10% of usage" },
    { lane: "opt", icon: "git", name: "GitHub Enterprise", src: "github", opt: "ghEnterprise", cost: () => 0, note: true, what: () => "SSO, audit-log streaming, 50k Actions minutes (cost shown on the GitHub lines)", unit: () => "$21 per user/mo" },

    // Payments (variable)
    { lane: "pay", icon: "card", name: "Card payments · Shopify Payments", src: "shopify", when: () => !own(), cost: (v) => shopifyBest(v).cardFees,
      what: (v, p) => Math.round((1 - CFG.paypalShare[p - 1]) * 100) + "% of orders · " + Math.round(CFG.intlShare[p - 1] * 100) + "% on non-UK cards · " + shopifyBest(v).name + " rates",
      unit: (v) => { const b = shopifyBest(v); return (b.uk * 100).toFixed(1) + "% + 25p UK · " + (b.intl * 100).toFixed(1) + "% + 25p international"; } },
    { lane: "pay", icon: "card", name: "Card payments · Stripe", src: "stripe", when: () => own(), cost: (v, p) => stripeCard(v, p),
      what: (v, p) => Math.round((1 - CFG.paypalShare[p - 1]) * 100) + "% of orders · " + Math.round(CFG.intlShare[p - 1] * 100) + "% non-UK cards", unit: () => "1.5% + 20p UK · 2.5% EEA · 3.15% international" },
    { lane: "pay", icon: "lock", name: "Fraud screening · Stripe Radar", src: "stripe", when: () => own(), cost: (v, p) => v.orders * (1 - CFG.paypalShare[p - 1]) * P.stripe.radar,
      what: (v, p) => big(v.orders * (1 - CFG.paypalShare[p - 1])) + " card payments screened", unit: () => "£0.04 per screened transaction" },
    { lane: "pay", icon: "book", name: "US sales tax · Stripe Tax", src: "stripeTax", when: () => own(), cost: (v, p) => v.orders * CFG.intlShare[p - 1] * 0.6 * CFG.aov * P.stripe.taxPct,
      what: (v, p) => "US orders ≈ " + Math.round(CFG.intlShare[p - 1] * 60) + "% of orders; UK/EU VAT calculated in our code", unit: () => "0.5% per transaction where registered" },
    { lane: "pay", icon: "wallet", name: "PayPal", src: "paypal",
      cost: (v, p) => v.orders * CFG.paypalShare[p - 1] * (P.paypalPct * CFG.aov + P.paypalFixed + CFG.intlShare[p - 1] * P.paypalIntl * CFG.aov),
      what: (v, p) => Math.round(CFG.paypalShare[p - 1] * 100) + "% of orders", unit: () => "2.9% + £0.30 · +1.99% international" },

    // Team
    { lane: "team", icon: "people", name: "Developers", src: null, cost: (v, p) => CFG.devs[p - 1] * CFG.devCost, what: (v, p) => CFG.devs[p - 1] + " × £" + n0(CFG.devCost) + "/mo (your inputs)", unit: () => "Your input" },
    { lane: "team", icon: "people", name: "Extra developers · own storefront", src: null, when: () => own(), cost: (v, p) => CFG.ownDevs[p - 1] * CFG.devCost,
      what: (v, p) => CFG.ownDevs[p - 1] + " × £" + n0(CFG.devCost) + "/mo to build and run checkout, accounts, CMS, tax, fraud", unit: () => "Your input" },
  ];

  const LANES = [
    { id: "commerce", name: "Commerce", bucket: "runtime" },
    { id: "cloud", name: "Cloud compute & network", bucket: "runtime" },
    { id: "data", name: "Data, events & secrets", bucket: "runtime" },
    { id: "ai", name: "AI & agent platform", bucket: "runtime" },
    { id: "obs", name: "Observability & security", bucket: "runtime" },
    { id: "biz", name: "Business software", bucket: "runtime" },
    { id: "eng", name: "Engineering & workplace", bucket: "eng" },
    { id: "opt", name: "Optional add-ons", bucket: "opt", note: "off unless you switch them on" },
    { id: "pay", name: "Payment fees", bucket: "pay", note: "% of sales" },
    { id: "team", name: "Team", bucket: "team", note: "your inputs" },
  ];
  const BUCKETS = [
    { id: "runtime", name: "Runtime platform" },
    { id: "eng", name: "Engineering & workplace" },
    { id: "opt", name: "Optional add-ons" },
    { id: "pay", name: "Payment fees", variable: true },
    { id: "team", name: "Team" },
  ];
  const laneBucket = {}; LANES.forEach((l) => (laneBucket[l.id] = l.bucket));
  LINES.forEach((l) => (l.bucket = laneBucket[l.lane]));

  function bill(m) {
    const v = volume(m), p = v.phase.n;
    const items = LINES.map((l) => {
      const used = !l.when || l.when(p);
      const active = used && !(l.from && m < l.from) && (!l.opt || CFG.optional[l.opt]);
      const avail = used && !(l.from && m < l.from);
      const cost = active ? l.cost(v, p, m) : 0;
      return { ...l, active, avail, used, cost, what: avail ? l.what(v, p, m) : "", unitTxt: l.unit(v, p, m) };
    });
    const by = {}; BUCKETS.forEach((b) => (by[b.id] = 0));
    items.forEach((x) => (by[x.bucket] += x.cost));
    return { items, by };
  }

  function month(m) {
    const v = volume(m), b = bill(m);
    const tech = b.by.runtime + b.by.eng + b.by.opt;
    const team = CFG.includeTeam ? b.by.team : 0;
    return {
      ...v, items: b.items, by: b.by, runtime: b.by.runtime, eng: b.by.eng, opt: b.by.opt, fees: b.by.pay, teamCost: b.by.team,
      tech, allIn: tech + team, allInPct: (tech + team) / v.sales, techPct: tech / v.sales, feesPct: b.by.pay / v.sales,
      llm: llm(m), agents: AGENTS[v.phase.n - 1],
    };
  }

  const api = { FX, SRC, P, CFG, SHAPE, PHASES, LINES, LANES, BUCKETS, ROUTES, volume, bill, month, llm, phaseOf };
  if (typeof module !== "undefined") module.exports = api; else root.SCALE = api;
})(this);
