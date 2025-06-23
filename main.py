# main.py
import os
import sys
import time
import re
import yaml
import argparse
import warnings
import calendar
from datetime import datetime, timedelta

import pandas as pd
import requests
from google.cloud import bigquery
from google.cloud.exceptions import NotFound
from tabulate import tabulate

# --- Initial Setup ---
warnings.filterwarnings("ignore", category=UserWarning, module="google.cloud.bigquery_storage")
sys.stdout.reconfigure(encoding='utf-8')

print("✅ Starting GCP Cost Alerting Script (Production Version with Restored Formatting)")

# ... (All functions like clean_currency, format_diff, send_slack_message, run_global_query, etc., remain unchanged) ...

# ---------- Utility Functions ----------
def clean_currency(val):
    return f"${val:,.2f}"

def format_diff(last_month_total, this_month_total, days_so_far, last_month_days):
    try:
        if last_month_total == 0 or days_so_far == 0: return "", 0.0
        expected_so_far = (last_month_total / last_month_days) * days_so_far
        if expected_so_far == 0: return " (↑ ∞%) 🔴" if this_month_total > 0 else " (→ 0.00%)", 0.0
        percent_diff = ((this_month_total / expected_so_far) - 1) * 100
        if percent_diff > 0: return f" (↑{abs(percent_diff):.2f}%) 🔴", percent_diff
        elif percent_diff < 0: return f" (↓{abs(percent_diff):.2f}%) 🟢", percent_diff
        else: return f" (→ 0.00%)", percent_diff
    except Exception as e:
        print(f"⚠️ Error in format_diff: {e}")
        return " N/A", 0.0

# ---------- Category 1: Resilience and Error Handling ----------

def send_slack_message(text: str, channel_id: str, thread_ts: str = None):
    token = os.getenv("SLACK_BOT_TOKEN")
    if not token or not channel_id:
        print("❌ Missing SLACK_BOT_TOKEN or channel_id. Cannot send message.")
        return None

    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"channel": channel_id, "text": text, "thread_ts": thread_ts}
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"📤 Sending message to Slack channel {channel_id} (Attempt {attempt + 1})...")
            response = requests.post("https://slack.com/api/chat.postMessage", headers=headers, json=payload, timeout=15)
            response.raise_for_status()
            r_json = response.json()
            if r_json.get("ok"):
                print("✅ Sent to Slack")
                return r_json.get("ts")
            else:
                print(f"❌ Slack API Error: {r_json.get('error', 'Unknown error')}")
        except requests.exceptions.RequestException as e:
            print(f"❌ Slack API Request Error: {e}")
        
        if attempt < max_retries - 1:
            print(f"   Retrying in 5 seconds...")
            time.sleep(5)
    
    print(f"❌ Failed to send message to {channel_id} after {max_retries} attempts.")
    return None

def run_global_query(query: str, client: bigquery.Client):
    job_config = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
    try:
        dry_run_job = client.query(query, job_config=job_config)
        bytes_to_process = dry_run_job.total_bytes_processed
        cost_usd = (bytes_to_process / (1024**4)) * 6.25 if bytes_to_process else 0
        print(f"💡 BigQuery Dry Run: This query will process {bytes_to_process/1e9:.2f} GB. Estimated cost: ${cost_usd:.4f}")
    except Exception as e:
        print(f"⚠️ Could not perform BigQuery dry run: {e}")

    print("🚀 Running BigQuery query...")
    results = client.query(query).result()
    return results.to_dataframe()

def validate_dataframe(df: pd.DataFrame):
    required_cols = {'project_id', 'service_id', 'service_description', 'sku_description', 'usage_date', 'subtotal'}
    missing_cols = required_cols - set(df.columns)
    if missing_cols:
        print(f"❌ FATAL: Input data is missing required columns: {missing_cols}")
        sys.exit(1)
    print("✅ Input data validation passed.")


# ---------- PHASE 2: Report Generation (Logic mostly unchanged) ----------

