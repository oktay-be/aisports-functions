# GitHub Actions Authentication with Workload Identity Federation for Google Cloud Functions (Revised)

This revised guide explains how to securely authenticate your GitHub Actions workflows to Google Cloud using **Workload Identity Federation** (WIF), specifically leveraging your *existing* service account (`svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com`) for deployments. This approach enables automated deployments of Cloud Functions without storing long-lived service account credentials in GitHub.

## Why Use Workload Identity Federation?
- **No service account keys in GitHub**: Eliminates the security risk of storing sensitive, long-lived service account keys in GitHub secrets.
- **Short-lived tokens**: Credentials are automatically generated and are only valid for the duration of the workflow execution, minimizing exposure.
- **Fine-grained access**: You maintain precise control over which GitHub repositories and workflows can access your Google Cloud resources, adhering to the principle of least privilege.
- **Leverages existing IAM**: Integrates seamlessly with your existing Google Cloud Identity and Access Management (IAM) setup.

## Prerequisites
- **Owner or Editor access** to your Google Cloud project (`gen-lang-client-0306766464`).
- **Admin access** to your GitHub repository (`oktay-be/aisports-functions`).
- **Google Cloud SDK (`gcloud`) installed and authenticated** on your local machine with an account that has sufficient permissions to manage IAM, Workload Identity Pools, and Service Accounts in your project.

---

## Step 1: Enable Necessary Google Cloud APIs

Before proceeding, ensure the following APIs are enabled in your Google Cloud project. These are essential for Workload Identity Federation and Cloud Functions deployment.

```bash
gcloud services enable iam.googleapis.com \
    iamcredentials.googleapis.com \
    cloudresourcemanager.googleapis.com \
    cloudfunctions.googleapis.com \
    cloudbuild.googleapis.com \
    pubsub.googleapis.com \
    storage.googleapis.com \
    aiplatform.googleapis.com \
    firestore.googleapis.com \
    --project=gen-lang-client-0306766464
```

**Note**: If you encounter an error like "Cloud Resource Manager API has not been used..." or similar API not enabled messages, you must visit the provided URL in your browser to enable the API manually and wait a few minutes for propagation before retrying the `gcloud` commands.

---

## Step 2: Grant Necessary Permissions to Your Existing Service Account

Your existing service account, `svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com`, will be used for both setting up Workload Identity Federation and for the actual deployments. Therefore, it needs specific permissions. You must grant these roles using an account with `Owner` or `Project IAM Admin` permissions.

**Important**: If you are performing these `gcloud` commands using your `svc-account-aisports` service account itself (via `gcloud auth activate-service-account`), ensure it has the `Project IAM Admin` role (`roles/resourcemanager.projectIamAdmin`) and `Service Account Admin` (`roles/iam.serviceAccountAdmin`) *before* attempting the Workload Identity Pool creation steps. These are powerful permissions and should be used with caution and removed after setup if not continuously needed for automation.

Here are the roles required for `svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com`:

*   **`roles/iam.workloadIdentityPoolAdmin`**: Required to create and manage Workload Identity Pools and Providers.
*   **`roles/iam.workloadIdentityUser`**: Allows the Workload Identity Provider (GitHub Actions) to impersonate this service account.
*   **`roles/cloudfunctions.developer`**: To deploy and manage Cloud Functions.
*   **`roles/iam.serviceAccountUser`**: To allow the Cloud Function to run as this service account (or to impersonate other service accounts if needed).
*   **`roles/storage.objectAdmin`**: If your deployment process involves uploading source code to GCS buckets (which Cloud Functions deployment does).
*   **`roles/pubsub.publisher`**: To publish messages to Pub/Sub topics (as your functions do).
*   **`roles/storage.objectViewer`**: To read from GCS buckets (as your functions do).
*   **`roles/aiplatform.user`**: To submit Vertex AI batch prediction jobs (as your functions do). This role includes the necessary `aiplatform.batchPredictionJobs.create` permission.
*   **`roles/datastore.user`**: To read/write to Cloud Firestore (if used by your functions).

Example of granting a role (repeat for all necessary roles):

```bash
gcloud projects add-iam-policy-binding gen-lang-client-0306766464 \
    --member="serviceAccount:svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com" \
    --role="roles/iam.workloadIdentityPoolAdmin"
```

**Note on `iam.serviceAccountAdmin`**: If you are unable to find `Service Account Admin` in the Cloud Console UI, try searching for `Service Account Admin` directly in the filter box. It is a standard role (`roles/iam.serviceAccountAdmin`) and is necessary for managing service accounts programmatically.

---

## Step 3: Create a Workload Identity Pool and Provider

These steps establish the trust relationship between your Google Cloud project and your GitHub repository. Ensure your `gcloud` CLI is configured to the correct project:

