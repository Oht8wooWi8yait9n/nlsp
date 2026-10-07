#!/usr/bin/env python3
"""
NASA Life Sciences Portal (nlsp.nasa.gov) Harvester, Mirror & Sitemap Generator
================================================================================
Harvests all authoritative life sciences records from NLSP:
  - Experiments (LSDA space biology & human physiology research)
  - Datasets (spaceflight research datasets & raw data repositories)
  - Missions (ISS, Space Shuttle, Apollo, Artemis, Skylab)
  - Hardware (flight payloads, instruments, centrifuges, freezers)
  - Documents (technical reports, SOPs, publications, checkouts)
  - Personnel (principal investigators, astronauts, flight medical officers)
  - Subjects (model organisms & research populations)
  - Images (mission and biological imagery)
  - Biospecimens (biological specimen archive tubes & storage inventory)

Generates:
  1. High-fidelity static HTML project cards (search/data/details/<id>.html & clean extensionless copy)
  2. Primary sitemap with clean mirror URLs (sitemap.xml & nlsp_sitemap.xml)
  3. Direct live NASA sitemap (nlsp_direct_sitemap.xml)
  4. Plain text URL lists (nlsp_urls.txt & nlsp_direct_urls.txt)
  5. Machine-readable JSONL dataset (nlsp_records.jsonl)
  6. Client-side searchable interactive catalog (index.html)
"""

import os
import sys
import re
import json
import time
import html
from html import escape
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DETAILS_DIR = os.path.join(BASE_DIR, "search", "data", "details")
CACHE_DIR = os.path.join(BASE_DIR, ".nlsp_cache")
RAW_CACHE_DIR = os.path.join(CACHE_DIR, "raw")
JSONL_FILE = os.path.join(BASE_DIR, "nlsp_records.jsonl")
SITEMAP_FILE = os.path.join(BASE_DIR, "sitemap.xml")
SITEMAP_ALIAS_FILE = os.path.join(BASE_DIR, "nlsp_sitemap.xml")
DIRECT_SITEMAP_FILE = os.path.join(BASE_DIR, "nlsp_direct_sitemap.xml")
URLS_FILE = os.path.join(BASE_DIR, "nlsp_urls.txt")
DIRECT_URLS_FILE = os.path.join(BASE_DIR, "nlsp_direct_urls.txt")
INDEX_HTML = os.path.join(BASE_DIR, "index.html")

NLSP_HOST = "https://nlsp.nasa.gov"
API_BASE = f"{NLSP_HOST}/api/v1/data"
LIVE_DETAIL_BASE = f"{NLSP_HOST}/search/data/details"

GH_PAGES_BASE = os.environ.get("GH_PAGES_BASE", "https://oht8woowi8yait9n.github.io/nlsp").rstrip("/")
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 (NASA Enterprise Knowledge Ingestion)"

DATA_TYPES = [
    ("experiments", "EXPERIMENTS", "Experiments", "#0284c7"),
    ("datasets", "DATASETS", "Datasets", "#059669"),
    ("missions", "MISSIONS", "Missions", "#7c3aed"),
    ("hardware", "HARDWARE", "Hardware", "#d97706"),
    ("documents", "DOCUMENTS", "Documents", "#dc2626"),
    ("personnel", "PERSONNEL", "Personnel", "#2563eb"),
    ("subjects", "SUBJECTS", "Subjects", "#4f46e5"),
    ("images", "IMAGES", "Images", "#db2777"),
    ("biospecimens", "BIOSPECIMEN", "Biospecimens", "#0d9488"),
]

TYPE_META = {t[0]: {"param": t[1], "label": t[2], "color": t[3]} for t in DATA_TYPES}


def make_request(url: str, data: bytes = None, headers: dict = None, max_retries: int = 5) -> bytes:
    """Send an HTTP request with exponential backoff."""
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    req = urllib.request.Request(url, data=data, headers=req_headers)

    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=35) as resp:
                return resp.read()
        except Exception as e:
            if attempt == max_retries - 1:
                print(f"[!] Request failed for {url}: {e}", file=sys.stderr)
                return b""
            sleep_time = (2 ** attempt) * 0.75
            time.sleep(sleep_time)
    return b""