def generate_service_summary_table(df_last: pd.DataFrame, df_this: pd.DataFrame, days_so_far: int, last_month_days: int, recent_days: list):
    last_services = df_last.groupby('service_description')['subtotal'].sum()
    this_services = df_this.groupby('service_description')['subtotal'].sum()
    all_service_names = sorted(set(last_services.index) | set(this_services.index), key=lambda s: this_services.get(s, 0), reverse=True)
    table_data = []
    headers = ["Service", "Last Month", "This Month ( %diff )"] + [d.strftime('%Y-%m-%d') for d in recent_days]

    for service in all_service_names:
        last, curr = last_services.get(service, 0.0), this_services.get(service, 0.0)
        if last <= 1 and curr <= 1: continue
        diff_str, _ = format_diff(last, curr, days_so_far, last_month_days)
        daily_vals = [clean_currency(df_this[(df_this['service_description'] == service) & (df_this['usage_date'] == d.strftime('%Y-%m-%d'))]['subtotal'].sum()) for d in recent_days]
        table_data.append([service, clean_currency(last), f"{clean_currency(curr)}{diff_str}", *daily_vals])

    grand_total_last, grand_total_this = last_services.sum(), this_services.sum()
    total_diff_str, _ = format_diff(grand_total_last, grand_total_this, days_so_far, last_month_days)
    total_daily = [clean_currency(df_this[df_this['usage_date'] == d.strftime('%Y-%m-%d')]['subtotal'].sum()) for d in recent_days]
    table_data.append(["-"] * len(headers))
    table_data.append(["Total", clean_currency(grand_total_last), f"{clean_currency(grand_total_this)}{total_diff_str}", *total_daily])
    return tabulate(table_data, headers=headers, tablefmt="plain", numalign="right", stralign="left")

def generate_sku_breakdown_table(service_id: str, service_name: str, df_last: pd.DataFrame, df_this: pd.DataFrame, days_so_far: int, last_month_days: int, recent_days: list):
    df_last_svc = df_last[df_last['service_id'] == service_id]
    df_this_svc = df_this[df_this['service_id'] == service_id]
    if df_this_svc.empty and df_last_svc.empty: return ""

    if service_name == "Compute Engine":
        print("   -> Applying advanced aggregation for Compute Engine...")
        
        def categorize_sku(sku_description):
            sku_lower = sku_description.lower()
            if 'local ssd' in sku_lower or 'local storage' in sku_lower:
                return 'Storage: Local SSD/Storage (Committed Use)' if 'commitment' in sku_lower else 'Storage: Local SSD/Storage (On-Demand)'
            if ' ram ' in sku_lower or 'instance ram' in sku_lower or 'memory' in sku_lower:
                if 'spot' in sku_lower or 'preemptible' in sku_lower: return 'VM RAM (Spot/Preemptible)'
                elif 'commitment' in sku_lower: return 'VM RAM (Committed Use)'
                else: return 'VM RAM (On-Demand)'
            if 'instance core' in sku_lower or 'cpu' in sku_lower:
                if 'spot' in sku_lower or 'preemptible' in sku_lower: return 'VM Core Hours (Spot/Preemptible)'
                elif 'commitment' in sku_lower: return 'VM Core Hours (Committed Use)'
                else: return 'VM Core Hours (On-Demand)'
            if 'storage pd' in sku_lower or 'persistent disk' in sku_lower:
                return 'Storage: PD Snapshots' if 'snapshot' in sku_lower else 'Storage: Persistent Disk'
            if 'data transfer' in sku_lower: return 'Network: Data Transfer'
            if 'ip address' in sku_lower: return 'Network: IP Addresses'
            if 'license' in sku_lower or 'licensing fee' in sku_lower: return 'Licenses'
            if 'router' in sku_lower: return 'Network: Cloud Router'
            return 'Other'

        df_last_svc.loc[:, 'Category'] = df_last_svc['sku_description'].apply(categorize_sku)
        df_this_svc.loc[:, 'Category'] = df_this_svc['sku_description'].apply(categorize_sku)
        
        grouping_key = 'Category'
        header_name = "Aggregated Category"
        last_costs = df_last_svc.groupby(grouping_key)['subtotal'].sum()
        this_costs = df_this_svc.groupby(grouping_key)['subtotal'].sum()
        
        category_order = [
            'VM Core Hours (On-Demand)', 'VM Core Hours (Committed Use)', 'VM Core Hours (Spot/Preemptible)',
            'VM RAM (On-Demand)', 'VM RAM (Committed Use)', 'VM RAM (Spot/Preemptible)',
            'Storage: Local SSD/Storage (On-Demand)', 'Storage: Local SSD/Storage (Committed Use)',
            'Storage: Persistent Disk', 'Storage: PD Snapshots',
            'Network: Data Transfer', 'Network: IP Addresses', 'Network: Cloud Router',
            'Licenses', 'Other'
        ]
        category_sort_map = {cat: i for i, cat in enumerate(category_order)}
        all_items = sorted(set(last_costs.index) | set(this_costs.index), key=lambda s: category_sort_map.get(s, 99))

    else: # For all other services
        grouping_key = 'sku_description'
        header_name = "SKU Description"
        last_costs = df_last_svc.groupby(grouping_key)['subtotal'].sum()
        this_costs = df_this_svc.groupby(grouping_key)['subtotal'].sum()
        all_items = sorted(set(last_costs.index) | set(this_costs.index), key=lambda s: this_costs.get(s, 0), reverse=True)

    table_rows = []
    date_columns = [d.strftime('%Y-%m-%d') for d in recent_days]
    headers = [header_name, "Last Month", "This Month ( %diff )"] + date_columns

    for item in all_items:
        last, curr = last_costs.get(item, 0.0), this_costs.get(item, 0.0)
        if last <= 1 and curr <= 1: continue
        diff_str, _ = format_diff(last, curr, days_so_far, last_month_days)
        daily_vals = [clean_currency(df_this_svc.loc[df_this_svc[grouping_key] == item, 'subtotal'].sum()) for _ in date_columns]
        table_rows.append([item, clean_currency(last), f"{clean_currency(curr)}{diff_str}", *daily_vals])

    if not table_rows: return ""

    grand_total_last, grand_total_this = df_last_svc['subtotal'].sum(), df_this_svc['subtotal'].sum()
    total_diff_str, _ = format_diff(grand_total_last, grand_total_this, days_so_far, last_month_days)
    total_daily_vals = [clean_currency(df_this_svc[df_this_svc['usage_date'] == day_str]['subtotal'].sum()) for day_str in date_columns]
    table_rows.append(['-'] * len(headers))
    table_rows.append(["Total", clean_currency(grand_total_last), f"{clean_currency(grand_total_this)}{total_diff_str}", *total_daily_vals])
    return tabulate(table_rows, headers=headers, tablefmt="plain", numalign="right", stralign="left")

