# CI/CD Architecture for Google Cloud Functions with GitHub Actions

This document outlines the optimal CI/CD architecture for deploying Google Cloud Functions from a monorepo using GitHub Actions. The design prioritizes security, efficiency, and maintainability, leveraging best practices for both GitHub Actions and Google Cloud.

## 1. Authentication: Securely Connecting GitHub Actions to Google Cloud

The most critical aspect of the CI/CD pipeline is securely authenticating GitHub Actions with your Google Cloud project. The recommended and most secure method is to use **Workload Identity Federation**, which allows you to grant short-lived credentials to your GitHub Actions workflows without needing to store long-lived service account keys as GitHub secrets.

### Workload Identity Federation Setup

Workload Identity Federation works by establishing a trust relationship between your Google Cloud project and your GitHub repository. This allows your GitHub Actions workflows to impersonate a Google Cloud service account, granting them the necessary permissions to deploy Cloud Functions.

Here's a step-by-step guide to setting up Workload Identity Federation:

1.  **Create a Workload Identity Pool and Provider**:
    *   A **Workload Identity Pool** is a container for identity providers. You'll create one for your GitHub Actions.
    *   A **Workload Identity Provider** represents the trust relationship with your GitHub repository. You'll configure it to trust your specific repository.

2.  **Create a Google Cloud Service Account for GitHub Actions**: This service account will be impersonated by your GitHub Actions workflows. It's crucial to grant this service account only the necessary permissions (principle of least privilege) to deploy your Cloud Functions.

3.  **Grant the Service Account the Necessary Roles**: The service account will need roles like:
    *   `roles/cloudfunctions.developer`: To deploy and manage Cloud Functions.
    *   `roles/iam.serviceAccountUser`: To allow the Cloud Function to run as another service account (your existing `svc-account-aisports@...`).
    *   `roles/storage.objectAdmin`: If your deployment process involves uploading to GCS.

4.  **Allow the GitHub Actions Provider to Impersonate the Service Account**: You'll create an IAM policy binding that allows the Workload Identity Provider to impersonate the service account you created.

5.  **Configure GitHub Actions to Use Workload Identity Federation**: In your GitHub Actions workflows, you'll use the `google-github-actions/auth` action to authenticate with Google Cloud using Workload Identity Federation. This action will handle the token exchange and provide your workflow with short-lived credentials.

### Handling `GOOGLE_APPLICATION_CREDENTIALS_BASE64`

You mentioned storing your credentials in a base64 encoded secret named `GOOGLE_APPLICATION_CREDENTIALS_BASE64`. While this is a common practice, it's **less secure** than Workload Identity Federation because it involves storing a long-lived service account key. If this key is compromised, it could provide an attacker with persistent access to your Google Cloud project.

**Recommendation**: **Migrate to Workload Identity Federation.** It's the industry best practice and significantly improves the security of your CI/CD pipeline. However, if you must use the base64 encoded key for now, the CI/CD workflow can be adapted to decode and use it. The provided leanest CI/CD workflow will include instructions for both methods, with a strong recommendation to use Workload Identity Federation.

## 2. Monorepo CI/CD Workflow Design

For a monorepo, the CI/CD pipeline needs to be intelligent enough to only build and deploy the functions that have changed. This is achieved using path filtering in GitHub Actions.

### Workflow Triggers

Each Cloud Function will have its own dedicated GitHub Actions workflow file (e.g., `deploy-scraper-function.yml`). The trigger for each workflow will be configured to run only when changes are detected in the corresponding function's directory or any shared directories it depends on.

Example trigger for the `scraper_function`:

```yaml
on:
  push:
    branches:
      - main
    paths:
      - 'functions/scraper_function/**'
      - 'shared_libs/**'
```

This ensures that the `deploy-scraper-function.yml` workflow only runs when there are changes in the `functions/scraper_function/` directory or the `shared_libs/` directory.

### Workflow Steps

Each workflow will consist of the following steps:

1.  **Checkout Code**: Check out the monorepo code.
2.  **Authenticate to Google Cloud**: Use the `google-github-actions/auth` action to authenticate with Google Cloud (preferably using Workload Identity Federation).
3.  **Set up Google Cloud SDK**: Use the `google-github-actions/setup-gcloud` action to install and configure the `gcloud` CLI.
4.  **Deploy the Cloud Function**: Use the `google-github-actions/deploy-cloud-functions` action to deploy the specific Cloud Function. This action will handle packaging the function code and its dependencies and deploying it to your Google Cloud project.

### Leanest CI/CD Implementation

To create the *leanest* CI/CD, we will:

*   **Use official Google-provided GitHub Actions**: These actions are well-maintained, documented, and optimized for interacting with Google Cloud.
*   **Minimize custom scripting**: Rely on the declarative syntax of GitHub Actions and the capabilities of the official actions to avoid complex custom scripts.
*   **Keep workflows focused**: Each workflow will have a single responsibility: to deploy a specific Cloud Function.
*   **Provide clear instructions**: The implementation guide will provide clear, copy-pasteable workflow files and detailed instructions for setting up authentication.

By following this architecture, you will have a secure, efficient, and maintainable CI/CD pipeline for your Google Cloud Functions microservices, enabling you to refactor your monolith with confidence.