```bash
gcloud config set project gen-lang-client-0306766464
```

1.  **Create a Workload Identity Pool**

    ```bash
    gcloud iam workload-identity-pools create github-actions-pool \
        --project=gen-lang-client-0306766464 \
        --location="global" \
        --display-name="GitHub Actions Pool"
    ```

    **Troubleshooting**: If you encounter a `NOT_FOUND` error here, it means the pool was not created successfully or is not accessible. Verify the project ID and ensure the service account performing this command has `roles/iam.workloadIdentityPoolAdmin`.

2.  **Get the Workload Identity Pool ID**

    This command will output the full resource name of the pool, which you will need for the next step.

    ```bash
    gcloud iam workload-identity-pools describe github-actions-pool \
        --location="global" \
        --format="value(name)" \
        --project=gen-lang-client-0306766464
    ```

    The output will look something like: `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool`.

3.  **Create a Workload Identity Provider for GitHub**

    This step links your GitHub repository to the Workload Identity Pool. Replace `YOUR_GITHUB_ORG` with your GitHub organization name (or your username if it's a personal repository) and `YOUR_REPOSITORY_NAME` with the name of your GitHub repository (`aisports-functions`).

    **Important**: Pay close attention to the backslashes (`\`) for line continuation and the escaping of quotes (`\"`) around the repository name in `attribute-condition`.

    ```bash
    gcloud iam workload-identity-pools providers create-oidc github-actions-provider \
        --project=gen-lang-client-0306766464 \
        --location="global" \
        --workload-identity-pool="github-actions-pool" \
        --display-name="GitHub Actions Provider" \
        --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository" \
        --issuer-uri="https://token.actions.githubusercontent.com" \
        --attribute-condition="attribute.repository == \"oktay-be/aisports-functions\""
    ```

    **Troubleshooting**: If you encounter "unrecognized arguments" or "No such file or directory" errors, it's likely a shell parsing issue. Try running the command as a single line, or carefully re-type it to ensure no hidden characters or incorrect line breaks.

---

## Step 4: Allow GitHub to Impersonate Your Service Account

This step creates an IAM policy binding that allows the Workload Identity Provider to impersonate your existing service account (`svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com`).

First, get your Google Cloud Project Number:

```bash
gcloud projects describe gen-lang-client-0306766464 --format="value(projectNumber)"
```

Then, use the project number in the following command. Replace `PROJECT_NUMBER` with the actual number you obtained.

```bash
gcloud iam service-accounts add-iam-policy-binding svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com \
    --project=gen-lang-client-0306766464 \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/oktay-be/aisports-functions"
```

**Note**: The `attribute.repository` value (`oktay-be/aisports-functions`) must exactly match your GitHub repository path.

Resp:

Updated IAM policy for serviceAccount [svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com].
bindings:
- members:
  - principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/attribute.repository/oktay-be/aisports-functions
  role: roles/iam.workloadIdentityUser
etag: BwY5usxnUPs=
version: 1

---

## Step 5: Update Your GitHub Actions Workflow

Now, modify your GitHub Actions workflow files (e.g., `.github/workflows/deploy-scraper-function.yml`) to use Workload Identity Federation for authentication. You will replace the `service_account_key` input with `workload_identity_provider` and `service_account`.

Replace `<PROJECT_NUMBER>` with your actual Google Cloud Project Number.

```yaml
    - name: Authenticate to Google Cloud (Workload Identity Federation)
      uses: google-github-actions/auth@v2
      with:
        workload_identity_provider: "projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions-pool/providers/github-actions-provider"
        service_account: "svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com"
```

**Ensure you remove any lines referencing `service_account_key` from your workflow files.**

---

## Step 6: Test Your Workflow

1.  Commit and push your updated workflow changes to your GitHub repository.
2.  Trigger the workflow (e.g., by pushing a change to a function's directory).
3.  Monitor the GitHub Actions run and verify that authentication and deployment succeed without any credential errors.

---

## Troubleshooting
- **Permission Errors**: If you encounter permission errors, double-check that your `svc-account-aisports` service account has all the necessary IAM roles as listed in Step 2.
- **`NOT_FOUND` Errors**: Ensure the Workload Identity Pool and Provider names are correct and that they were created successfully in your Google Cloud project.
- **Shell Parsing Issues**: When copying `gcloud` commands, be mindful of line breaks and hidden characters. Running commands as a single line can often resolve these.
- **Incorrect Repository Path**: Verify that `attribute.repository` in your `gcloud` commands and `principalSet` in the IAM policy binding exactly matches your GitHub repository path (e.g., `oktay-be/aisports-functions`).

---

**By following this revised guide, your GitHub Actions workflows will securely authenticate to Google Cloud using Workload Identity Federation and your existing service account, enabling safe and automated Cloud Functions deployments.**