def fetch_data_type_page(data_type: str, page: int, limit: int = 500) -> dict:
    """Fetch a single page of records for a given data type, using disk cache if fresh."""
    cache_path = os.path.join(RAW_CACHE_DIR, f"{data_type}_page_{page}.json")
    if os.path.exists(cache_path) and os.environ.get("FORCE_REFRESH") != "1":
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    url = f"{API_BASE}/{data_type}?page={page}&limit={limit}"
    raw = make_request(url)
    if not raw:
        return {}

    try:
        data = json.loads(raw.decode("utf-8", errors="ignore"))
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return data
    except Exception as e:
        print(f"[!] JSON parse error for {url}: {e}", file=sys.stderr)
        return {}


def harvest_all_records() -> dict:
    """Harvest all records across all 9 data types."""
    os.makedirs(RAW_CACHE_DIR, exist_ok=True)
    all_by_type = {}
    total_records_count = 0

    print("[*] Starting harvest from NASA Life Sciences Portal API (https://nlsp.nasa.gov/api/v1/data/)...")
    for data_type, type_param, label, color in DATA_TYPES:
        print(f"[*] Querying catalog for '{data_type}' ({label})...")
        first_page = fetch_data_type_page(data_type, page=1, limit=500)
        if not first_page:
            print(f"[!] Warning: Failed to retrieve first page for {data_type}")
            all_by_type[data_type] = []
            continue

        total = first_page.get("total", 0)
        total_pages = first_page.get("totalPages", 1)
        records = list(first_page.get("documents", []))
        print(f"    Total: {total:,} records across {total_pages} page(s)")

        if total_pages > 1:
            for p in range(2, total_pages + 1):
                page_data = fetch_data_type_page(data_type, page=p, limit=500)
                docs = page_data.get("documents", [])
                records.extend(docs)
                print(f"    Fetched page {p}/{total_pages} ({len(docs)} records)")
                time.sleep(0.1)

        all_by_type[data_type] = records
        total_records_count += len(records)
        print(f"    Completed '{data_type}': {len(records):,} records harvested")

    print(f"[+] Total records harvested across all types: {total_records_count:,}")
    return all_by_type


def sanitize_text(val) -> str:
    """Flatten and clean string/list values for display."""
    if val is None:
        return ""
    if isinstance(val, (list, tuple)):
        items = []
        for v in val:
            if isinstance(v, (list, tuple)):
                items.extend(str(x) for x in v if x is not None)
            elif v is not None:
                items.append(str(v))
        return ", ".join(dict.fromkeys(items))
    return str(val).strip()


def clean_html_content(raw_html) -> str:
    """Clean HTML descriptions for safe card presentation."""
    if not raw_html:
        return ""
    if isinstance(raw_html, (list, tuple)):
        raw_html = " ".join(str(x) for x in raw_html if x is not None)
    else:
        raw_html = str(raw_html)
    # Strip dangerous tags
    clean = re.sub(r'<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>', '', raw_html, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r'on\w+\s*=\s*["\'][^"\']*["\']', '', clean, flags=re.IGNORECASE)
    # Convert unclosed paragraph tags or multiple brs
    clean = clean.replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&').replace('&quot;', '"')
    return clean.strip()


