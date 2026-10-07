# NASA Life Sciences Portal (NLSP) Harvester, Mirror & Sitemap

[![Update NLSP Catalog & Sitemap](https://github.com/Oht8wooWi8yait9n/nlsp/actions/workflows/update-sitemap.yml/badge.svg)](https://github.com/Oht8wooWi8yait9n/nlsp/actions/workflows/update-sitemap.yml)

Automated harvester, static HTML mirror, searchable catalog, and dual XML sitemaps for the **NASA Life Sciences Portal** ([https://nlsp.nasa.gov](https://nlsp.nasa.gov)).

This repository mirrors NASA's Life Sciences Data Archive (LSDA), Lifetime Surveillance of Astronaut Health (LSAH), and Human Research Program (HRP) knowledge bases, enabling enterprise RAG search engines like **Onyx** to reliably index all authoritative life sciences records with deterministic URL rewrites linking directly to official NASA live sources.

---

## 1. Catalog Coverage & Statistics

The harvest pulls directly from the public REST API (`https://nlsp.nasa.gov/api/v1/data/`) across all 9 canonical domains:

| Category | Description | Records |
| :--- | :--- | :--- |
| **Experiments** | LSDA space biology and human physiology flight & ground studies | **2,676** |
| **Datasets** | Flight research datasets, raw data repositories, and telemetry | **2,593** |
| **Missions** | Spaceflight missions (ISS, Shuttle, Apollo, Artemis, Skylab) | **350** |
| **Hardware** | Spaceflight payloads, centrifuges, freezers, and instruments | **782** |
| **Documents** | Technical reports, checkouts, standard operating procedures, publications | **3,933** |
| **Personnel** | Principal investigators, astronauts, flight medical officers, researchers | **3,604** |
| **Subjects** | Model organisms & research subject populations | **570** |
| **Images** | Mission, payload, and biological imagery metadata | **2,086** |
| **Biospecimens** | Biological specimen archive inventory (blood, tissue, urine) | **15,307** |
| **TOTAL** | **All Authoritative NLSP Records** | **31,901** |

---

## 2. Machine-Readable Endpoints

- **Live Searchable Catalog**: [https://oht8woowi8yait9n.github.io/nlsp/](https://oht8woowi8yait9n.github.io/nlsp/)
- **Primary XML Sitemap (Mirror URLs for Onyx)**: [https://oht8woowi8yait9n.github.io/nlsp/sitemap.xml](https://oht8woowi8yait9n.github.io/nlsp/sitemap.xml)
- **Direct NASA XML Sitemap (Live URLs)**: [https://oht8woowi8yait9n.github.io/nlsp/nlsp_direct_sitemap.xml](https://oht8woowi8yait9n.github.io/nlsp/nlsp_direct_sitemap.xml)
- **Plain Text Mirror URLs**: [https://oht8woowi8yait9n.github.io/nlsp/nlsp_urls.txt](https://oht8woowi8yait9n.github.io/nlsp/nlsp_urls.txt)
- **Unified JSONL Dataset**: [nlsp_records.jsonl](nlsp_records.jsonl)

---

## 3. Onyx Web Connector Configuration

When adding this dataset to Onyx:

1. Navigate to **Onyx Admin Panel** &rarr; **Connectors** &rarr; **Web**.
2. Create a new Web Connector with the following settings:
   - **Connector Name**: `NASA Life Sciences Portal (NLSP)`
   - **Base URL / Starting URLs**:
     ```
     https://oht8woowi8yait9n.github.io/nlsp/sitemap.xml
     ```
   - **Indexing Mode**: Single Page / Sitemap mode (non-recursive).
3. **URL Rewrite Rule**:
   - **Source Prefix**:
     ```
     https://oht8woowi8yait9n.github.io/nlsp/
     ```
   - **Target Prefix**:
     ```
     https://nlsp.nasa.gov/
     ```
4. **Result**:
   - Onyx indexes the high-fidelity pre-rendered static cards hosted on GitHub Pages with zero rate-limiting.
   - All citations in search results, chat answers, and agent workflows map directly to the official interactive NASA application:
     ```
     https://nlsp.nasa.gov/search/data/details/<id>?dataType=<DATA_TYPE>
     ```

---

## 4. Local Execution & Regrowth

To run the harvest locally:

```bash
# Full harvest and mirror build
python3 generate_nlsp_sitemap.py

# Force refresh (bypass cache)
FORCE_REFRESH=1 python3 generate_nlsp_sitemap.py
```
