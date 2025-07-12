# Cloud Project Setup Before CI/CD

This document summarizes the required Google Cloud APIs and IAM roles for secure, automated deployment of Cloud Functions using Workload Identity Federation and GitHub Actions.

---

## Enabled APIs

The following APIs must be enabled in your Google Cloud project (`gen-lang-client-0306766464`). These are visible under the "Enabled APIs & Services" page in the Cloud Console:

1. **Cloud Resource Manager API** (`cloudresourcemanager.googleapis.com`)
   - Required for managing project-level resources and IAM policies.
2. **IAM API** (`iam.googleapis.com`)
   - Required for managing service accounts, IAM roles, and Workload Identity Federation.
3. **Service Usage API** (`serviceusage.googleapis.com`)
   - Required for enabling/disabling other APIs programmatically.
4. **Cloud Functions API** (`cloudfunctions.googleapis.com`)
   - Required for deploying and managing Cloud Functions.
5. **Cloud Storage API** (`storage.googleapis.com`)
   - Required for storing and retrieving data in Google Cloud Storage.
6. **Vertex AI API** (`aiplatform.googleapis.com`)
   - Required for AI/ML workloads and batch processing.
7. **Generative Language API** (`generativelanguage.googleapis.com`)
   - Required for advanced generative AI features (if used).

---

## IAM Roles for Service Account

The following roles were granted to the deployment service account (`svc-account-aisports@gen-lang-client-0306766464.iam.gserviceaccount.com`) to enable full automation and IaC:

### 1. **Cloud Functions Developer** (`roles/cloudfunctions.developer`)
- Allows deploying, updating, and managing Cloud Functions.

### 2. **IAM Workload Identity Pool Admin** (`roles/iam.workloadIdentityPoolAdmin`)
- Allows creation and management of Workload Identity Pools and Providers for federated authentication.

### 3. **Project IAM Admin** (`roles/resourcemanager.projectIamAdmin`)
- Allows full management of IAM policies and permissions at the project level.

### 4. **Service Account Admin** (`roles/iam.serviceAccountAdmin`)
- Allows creation, deletion, and management of service accounts.

### 5. **Service Account User** (`roles/iam.serviceAccountUser`)
- Allows a principal to act as (impersonate) a service account, required for federated workflows.

### 6. **Service Usage Admin** (`roles/serviceusage.serviceUsageAdmin`)
- Allows enabling and disabling Google Cloud APIs programmatically.

### 7. **Storage Object Admin** (`roles/storage.objectAdmin`)
- Allows full access to objects in Google Cloud Storage buckets (read, write, delete).

### 8. **Vertex AI Service Agent** (`roles/aiplatform.serviceAgent`)
- Allows interaction with Vertex AI for batch processing and AI workloads.

---

## Why These Roles?
- **Cloud Functions Developer**: Needed for deploying and managing serverless functions.
- **Workload Identity Pool Admin**: Needed for setting up federated authentication (GitHub Actions).
- **Project IAM Admin**: Needed for full automation of IAM policies and permissions (IaC).
- **Service Account Admin & User**: Needed for creating and impersonating service accounts in automated workflows.
- **Service Usage Admin**: Needed for enabling/disabling APIs as part of automation.
- **Storage Object Admin**: Needed for reading/writing data to GCS buckets.
- **Vertex AI Service Agent**: Needed for AI/ML workloads and batch processing.

---

## Security Note
These roles grant broad permissions for automation and IaC. For production, consider:
- Using a dedicated admin service account for setup and automation.
- Restricting deployment service accounts to least privilege (only the roles needed for deployment).
- Regularly auditing IAM roles and API usage.

---

**This setup ensures your project is ready for secure, automated CI/CD and cloud function deployments using Workload Identity Federation and GitHub Actions.**