def extract_record_fields(data_type: str, doc: dict) -> dict:
    """Extract canonical fields based on data type."""
    rec_id = doc.get("id") or doc.get("_id") or doc.get("__dirid") or ""
    param = TYPE_META.get(data_type, {}).get("param", data_type.upper())
    type_label = TYPE_META.get(data_type, {}).get("label", data_type.title())
    color = TYPE_META.get(data_type, {}).get("color", "#0284c7")

    live_url = f"{LIVE_DETAIL_BASE}/{rec_id}?dataType={param}"
    mirror_url = f"{GH_PAGES_BASE}/search/data/details/{rec_id}?dataType={param}"

    title = ""
    description = ""
    ident = rec_id
    metadata = {}

    if data_type == "experiments":
        title = doc.get("experiment_title") or doc.get("__title") or f"Experiment {rec_id}"
        ident = doc.get("experiment_id") or sanitize_text(doc.get("experiment_identifier")) or rec_id
        description = doc.get("experiment_description") or doc.get("__description") or ""
        metadata["Identifier"] = ident
        metadata["Principal Investigator"] = sanitize_text(doc.get("PrincipalInvestigator") or doc.get("PI"))
        metadata["Center"] = sanitize_text(doc.get("center"))
        metadata["Agency"] = sanitize_text(doc.get("agency"))
        metadata["Program"] = sanitize_text(doc.get("program_name") or doc.get("Program"))
        metadata["Research Area"] = sanitize_text(doc.get("research_area"))
        metadata["Missions"] = sanitize_text(doc.get("missions") or doc.get("mission_id"))
        metadata["Species"] = sanitize_text(doc.get("CombinedSpecies") or doc.get("species"))
        metadata["DOI"] = sanitize_text(doc.get("__doi"))
        metadata["Archive Status"] = sanitize_text(doc.get("archive_status"))
        metadata["Proposal Source"] = sanitize_text(doc.get("proposal_source"))

    elif data_type == "datasets":
        title = doc.get("dataset_catalog") or doc.get("experiment_title") or doc.get("__title") or f"Dataset {rec_id}"
        ident = doc.get("dataset_id") or doc.get("file_name") or rec_id
        description = doc.get("__description") or doc.get("dataset_description") or sanitize_text(doc.get("parms")) or ""
        metadata["Dataset ID"] = ident
        metadata["Associated Experiment"] = sanitize_text(doc.get("experiment_title"))
        metadata["Mission"] = sanitize_text(doc.get("mission_id"))
        metadata["Availability"] = sanitize_text(doc.get("availability"))
        metadata["Platform"] = sanitize_text(doc.get("platform_name") or doc.get("spacecraft"))
        metadata["Species"] = sanitize_text(doc.get("species_science_name") or doc.get("species"))

    elif data_type == "missions":
        title = doc.get("mission_id") or doc.get("program_name") or doc.get("__title") or f"Mission {rec_id}"
        ident = doc.get("mission_id") or rec_id
        description = doc.get("description") or doc.get("program_descrp") or ""
        metadata["Mission ID"] = ident
        metadata["Program"] = sanitize_text(doc.get("program_name"))
        metadata["Launch Year"] = sanitize_text(doc.get("year"))
        metadata["Duration"] = sanitize_text(doc.get("duration_range") or doc.get("flight_duration"))
        metadata["Species Flown"] = sanitize_text(doc.get("Species"))

    elif data_type == "hardware":
        title = doc.get("hardware_name") or doc.get("__title") or f"Hardware {rec_id}"
        ident = doc.get("hardware_id") or doc.get("part_number") or rec_id
        description = doc.get("hardware_description") or doc.get("config_description") or ""
        metadata["Hardware Name"] = title
        metadata["Associated Mission"] = sanitize_text(doc.get("mission_id"))
        metadata["Associated Experiment"] = sanitize_text(doc.get("experiment_title"))
        metadata["Configuration"] = sanitize_text(doc.get("config_name"))
        metadata["Manufacturer"] = sanitize_text(doc.get("manufacturer"))

    elif data_type == "documents":
        title = doc.get("document_title") or doc.get("filename") or doc.get("__title") or f"Document {rec_id}"
        ident = doc.get("document_number") or rec_id
        description = doc.get("document_description") or ""
        metadata["Document Number"] = ident
        metadata["Document Type"] = sanitize_text(doc.get("type"))
        metadata["Project Name"] = sanitize_text(doc.get("project_name"))
        metadata["Creator"] = sanitize_text(doc.get("creator"))
        metadata["Publication Date"] = sanitize_text(doc.get("publication_date"))
        metadata["Availability"] = sanitize_text(doc.get("availability"))

    elif data_type == "personnel":
        title = sanitize_text(doc.get("full_name") or doc.get("degree_lastname") or doc.get("__title") or f"Personnel {rec_id}")
        ident = doc.get("per_id") or rec_id
        description = f"Personnel entry for {title}. Affiliated institution: {sanitize_text(doc.get('institution'))} ({sanitize_text(doc.get('country'))})."
        metadata["Full Name"] = title
        metadata["Degree"] = sanitize_text(doc.get("degree"))
        metadata["Institution"] = sanitize_text(doc.get("institution"))
        metadata["Country"] = sanitize_text(doc.get("country"))
        metadata["Role"] = sanitize_text(doc.get("pme_role_name") or doc.get("role"))
        metadata["Associated Experiment"] = sanitize_text(doc.get("experiment_title"))

    elif data_type == "subjects":
        title = sanitize_text(doc.get("subject_sci_name") or doc.get("subject_species") or doc.get("__title") or f"Subject {rec_id}")
        ident = rec_id
        description = doc.get("subject_description") or f"Research subject record for {title}."
        metadata["Scientific Name"] = sanitize_text(doc.get("subject_sci_name"))
        metadata["Common Species"] = sanitize_text(doc.get("subject_species"))
        metadata["Payload ID"] = sanitize_text(doc.get("payload_id"))
        metadata["Mission ID"] = sanitize_text(doc.get("mission_id"))

    elif data_type == "images":
        title = doc.get("image_name") or doc.get("__title") or f"Image {rec_id}"
        ident = rec_id
        description = doc.get("caption") or doc.get("description") or f"NASA Life Sciences imagery record for {title}."
        metadata["Image Name"] = title
        metadata["Mission"] = sanitize_text(doc.get("mission_id"))
        metadata["Program"] = sanitize_text(doc.get("program_name"))
        metadata["Keywords"] = sanitize_text(doc.get("keyword"))
        metadata["Thumbnail URL"] = sanitize_text(doc.get("thumbnail_url") or doc.get("file_thumb"))

    elif data_type == "biospecimens":
        title = sanitize_text(doc.get("bio_name") or doc.get("tissue_medium") or doc.get("storage_medium_id") or f"Biospecimen {rec_id}")
        ident = doc.get("bio_id") or rec_id
        description = f"Biological specimen archive entry for {title}. Protocol: {sanitize_text(doc.get('protocol'))}."
        metadata["Biospecimen ID"] = ident
        metadata["Tissue/Medium"] = sanitize_text(doc.get("tissue_medium"))
        metadata["Storage Medium"] = sanitize_text(doc.get("storage_medium_id"))
        metadata["Protocol"] = sanitize_text(doc.get("protocol"))
        metadata["Session Type"] = sanitize_text(doc.get("session_type"))
        metadata["Mission"] = sanitize_text(doc.get("mission_id"))

    # Remove empty metadata entries
    clean_meta = {k: v for k, v in metadata.items() if v and v != "None" and v != "N/A"}

    # Extract lastmod date
    lastmod = doc.get("__record_modified_date") or doc.get("__record_creation_date") or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if "T" in str(lastmod):
        lastmod = str(lastmod).split("T")[0]

    clean_title = sanitize_text(title) or f"{type_label} Record {rec_id}"
    clean_ident = sanitize_text(ident) or rec_id

    return {
        "id": rec_id,
        "data_type": data_type,
        "type_param": param,
        "type_label": type_label,
        "color": color,
        "title": clean_title,
        "ident": clean_ident,
        "description": clean_html_content(description),
        "metadata": clean_meta,
        "lastmod": lastmod,
        "live_url": live_url,
        "mirror_url": mirror_url,
    }


