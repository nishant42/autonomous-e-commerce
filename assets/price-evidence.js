/* Official price snapshot: Microsoft Azure Retail Prices API, region UK South, retrieved 2026-10-17 (USD).
   Each entry holds only the meters used by assets/scale-model.js, plus the live query URL to re-check them. */
window.PRICE_EVIDENCE = {
 "retrieved": "2026-10-17",
 "currency": "USD",
 "evidence": {
  "aca": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Azure%20Container%20Apps%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20vCPU%20Active%20Usage%27%20or%20meterName%20eq%20%27Standard%20vCPU%20Idle%20Usage%27%20or%20meterName%20eq%20%27Standard%20Memory%20Active%20Usage%27%20or%20meterName%20eq%20%27Standard%20Memory%20Idle%20Usage%27%20or%20meterName%20eq%20%27Standard%20Requests%27%20or%20meterName%20eq%20%27Dedicated%20vCPU%20Usage%27%20or%20meterName%20eq%20%27Dedicated%20Memory%20Usage%27%20or%20meterName%20eq%20%27Dedicated%20Plan%20Management%27%29",
   "rows": [
    {
     "meter": "Dedicated Memory Usage",
     "sku": "Dedicated",
     "product": "Azure Container Apps",
     "unit": "1 Hour",
     "price": 0.006638,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Dedicated Plan Management",
     "sku": "Dedicated",
     "product": "Azure Container Apps",
     "unit": "1 Hour",
     "price": 0.1,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Dedicated vCPU Usage",
     "sku": "Dedicated",
     "product": "Azure Container Apps",
     "unit": "1 Hour",
     "price": 0.080859,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Memory Active Usage",
     "sku": "Standard",
     "product": "Azure Container Apps",
     "unit": "1 GiB Second",
     "price": 4e-06,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Memory Idle Usage",
     "sku": "Standard",
     "product": "Azure Container Apps",
     "unit": "1 GiB Second",
     "price": 4e-06,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Requests",
     "sku": "Standard",
     "product": "Azure Container Apps",
     "unit": "1M",
     "price": 0.4,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard vCPU Active Usage",
     "sku": "Standard",
     "product": "Azure Container Apps",
     "unit": "1 Second",
     "price": 3.4e-05,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard vCPU Idle Usage",
     "sku": "Standard",
     "product": "Azure Container Apps",
     "unit": "1 Second",
     "price": 4e-06,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "pg": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20%28%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flexible%20Server%20Burstable%20BS%20Series%20Compute%27%20and%20skuName%20eq%20%27B1MS%27%29%20or%20%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flexible%20Server%20General%20Purpose%20Ddsv5%20Series%20Compute%27%20and%20%28skuName%20eq%20%272%20vCore%27%20or%20skuName%20eq%20%274%20vCore%27%20or%20skuName%20eq%20%278%20vCore%27%29%29%20or%20%28productName%20eq%20%27Azure%20Database%20for%20PostgreSQL%20Flex%20Server%20Storage%27%20and%20meterName%20eq%20%27Storage%20Data%20Stored%27%29%29",
   "rows": [
    {
     "meter": "Storage Data Stored",
     "sku": "Storage",
     "product": "Azure Database for PostgreSQL Flex Server Storage",
     "unit": "1 GB/Month",
     "price": 0.133,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "B1MS",
     "sku": "B1MS",
     "product": "Azure Database for PostgreSQL Flexible Server Burstable BS Series Compute",
     "unit": "1 Hour",
     "price": 0.019,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "vCore",
     "sku": "4 vCore",
     "product": "Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 Series Compute",
     "unit": "1 Hour",
     "price": 0.412,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "vCore",
     "sku": "2 vCore",
     "product": "Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 Series Compute",
     "unit": "1 Hour",
     "price": 0.206,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "vCore",
     "sku": "8 vCore",
     "product": "Azure Database for PostgreSQL Flexible Server General Purpose Ddsv5 Series Compute",
     "unit": "1 Hour",
     "price": 0.824,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "sb": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Service%20Bus%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20skuName%20eq%20%27Standard%27%20and%20%28%28meterName%20eq%20%27Standard%20Base%20Unit%27%20and%20unitOfMeasure%20eq%20%271/Month%27%29%20or%20meterName%20eq%20%27Standard%20Messaging%20Operations%27%29",
   "rows": [
    {
     "meter": "Standard Base Unit",
     "sku": "Standard",
     "product": "Service Bus",
     "unit": "1/Month",
     "price": 10.0,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Messaging Operations",
     "sku": "Standard",
     "product": "Service Bus",
     "unit": "1M",
     "price": 0.0,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Messaging Operations",
     "sku": "Standard",
     "product": "Service Bus",
     "unit": "1M",
     "price": 0.8,
     "tierMin": 13.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Messaging Operations",
     "sku": "Standard",
     "product": "Service Bus",
     "unit": "1M",
     "price": 0.5,
     "tierMin": 100.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Messaging Operations",
     "sku": "Standard",
     "product": "Service Bus",
     "unit": "1M",
     "price": 0.2,
     "tierMin": 2500.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "sbp": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Service%20Bus%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20meterName%20eq%20%27Premium%20Messaging%20Unit%27",
   "rows": [
    {
     "meter": "Premium Messaging Unit",
     "sku": "Premium",
     "product": "Service Bus",
     "unit": "1/Hour",
     "price": 0.9275,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "kv": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Key%20Vault%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20skuName%20eq%20%27Standard%27%20and%20meterName%20eq%20%27Operations%27",
   "rows": [
    {
     "meter": "Operations",
     "sku": "Standard",
     "product": "Key Vault",
     "unit": "10K",
     "price": 0.03,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "la": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Log%20Analytics%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20meterName%20eq%20%27Analytics%20Logs%20Data%20Ingestion%27",
   "rows": [
    {
     "meter": "Analytics Logs Data Ingestion",
     "sku": "Analytics Logs",
     "product": "Log Analytics",
     "unit": "1 GB",
     "price": 0.0,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Analytics Logs Data Ingestion",
     "sku": "Analytics Logs",
     "product": "Log Analytics",
     "unit": "1 GB",
     "price": 2.88,
     "tierMin": 5.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "blob": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27General%20Block%20Blob%20v2%27%20and%20meterName%20eq%20%27Hot%20LRS%20Data%20Stored%27%20and%20tierMinimumUnits%20eq%200",
   "rows": [
    {
     "meter": "Hot LRS Data Stored",
     "sku": "Hot LRS",
     "product": "General Block Blob v2",
     "unit": "1 GB/Month",
     "price": 0.0192,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "acr": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Container%20Registry%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Basic%20Registry%20Unit%27%20or%20meterName%20eq%20%27Standard%20Registry%20Unit%27%20or%20meterName%20eq%20%27Premium%20Registry%20Unit%27%29",
   "rows": [
    {
     "meter": "Basic Registry Unit",
     "sku": "Basic",
     "product": "Container Registry",
     "unit": "1/Day",
     "price": 0.1666,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Premium Registry Unit",
     "sku": "Premium",
     "product": "Container Registry",
     "unit": "1/Day",
     "price": 1.6666,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Registry Unit",
     "sku": "Standard",
     "product": "Container Registry",
     "unit": "1/Day",
     "price": 0.6666,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "dns": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Azure%20DNS%27%20and%20meterName%20eq%20%27Public%20Zone%27%20and%20armRegionName%20eq%20%27Zone%201%27",
   "rows": [
    {
     "meter": "Public Zone",
     "sku": "Public",
     "product": "Azure DNS",
     "unit": "1",
     "price": 0.5,
     "tierMin": 0.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Public Zone",
     "sku": "Public",
     "product": "Azure DNS",
     "unit": "1",
     "price": 0.1,
     "tierMin": 25.0,
     "region": "Zone 1",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "appcfg": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27App%20Configuration%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20Instance%27%20or%20meterName%20eq%20%27Standard%20Replica%20Instance%27%29",
   "rows": [
    {
     "meter": "Standard Instance",
     "sku": "Standard",
     "product": "App Configuration",
     "unit": "1/Day",
     "price": 1.2,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Replica Instance",
     "sku": "Standard",
     "product": "App Configuration",
     "unit": "1/Day",
     "price": 1.2,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "fd": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Azure%20Front%20Door%27%20and%20contains%28meterName%2C%27Base%20Fees%27%29%20and%20armRegionName%20eq%20%27Zone%201%27",
   "rows": [
    {
     "meter": "Premium Base Fees",
     "sku": "Premium",
     "product": "Azure Front Door",
     "unit": "1/Month",
     "price": 330.0,
     "tierMin": 0.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Base Fees",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1/Month",
     "price": 35.0,
     "tierMin": 0.0,
     "region": "Zone 1",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "redis": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Azure%20Managed%20Redis%20-%20Balanced%27%20and%20%28meterName%20eq%20%27B1%20Cache%20Instance%27%20or%20meterName%20eq%20%27B5%20Cache%20Instance%27%29",
   "rows": [
    {
     "meter": "B1 Cache Instance",
     "sku": "B1",
     "product": "Azure Managed Redis - Balanced",
     "unit": "1 Hour",
     "price": 0.037,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "B5 Cache Instance",
     "sku": "B5",
     "product": "Azure Managed Redis - Balanced",
     "unit": "1 Hour",
     "price": 0.179,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "defender": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Microsoft%20Defender%20for%20Containers%27%20and%20skuName%20eq%20%27Standard%20vCore%27",
   "rows": [
    {
     "meter": "Standard vCore vCore Pack",
     "sku": "Standard vCore",
     "product": "Microsoft Defender for Containers",
     "unit": "1/Hour",
     "price": 0.00941,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "egress": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Bandwidth%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Rtn%20Preference%3A%20MGN%27%20and%20meterName%20eq%20%27Standard%20Data%20Transfer%20Out%27%20and%20%28tierMinimumUnits%20eq%200%20or%20tierMinimumUnits%20eq%20100%29",
   "rows": [
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Rtn Preference: MGN",
     "unit": "1 GB",
     "price": 0.0,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Rtn Preference: MGN",
     "unit": "1 GB",
     "price": 0.087,
     "tierMin": 100.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "pe": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Virtual%20Network%20Private%20Link%27%20and%20meterName%20eq%20%27Standard%20Private%20Endpoint%27%20and%20armRegionName%20eq%20%27Global%27",
   "rows": [
    {
     "meter": "Standard Private Endpoint",
     "sku": "Standard",
     "product": "Virtual Network Private Link",
     "unit": "1 Hour",
     "price": 0.01,
     "tierMin": 0.0,
     "region": "Global",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "nat": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27NAT%20Gateway%27%20and%20meterName%20eq%20%27Standard%20Gateway%27%20and%20armRegionName%20eq%20%27Global%27",
   "rows": [
    {
     "meter": "Standard Gateway",
     "sku": "Standard",
     "product": "NAT Gateway",
     "unit": "1 Hour",
     "price": 0.045,
     "tierMin": 0.0,
     "region": "Global",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "apim": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27API%20Management%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Basic%20v2%20Unit%27%20or%20meterName%20eq%20%27Standard%20v2%20Unit%27%29",
   "rows": [
    {
     "meter": "Basic v2 Unit",
     "sku": "Basic v2",
     "product": "API Management",
     "unit": "1 Hour",
     "price": 0.20548,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard v2 Unit",
     "sku": "Standard v2",
     "product": "API Management",
     "unit": "1 Hour",
     "price": 0.9589,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "eh": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=serviceName%20eq%20%27Event%20Hubs%27%20and%20armRegionName%20eq%20%27uksouth%27%20and%20%28meterName%20eq%20%27Standard%20Throughput%20Unit%27%20or%20meterName%20eq%20%27Standard%20Capture%27%29",
   "rows": [
    {
     "meter": "Standard Capture",
     "sku": "Standard",
     "product": "Event Hubs",
     "unit": "1 Hour",
     "price": 0.1,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    },
    {
     "meter": "Standard Throughput Unit",
     "sku": "Standard",
     "product": "Event Hubs",
     "unit": "1 Hour",
     "price": 0.03,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "fabric": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=armRegionName%20eq%20%27uksouth%27%20and%20productName%20eq%20%27Fabric%20Capacity%27%20and%20meterName%20eq%20%27Data%20Warehouse%20Capacity%20Usage%20CU%27",
   "rows": [
    {
     "meter": "Data Warehouse Capacity Usage CU",
     "sku": "Data Warehouse Capacity Usage",
     "product": "Fabric Capacity",
     "unit": "1 Hour",
     "price": 0.21,
     "tierMin": 0.0,
     "region": "uksouth",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "fdcdn": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Azure%20Front%20Door%27%20and%20armRegionName%20eq%20%27Zone%201%27%20and%20skuName%20eq%20%27Standard%27%20and%20%28meterName%20eq%20%27Standard%20Data%20Transfer%20Out%27%20or%20meterName%20eq%20%27Standard%20Requests%27%29",
   "rows": [
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.0825,
     "tierMin": 0.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.065002,
     "tierMin": 10000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.056001,
     "tierMin": 50000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.014083,
     "tierMin": 150000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.00693,
     "tierMin": 500000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.005742,
     "tierMin": 1000000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Data Transfer Out",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "1 GB",
     "price": 0.005404,
     "tierMin": 5000000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Requests",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "10K",
     "price": 0.009,
     "tierMin": 0.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Requests",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "10K",
     "price": 0.0081,
     "tierMin": 25000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Requests",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "10K",
     "price": 0.00729,
     "tierMin": 100000.0,
     "region": "Zone 1",
     "type": "Consumption"
    },
    {
     "meter": "Standard Requests",
     "sku": "Standard",
     "product": "Azure Front Door",
     "unit": "10K",
     "price": 0.006561,
     "tierMin": 500000.0,
     "region": "Zone 1",
     "type": "Consumption"
    }
   ],
   "next": false
  },
  "entra": {
   "api": "https://prices.azure.com/api/retail/prices?currencyCode='USD'&$filter=productName%20eq%20%27Microsoft%20Entra%20External%20ID%27%20and%20meterName%20eq%20%27Core%20Monthly%20Active%20Users%27",
   "rows": [
    {
     "meter": "Core Monthly Active Users",
     "sku": "Core",
     "product": "Microsoft Entra External ID",
     "unit": "1/Month",
     "price": 0.0,
     "tierMin": 0.0,
     "region": "Global",
     "type": "Consumption"
    },
    {
     "meter": "Core Monthly Active Users",
     "sku": "Core",
     "product": "Microsoft Entra External ID",
     "unit": "1/Month",
     "price": 0.01625,
     "tierMin": 50000.0,
     "region": "Global",
     "type": "Consumption"
    }
   ],
   "next": false
  }
 }
};
