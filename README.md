# GCP Cost Reporter for Slack

A comprehensive Python script that queries Google Cloud Platform (GCP) billing data from BigQuery, generates detailed cost analysis reports, and sends them as well-formatted messages to Slack.

This tool helps teams monitor their GCP spending by providing daily summaries, month-over-month comparisons and granular break down expenses by projects, services and there SKU's

## Key Features

-   **Multi-Project Reporting**: Monitor costs for multiple GCP projects in a single run.
-   **Detailed Slack Integration**: Posts a main summary table by service, followed by detailed, threaded replies with granular SKU-level breakdowns for each service.
-   **Advanced Cost Analysis**:
    -   Calculates a **month-to-date forecast**.
    -   Compares spending against a **prorated last-month baseline**.
    -   Displays a **7-day average** and recent daily costs to identify trends.
    -   Highlights the most recent day's cost variance against the 7-day average.
-   **Smart Compute Engine Aggregation**: Simplifies complex Compute Engine costs by grouping hundreds of SKUs into easy-to-understand categories (e.g., "VM Core Hours", "VM RAM").
-   **Custom Sorting**: Prioritizes BigQuery costs and then sorts all other services by current spending, ensuring the most important information is always at the top.
-   **Intelligent Caching**: Saves query results to minimize BigQuery costs and automatically refreshes the previous month's data during the first 7 days of a new month to ensure billing data is final.
-   **Clean & Readable Reports**: Uses `prettytable` to generate perfectly aligned, easy-to-read text tables with row numbers.
-   **Highly Configurable**: All settings, projects, and Slack channels are managed via an external `config.yaml` file.
-   **Resilient Notifications**: Includes a retry mechanism for sending Slack messages to handle temporary network or API issues.
-   **Cost-Aware Execution**: Performs a BigQuery "dry run" before executing queries to estimate the cost of the query itself.
-   **Flexible Usage**: Supports command-line arguments to force data refreshes and specify config file paths.

## Prerequisites

1.  **Google Cloud Project**: A GCP project with billing enabled.
2.  **BigQuery Billing Export**: You must have [GCP billing data exported to a BigQuery dataset](https://cloud.google.com/billing/docs/how-to/export-data-bigquery).
3.  **Service Account**: A GCP Service Account with the `BigQuery User` role on the project containing the billing export. You'll need to generate a key and set up authentication (e.g., by setting the `GOOGLE_APPLICATION_CREDENTIALS` environment variable).
4.  **Slack App**: A Slack App with a Bot Token that has the `chat:write` permission.

## Setup & Installation

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/vadirajks/gcp-cost-reporter.git](https://github.com/vadirajks/gcp-cost-reporter.git)
    cd gcp-cost-reporter
    ```

2.  **Create a Python virtual environment (recommended):**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

3.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure the script:**
    * Copy the example configuration file:
        ```bash
        cp config.yaml.example config.yaml
        ```
    * Edit `config.yaml` with your specific details (BigQuery table ID, projects, Slack channel IDs).

5.  **Set environment variables:**
    * Set the path to your GCP service account key file.
        ```bash
        export GOOGLE_APPLICATION_CREDENTIALS="/path/to/your/service-account-key.json"
        ```
    * Set your Slack Bot Token.
        ```bash
        export SLACK_BOT_TOKEN="xoxb-your-slack-bot-token"
        ```

## Usage

Once configured, you can run the script from your terminal.

* **Standard Run (uses cache if available):**
    ```bash
    python main.py
    ```

* **Force a Data Refresh (ignores cache):**
    ```bash
    python main.py --force-refresh
    ```

* **Use a custom config file path:**
    ```bash
    python main.py --config /path/to/your/config.yaml
    ```

You can set this up to run automatically on a schedule using a cron job or a service like Cloud Scheduler with Cloud Functions.

## Future Enhancements & Roadmap

This section outlines potential future improvements for the project. Contributions are highly welcome!

### Deeper Cost Insights

-   **Cost Anomaly Detection**: Instead of just comparing to the previous month, implement statistical analysis (e.g. 30-day rolling average) to automatically detect and flag unusual cost spikes for a service with a "🔥 **COST ANOMALY**" warning.
-   **Label-Based Cost Breakdown**: Extend the query and reporting logic to group costs by GCP resource labels (e.g., `team: backend`, `env: prod`). This would provide powerful, fine-grained cost attribution for different teams or applications.
-   **Interactive Slack Bot**: Add functionality for the script to listen to replies in Slack. For example, replying to a "Compute Engine" summary with the word `raw` could trigger the bot to post a new reply with the detailed, non-aggregated list of SKUs.

### Smarter Alerting & Intelligence

-   **Threshold-Based Budget Alerts**: Enhance the `config.yaml` to allow setting a monthly budget per project. If the forecasted cost exceeds this budget, the script would send a special, high-visibility alert (e.g., using Slack's colored message attachments and an @-mention).
-   **Idle Resource Identification**: A more advanced feature to query GCP Asset Inventory or monitoring APIs to identify costly but underutilized resources, such as unattached Persistent Disks or idle Cloud SQL instances, and flag them in the report.
-   **Cost Correlation with Events**: Integrate with a CI/CD system (e.g., via webhooks) or Git history to correlate a sudden cost increase with a recent deployment or infrastructure change, adding valuable context to the alert.

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue to discuss a new feature.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