def render_html_page(item: dict) -> str:
    """Render a high-fidelity static HTML card for an NLSP record."""
    meta_rows = []
    for k, v in item["metadata"].items():
        meta_rows.append(f"""
        <tr>
          <th>{escape(k)}</th>
          <td>{escape(str(v))}</td>
        </tr>""")
    meta_table_html = "".join(meta_rows) if meta_rows else "<tr><td colspan='2'>No additional parameters documented.</td></tr>"

    desc_html = item["description"] if item["description"] else "<p><em>No detailed description provided in catalog record.</em></p>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{escape(item['title'])} - NASA Life Sciences Portal</title>
  <link rel="canonical" href="{escape(item['live_url'])}">
  <style>
    :root {{
      --primary: #0b3d91;
      --primary-dark: #061f4a;
      --accent: {item['color']};
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.6;
      padding: 20px;
    }}
    .container {{
      max-width: 900px;
      margin: 0 auto;
    }}
    .breadcrumb {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .breadcrumb a {{
      color: var(--primary);
      text-decoration: none;
    }}
    .breadcrumb a:hover {{
      text-decoration: underline;
    }}
    .card {{
      background: var(--card-bg);
      border-radius: 12px;
      border: 1px solid var(--border);
      box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
      overflow: hidden;
      margin-bottom: 24px;
    }}
    .header {{
      background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
      color: #ffffff;
      padding: 32px 28px;
    }}
    .badge {{
      display: inline-block;
      background: var(--accent);
      color: #ffffff;
      font-size: 0.75rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 4px 10px;
      border-radius: 9999px;
      margin-bottom: 12px;
      letter-spacing: 0.05em;
    }}
    h1 {{
      font-size: 1.65rem;
      font-weight: 700;
      line-height: 1.3;
      margin-bottom: 12px;
    }}
    .meta-id {{
      font-size: 0.9rem;
      opacity: 0.85;
      font-family: monospace;
    }}
    .content {{
      padding: 28px;
    }}
    .action-banner {{
      background: #eff6ff;
      border-left: 4px solid var(--primary);
      padding: 16px 20px;
      margin-bottom: 24px;
      border-radius: 0 8px 8px 0;
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 12px;
    }}
    .action-banner-text {{
      font-size: 0.9rem;
      color: #1e3a8a;
    }}
    .btn {{
      display: inline-flex;
      align-items: center;
      background: var(--primary);
      color: #ffffff;
      font-weight: 600;
      font-size: 0.875rem;
      padding: 10px 18px;
      border-radius: 6px;
      text-decoration: none;
      transition: background 0.15s ease;
    }}
    .btn:hover {{
      background: var(--primary-dark);
    }}
    h2 {{
      font-size: 1.25rem;
      color: var(--primary-dark);
      border-bottom: 2px solid var(--border);
      padding-bottom: 8px;
      margin: 28px 0 16px 0;
    }}
    h2:first-of-type {{
      margin-top: 0;
    }}
    .description {{
      color: #334155;
      font-size: 0.95rem;
      margin-bottom: 24px;
    }}
    .description p {{ margin-bottom: 1em; }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      margin-bottom: 24px;
    }}
    th, td {{
      padding: 10px 14px;
      text-align: left;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
    }}
    th {{
      width: 25%;
      background: #f8fafc;
      font-weight: 600;
      color: #475569;
    }}
    td {{
      color: #0f172a;
    }}
    .footer {{
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-muted);
      margin-top: 32px;
    }}
    .footer a {{
      color: var(--primary);
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="container">
    <div class="breadcrumb">
      <a href="../../../index.html">NASA Life Sciences Portal</a> /
      <span>{escape(item['type_label'])}</span> /
      <span>{escape(item['ident'])}</span>
    </div>

    <div class="card">
      <div class="header">
        <span class="badge">{escape(item['type_label'])}</span>
        <h1>{escape(item['title'])}</h1>
        <div class="meta-id">Record ID: {escape(item['ident'])}</div>
      </div>

      <div class="content">
        <div class="action-banner">
          <div class="action-banner-text">
            <strong>Official Source:</strong> National Aeronautics and Space Administration Life Sciences Data Archive
          </div>
          <a href="{escape(item['live_url'])}" target="_blank" rel="noopener noreferrer" class="btn">
            View Official Record on NASA NLSP &rarr;
          </a>
        </div>

        <h2>Summary / Description</h2>
        <div class="description">
          {desc_html}
        </div>

        <h2>Technical Parameters & Metadata</h2>
        <table>
          <tbody>
            {meta_table_html}
          </tbody>
        </table>
      </div>
    </div>

    <div class="footer">
      NASA Life Sciences Portal (NLSP) &bull; Life Sciences Data Archive (LSDA) &bull; Lifetime Surveillance of Astronaut Health (LSAH)
      <br>
      Direct citation link: <a href="{escape(item['live_url'])}">{escape(item['live_url'])}</a>
    </div>
  </div>
</body>
</html>
"""


def render_index_html(stats_by_type: dict, all_items_summary: list) -> str:
    """Generate interactive, fast searchable catalog index.html."""
    total_records = sum(stats_by_type.values())
    pills = []
    pills.append(f'<button class="filter-pill active" data-type="all">All ({total_records:,})</button>')
    for dt, param, label, color in DATA_TYPES:
        cnt = stats_by_type.get(dt, 0)
        pills.append(f'<button class="filter-pill" data-type="{dt}">{label} ({cnt:,})</button>')
    pills_html = "\n".join(pills)

    # Embed sample catalog for fast client-side searching
    json_catalog = json.dumps(all_items_summary[:3500], ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NASA Life Sciences Portal (NLSP) Mirror & Catalog</title>
  <style>
    :root {{
      --primary: #0b3d91;
      --primary-dark: #061f4a;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 24px 16px;
    }}
    .container {{
      max-width: 1140px;
      margin: 0 auto;
    }}
    header {{
      background: linear-gradient(135deg, var(--primary-dark) 0%, var(--primary) 100%);
      color: #ffffff;
      border-radius: 12px;
      padding: 36px 32px;
      margin-bottom: 24px;
      box-shadow: 0 4px 12px rgba(11, 61, 145, 0.15);
    }}
    h1 {{ font-size: 2rem; margin-bottom: 8px; }}
    p.lead {{ font-size: 1rem; opacity: 0.9; max-width: 800px; }}
    .stats-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 16px;
      margin-top: 20px;
    }}
    .stat-badge {{
      background: rgba(255, 255, 255, 0.15);
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.85rem;
      font-weight: 500;
    }}
    .controls {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 16px 20px;
      margin-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    .search-box {{
      width: 100%;
      padding: 12px 16px;
      font-size: 1rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      outline: none;
    }}
    .search-box:focus {{
      border-color: var(--primary);
      box-shadow: 0 0 0 3px rgba(11, 61, 145, 0.1);
    }}
    .filter-pills {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .filter-pill {{
      background: #f1f5f9;
      color: #475569;
      border: none;
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.825rem;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }}
    .filter-pill:hover {{ background: #e2e8f0; }}
    .filter-pill.active {{ background: var(--primary); color: #ffffff; }}
    .results-count {{
      font-size: 0.875rem;
      color: var(--text-muted);
      margin-bottom: 16px;
    }}
    .cards-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 16px;
    }}
    .item-card {{
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 20px;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      transition: transform 0.1s, box-shadow 0.1s;
    }}
    .item-card:hover {{
      transform: translateY(-2px);
      box-shadow: 0 6px 12px rgba(0, 0, 0, 0.05);
    }}
    .item-type {{
      display: inline-block;
      font-size: 0.7rem;
      font-weight: 700;
      text-transform: uppercase;
      padding: 3px 8px;
      border-radius: 4px;
      color: #ffffff;
      margin-bottom: 8px;
      letter-spacing: 0.04em;
    }}
    .item-title {{
      font-size: 1.05rem;
      font-weight: 600;
      margin-bottom: 8px;
      line-height: 1.35;
    }}
    .item-meta {{
      font-size: 0.825rem;
      color: var(--text-muted);
      margin-bottom: 12px;
      flex-grow: 1;
    }}
    .item-links {{
      display: flex;
      gap: 10px;
      margin-top: 12px;
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }}
    .item-link {{
      font-size: 0.825rem;
      font-weight: 600;
      text-decoration: none;
      color: var(--primary);
    }}
    .item-link:hover {{ text-decoration: underline; }}
    .sitemaps-box {{
      background: #eff6ff;
      border: 1px solid #bfdbfe;
      border-radius: 10px;
      padding: 20px;
      margin-top: 36px;
    }}
    .sitemaps-box h3 {{
      font-size: 1.1rem;
      color: #1e3a8a;
      margin-bottom: 10px;
    }}
    .sitemaps-box ul {{
      margin-left: 20px;
      font-size: 0.9rem;
      color: #1e40af;
    }}
    .sitemaps-box li {{ margin-bottom: 6px; }}
    .sitemaps-box a {{ color: #1d4ed8; font-weight: 600; text-decoration: none; }}
    .sitemaps-box a:hover {{ text-decoration: underline; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <h1>NASA Life Sciences Portal (NLSP) Catalog Mirror</h1>
      <p class="lead">
        Static knowledge mirror and high-throughput RAG search ingestion catalog for NASA's Life Sciences Data Archive (LSDA),
        Lifetime Surveillance of Astronaut Health (LSAH), and space medicine research.
      </p>
      <div class="stats-bar">
        <span class="stat-badge">Total Records: {total_records:,}</span>
        <span class="stat-badge">Experiments: {stats_by_type.get('experiments', 0):,}</span>
        <span class="stat-badge">Datasets: {stats_by_type.get('datasets', 0):,}</span>
        <span class="stat-badge">Missions: {stats_by_type.get('missions', 0):,}</span>
        <span class="stat-badge">Hardware: {stats_by_type.get('hardware', 0):,}</span>
        <span class="stat-badge">Documents: {stats_by_type.get('documents', 0):,}</span>
        <span class="stat-badge">Biospecimens: {stats_by_type.get('biospecimens', 0):,}</span>
      </div>
    </header>

    <div class="controls">
      <input type="text" id="searchInput" class="search-box" placeholder="Search by title, investigator, mission, organism, hardware...">
      <div class="filter-pills" id="filterPills">
        {pills_html}
      </div>
    </div>

    <div class="results-count" id="resultsCount">Showing records...</div>

    <div class="cards-grid" id="cardsGrid">
      <!-- Dynamic Javascript Content -->
    </div>

    <div class="sitemaps-box">
      <h3>Machine-Readable Endpoints & Sitemaps</h3>
      <ul>
        <li><strong>Primary XML Sitemap (Mirror URLs for Onyx):</strong> <a href="sitemap.xml">sitemap.xml</a></li>
        <li><strong>Direct NASA XML Sitemap (Live URLs):</strong> <a href="nlsp_direct_sitemap.xml">nlsp_direct_sitemap.xml</a></li>
        <li><strong>Plain Text URL List:</strong> <a href="nlsp_urls.txt">nlsp_urls.txt</a></li>
        <li><strong>Unified JSONL Dataset:</strong> <a href="nlsp_records.jsonl">nlsp_records.jsonl</a></li>
      </ul>
    </div>
  </div>

  <script>
    const CATALOG = {json_catalog};
    const COLORS = {{
      experiments: "#0284c7",
      datasets: "#059669",
      missions: "#7c3aed",
      hardware: "#d97706",
      documents: "#dc2626",
      personnel: "#2563eb",
      subjects: "#4f46e5",
      images: "#db2777",
      biospecimens: "#0d9488"
    }};

    let currentFilter = "all";
    let searchQuery = "";

    const searchInput = document.getElementById("searchInput");
    const filterPills = document.getElementById("filterPills");
    const cardsGrid = document.getElementById("cardsGrid");
    const resultsCount = document.getElementById("resultsCount");

    function renderCards() {{
      const q = searchQuery.toLowerCase().trim();
      const filtered = CATALOG.filter(item => {{
        const matchesType = (currentFilter === "all" || item.type === currentFilter);
        const matchesSearch = !q || item.title.toLowerCase().includes(q) || (item.meta && item.meta.toLowerCase().includes(q));
        return matchesType && matchesSearch;
      }});

      resultsCount.textContent = `Showing ${{filtered.length.toLocaleString()}} records (search catalog view)`;

      if (filtered.length === 0) {{
        cardsGrid.innerHTML = '<div style="grid-column: 1/-1; padding: 40px; text-align: center; color: #64748b;">No records match your search criteria.</div>';
        return;
      }}

      cardsGrid.innerHTML = filtered.slice(0, 100).map(item => `
        <div class="item-card">
          <div>
            <span class="item-type" style="background: ${{COLORS[item.type] || '#0284c7'}}">${{item.label}}</span>
            <h3 class="item-title">${{item.title}}</h3>
            <div class="item-meta">${{item.meta || ''}}</div>
          </div>
          <div class="item-links">
            <a href="search/data/details/${{item.id}}.html" class="item-link">Card Mirror &rarr;</a>
            <a href="${{item.live_url}}" target="_blank" rel="noopener noreferrer" class="item-link">NASA Portal &nearr;</a>
          </div>
        </div>
      `).join("");
    }}

    searchInput.addEventListener("input", e => {{
      searchQuery = e.target.value;
      renderCards();
    }});

    filterPills.addEventListener("click", e => {{
      const btn = e.target.closest(".filter-pill");
      if (!btn) return;
      document.querySelectorAll(".filter-pill").forEach(p => p.classList.remove("active"));
      btn.classList.add("active");
      currentFilter = btn.dataset.type;
      renderCards();
    }});

    renderCards();
  </script>
</body>
</html>
"""


def main():
    print("=" * 80)
    print(" NASA Life Sciences Portal (NLSP) Harvester & Static Mirror Generator")
    print("=" * 80)

    # 1. Harvest raw records from API
    all_by_type = harvest_all_records()

    # 2. Extract and process items
    print("\n[*] Processing records into canonical cards and metadata...")
    processed_items = []
    stats_by_type = {}
    catalog_summary = []

    for data_type, records in all_by_type.items():
        stats_by_type[data_type] = len(records)
        for doc in records:
            item = extract_record_fields(data_type, doc)
            if item["id"]:
                processed_items.append(item)
                # Brief metadata summary for index.html client search
                meta_str = " | ".join(f"{k}: {v}" for k, v in list(item["metadata"].items())[:3])
                catalog_summary.append({
                    "id": item["id"],
                    "type": item["data_type"],
                    "label": item["type_label"],
                    "title": item["title"],
                    "meta": meta_str,
                    "live_url": item["live_url"],
                })

    print(f"[+] Successfully extracted {len(processed_items):,} canonical records.")

    # 3. Render HTML cards to disk
    print(f"\n[*] Rendering {len(processed_items):,} HTML cards and extensionless mirrors to {DETAILS_DIR}...")
    os.makedirs(DETAILS_DIR, exist_ok=True)

    t0 = time.time()
    for idx, item in enumerate(processed_items, start=1):
        html_content = render_html_page(item)
        rec_id = item["id"]
        html_file = os.path.join(DETAILS_DIR, f"{rec_id}.html")

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_content)

        if idx % 5000 == 0 or idx == len(processed_items):
            print(f"    Rendered {idx:,}/{len(processed_items):,} cards ({time.time() - t0:.1f}s)")

    print(f"[+] Completed rendering {len(processed_items):,} cards in {time.time() - t0:.1f} seconds.")

    # 4. Generate Sitemaps & URL lists
    print("\n[*] Generating XML sitemaps and plain text URL lists...")
    sitemap_entries = []
    direct_sitemap_entries = []
    mirror_urls = []
    direct_urls = []

    for item in processed_items:
        mirror_urls.append(item["mirror_url"])
        direct_urls.append(item["live_url"])
        sitemap_entries.append(
            f"  <url>\n    <loc>{escape(item['mirror_url'])}</loc>\n    <lastmod>{item['lastmod']}</lastmod>\n    <changefreq>monthly</changefreq>\n  </url>"
        )
        direct_sitemap_entries.append(
            f"  <url>\n    <loc>{escape(item['live_url'])}</loc>\n    <lastmod>{item['lastmod']}</lastmod>\n    <changefreq>monthly</changefreq>\n  </url>"
        )

    # Primary XML Sitemap (Mirror URLs for Onyx)
    sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(sitemap_entries)}
