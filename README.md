# GCP Cost Reporter for Slack

A flexible and powerful Python script to monitor Google Cloud Platform costs, generate daily summaries, and send detailed, aggregated reports to Slack.

This tool helps teams keep track of their cloud spending by providing clear, automated reports that highlight cost trends and break down expenses by service, SKU, and region.

## Features

- **Multi-Project Reporting**: Monitor costs for multiple GCP projects in a single run.
- **Slack Integration**: Posts a main summary and detailed, threaded replies for each service.
- **Intelligent Aggregation**: For complex services like Compute Engine, SKUs are aggregated into human-readable categories (e.g., "VM Core Hours (On-Demand)", "Network: Data Transfer").
- **Logical Sorting**: Slack threads are intelligently sorted to show the highest-cost services first and group related services (like BigQuery) together.
- **Cost-Saving Cache**: Automatically caches daily results to avoid re-running expensive BigQuery queries.
- **Resilient & Robust**: Includes retry logic for Slack notifications and pre-flight cost estimation for BigQuery queries.
- **Highly Configurable**: All settings, projects, and Slack channels are managed via an external `config.yaml` file.
- **Flexible Usage**: Supports command-line arguments to force data refreshes and specify config file paths.

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

-   **Cost Anomaly Detection**: Instead of just comparing to the previous month, implement statistical analysis (e.g., based on a 7 or 30-day rolling average) to automatically detect and flag unusual cost spikes for a service with a "🔥 **COST ANOMALY**" warning.
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