# ---------- Main Execution Logic ----------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GCP Cost Alerting Script")
    parser.add_argument('--config', type=str, default='config.yaml', help="Path to the configuration YAML file.")
    parser.add_argument('--force-refresh', action='store_true', help="Force a new BigQuery query, ignoring existing backup files for today.")
    args = parser.parse_args()

    try:
        with open(args.config, 'r') as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"❌ FATAL: Configuration file not found at '{args.config}'")
        sys.exit(1)
    except Exception as e:
        print(f"❌ FATAL: Error parsing YAML configuration file: {e}")
        sys.exit(1)
        
    BIGQUERY_BILLING_TABLE = config.get('bigquery_billing_table')
    BACKUP_DIR = config.get('backup_directory')
    DEFAULT_CHANNEL_ID = config.get('default_slack_channel_id')
    PROJECTS_TO_MONITOR = config.get('projects', [])

    if not all([BIGQUERY_BILLING_TABLE, BACKUP_DIR, DEFAULT_CHANNEL_ID, PROJECTS_TO_MONITOR]):
        print("❌ FATAL: One or more required keys are missing from the config file.")
        sys.exit(1)

    now = datetime.utcnow().date()
    today_str = now.strftime('%Y-%m-%d')
    first_of_this_month = now.replace(day=1)
    last_day_of_last_month = first_of_this_month - timedelta(days=1)
    first_of_last_month = last_day_of_last_month.replace(day=1)
    end_of_this_month_day = calendar.monthrange(now.year, now.month)[1]
    last_month_days = calendar.monthrange(first_of_last_month.year, first_of_last_month.month)[1]
    days_so_far = now.day
    recent_days = sorted([now - timedelta(days=i) for i in range(3, 0, -1)])

    os.makedirs(BACKUP_DIR, exist_ok=True)
    this_month_file = os.path.join(BACKUP_DIR, f"costs_this_month_{today_str}.csv")
    last_month_file = os.path.join(BACKUP_DIR, f"costs_last_month_{last_day_of_last_month.strftime('%Y-%m')}.csv")

    bq_client = bigquery.Client()
    query_template = """
        SELECT project.id as project_id, project.name as project_name, service.id as service_id, 
               service.description as service_description, sku.description as sku_description, 
               DATE(usage_start_time) AS usage_date,
               SUM(cost) + SUM(IFNULL((SELECT SUM(c.amount) FROM UNNEST(credits) c), 0)) AS subtotal
        FROM `{table}` WHERE usage_start_time >= TIMESTAMP('{start}') AND usage_start_time < TIMESTAMP('{end}')
        AND cost_type NOT IN ('tax', 'adjustment') GROUP BY 1, 2, 3, 4, 5, 6
    """

    for period, file_path, start_date, end_date in [
        ("This Month", this_month_file, first_of_this_month.isoformat(), (now + timedelta(days=1)).isoformat()),
        ("Last Month", last_month_file, first_of_last_month.isoformat(), first_of_this_month.isoformat())
    ]:
        df_name = f"df_{period.lower().replace(' ', '_')}_full"
        if os.path.exists(file_path) and not args.force_refresh:
            print(f"✅ Found existing data for {period}, loading from cache: {file_path}")
            globals()[df_name] = pd.read_csv(file_path)
        else:
            if args.force_refresh:
                print(f"CACHE OVERRIDE: Re-fetching data for {period} due to --force-refresh flag.")
            else:
                print(f"No cache found for {period}, fetching data from BigQuery.")
            
            query = query_template.format(table=BIGQUERY_BILLING_TABLE, start=start_date, end=end_date)
            df = run_global_query(query, bq_client)
            df.to_csv(file_path, index=False)
            print(f"   Saved data for {period} to {file_path}")
            globals()[df_name] = df
            
    validate_dataframe(df_this_month_full)
    validate_dataframe(df_last_month_full)
    
    df_this_month_full['usage_date'] = pd.to_datetime(df_this_month_full['usage_date']).dt.strftime('%Y-%m-%d')
    df_last_month_full['usage_date'] = pd.to_datetime(df_last_month_full['usage_date']).dt.strftime('%Y-%m-%d')
    
    print("\n" + "="*50 + "\n✅ Global data ready. Starting per-project processing...\n" + "="*50 + "\n")

    for project in PROJECTS_TO_MONITOR:
        project_id, project_name = project['id'], project['name']
        channel_id = project.get('slack_channel_id', DEFAULT_CHANNEL_ID)
        print(f"\nProcessing Project: {project_name} ({project_id}) -> Slack Channel: {channel_id}")

        df_this_project = df_this_month_full[df_this_month_full['project_id'] == project_id].copy()
        df_last_project = df_last_month_full[df_last_month_full['project_id'] == project_id].copy()

        this_month_total = df_this_project['subtotal'].sum()
        last_month_total = df_last_project['subtotal'].sum()
        if this_month_total < 1 and last_month_total < 1:
            print(f"ℹ️ Skipping project '{project_name}' due to negligible cost.")
            continue

        forecast = (this_month_total / days_so_far) * end_of_this_month_day if days_so_far > 0 else 0
        diff_str, _ = format_diff(last_month_total, this_month_total, days_so_far, last_month_days)
        service_diff_report = generate_service_summary_table(df_last_project, df_this_project, days_so_far, last_month_days, recent_days)
        
        # --- CORRECTED: Restoring the detailed message format ---
        slack_message = [
            f"*GCP Cost Summary: {project_name}*",
            f"*Project ID:* `{project_id}`",
            "",
            "*Overall Cost:*",
            f"  • *Last Month Total:* `{clean_currency(last_month_total)}`",
            f"  • *This Month (so far):* `{clean_currency(this_month_total)}`{diff_str}",
            f"  • *Forecast (end of month):* `{clean_currency(forecast)}`",
            "",
            "*Cost Breakdown by Service:*",
            "```",
            service_diff_report,
            "```"
        ]
        
        main_message_ts = send_slack_message("\n".join(slack_message), channel_id=channel_id)

        if not main_message_ts:
            print(f"⚠️ Could not post main message for {project_name}, skipping threads.")
            continue
        
        this_month_services = df_this_project.groupby(['service_id', 'service_description'])['subtotal'].sum()
        
        def sort_key(service_item):
            (_, service_name), cost = service_item
            is_not_bigquery = 0 if 'bigquery' in service_name.lower() else 1
            return (is_not_bigquery, -cost)

        sorted_services = sorted(this_month_services.items(), key=sort_key)
        
        for (service_id, service_name), cost in sorted_services:
            if cost > 1:
                print(f"   - Generating SKU breakdown for '{service_name}' (Cost: {clean_currency(cost)})...")
                table = generate_sku_breakdown_table(service_id, service_name, df_last_project, df_this_project, days_so_far, last_month_days, recent_days)
                if table.strip():
                    breakdown_title = "Aggregated SKU Breakdown" if service_name == "Compute Engine" else "SKU-level Breakdown"
                    thread_message = f"*{breakdown_title} for `{service_name}`*:\n```{table}```"
                    send_slack_message(thread_message, channel_id=channel_id, thread_ts=main_message_ts)
                else:
                    print(f"   ℹ️ No detailed data to show for '{service_name}'.")

    print("\n✅ Script finished.")