</urlset>
"""
    with open(SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    with open(SITEMAP_ALIAS_FILE, "w", encoding="utf-8") as f:
        f.write(sitemap_xml)
    print(f"[+] Wrote primary XML sitemap ({len(sitemap_entries):,} URLs) to {SITEMAP_FILE}")

    # Direct NASA XML Sitemap
    direct_sitemap_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(direct_sitemap_entries)}
</urlset>
"""
    with open(DIRECT_SITEMAP_FILE, "w", encoding="utf-8") as f:
        f.write(direct_sitemap_xml)
    print(f"[+] Wrote direct NASA XML sitemap to {DIRECT_SITEMAP_FILE}")

    # Text lists
    with open(URLS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(mirror_urls) + "\n")
    with open(DIRECT_URLS_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(direct_urls) + "\n")
    print(f"[+] Wrote URL lists to {URLS_FILE} and {DIRECT_URLS_FILE}")

    # 5. Generate JSONL Dataset
    print(f"\n[*] Writing unified JSONL dataset to {JSONL_FILE}...")
    with open(JSONL_FILE, "w", encoding="utf-8") as f:
        for item in processed_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"[+] Wrote {len(processed_items):,} JSONL records to {JSONL_FILE}")

    # 6. Generate Index Catalog HTML
    print(f"\n[*] Generating client-side searchable catalog index.html...")
    index_content = render_index_html(stats_by_type, catalog_summary)
    with open(INDEX_HTML, "w", encoding="utf-8") as f:
        f.write(index_content)
    print(f"[+] Wrote interactive catalog to {INDEX_HTML}")

    print("\n" + "=" * 80)
    print(" HARVEST & BUILD SUMMARY:")
    for dt, cnt in stats_by_type.items():
        label = TYPE_META.get(dt, {}).get("label", dt)
        print(f"  - {label:15}: {cnt:>6,} records")
    print(f"  TOTAL RECORDS    : {len(processed_items):>6,}")
    print("=" * 80)


if __name__ == "__main__":
    main()
