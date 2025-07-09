
## Why Batch Prediction Is Not Supported on the Global Endpoint

- The **global endpoint** in Vertex AI does not support batch prediction jobs.
- Batch prediction requires specifying a **regional endpoint** because batch jobs involve storage and compute resources tied to specific Google Cloud regions.
- Using a regional endpoint ensures data residency compliance, optimized latency, and resource locality.


## Which Regions to Use for Batch Prediction

You must select a **specific Google Cloud region** where both your model and batch prediction job will run. The input data and output locations (Cloud Storage or BigQuery) must also be in the same region or a supported multi-region.

### Commonly Supported Regions for Vertex AI Batch Prediction (Including Gemini Models)

| Region ID | Location Name |
| :-- | :-- |
| `us-central1` | Iowa, USA |
| `us-east1` | South Carolina, USA |
| `us-east4` | Northern Virginia, USA |
| `us-west1` | Oregon, USA |
| `us-west4` | Las Vegas, USA |
| `europe-west1` | Belgium |
| `europe-west4` | Netherlands |
| `europe-west6` | Zürich, Switzerland |
| `asia-east1` | Taiwan |
| `asia-northeast1` | Tokyo, Japan |
| `asia-southeast1` | Singapore |

> **Note:** This is not an exhaustive list. You should choose a region closest to your users or data location for best performance.

## Important Considerations

- **Model and Batch Job Region Must Match:**
The region where your model is hosted and where you submit the batch job must be the same.
- **Input and Output Locations:**
The Cloud Storage bucket or BigQuery dataset used for input and output must be in the same region as the batch job.
- **Multi-Region Buckets:**
Some multi-region buckets (e.g., `us`, `europe`) are supported if they align with the model region.


## How to Specify Region in Batch Prediction

When creating a batch prediction job, specify the regional endpoint in your API calls or SDK client initialization. For example, in Python:

```python
client = genai.Client(vertexai=True, project="your-project-id", location="us-central1")
```

Use the region ID (e.g., `us-central1`) instead of `"global"`.

## Summary

| Aspect | Recommendation |
| :-- | :-- |
| **Batch Prediction Endpoint** | Use a specific regional endpoint (not global) |
| **Region Selection** | Choose from supported Vertex AI regions (e.g., `us-central1`, `europe-west1`) |
| **Data Location** | Input/output data must be in the same region |
| **Global Endpoint Usage** | Supported only for synchronous online predictions, not batch jobs |

For the most up-to-date list of supported regions and detailed instructions, refer to the official Vertex AI locations documentation.

**References:**
[^47_1] Vertex AI locations | Google Cloud
[^47_2] Batch prediction | Generative AI on Vertex AI - Google Cloud
[^47_3] Get batch predictions for Gemini | Generative AI on Vertex AI

<div style="text-align: center">⁂</div>

[^47_1]: https://cloud.google.com/vertex-ai/docs/general/locations

[^47_2]: https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/batch-prediction-gemini

[^47_3]: https://google-cloud-pipeline-components.readthedocs.io/en/google-cloud-pipeline-components-2.6.0/api/v1/batch_predict_job.html

[^47_4]: https://www.googlecloudcommunity.com/gc/AI-ML/Vertex-AI-training/m-p/785965/highlight/true

[^47_5]: https://www.googlecloudcommunity.com/gc/AI-ML/Batch-prediction-on-custom-model/td-p/442147

[^47_6]: https://cloud.google.com/vertex-ai/generative-ai/docs/model-reference/batch-prediction-api

[^47_7]: https://cloud.google.com/vertex-ai/docs/predictions/get-batch-predictions

[^47_8]: https://stackoverflow.com/questions/79254402/how-can-i-run-batch-predictions-with-few-shot-examples-in-vertex-ai

[^47_9]: https://github.com/googleapis/python-aiplatform/issues/3871

[^47_10]: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations

[^47_11]: https://status.cloud.google.com/regional/europe

[^47_12]: https://www.googlecloudcommunity.com/gc/AI-ML/Batch-prediction-on-custom-model/m-p/464206

[^47_13]: https://www.ml6.eu/blogpost/getting-model-predictions-from-vertex-ai-and-how-it-compares-to-ai-platform

[^47_14]: https://airflow.apache.org/docs/apache-airflow-providers-google/stable/_api/airflow/providers/google/cloud/operators/vertex_ai/batch_prediction_job/index.html

[^47_15]: https://github.com/GoogleCloudPlatform/generative-ai/issues/1308

[^47_16]: https://github.com/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/community/vertex_endpoints/optimized_tensorflow_runtime/tabular_optimized_online_prediction.ipynb

[^47_17]: https://docs.litellm.ai/docs/providers/vertex

[^47_18]: https://www.reddit.com/r/GoogleGeminiAI/comments/1iqwscx/batch_prediction_for_gemini_disabled/

[^47_19]: https://www.cloudskillsboost.google/course_templates/9/video/531749?locale=de

[^47_20]: https://colab.research.google.com/github/GoogleCloudPlatform/vertex-ai-samples/blob/main/notebooks/official/migration/sdk-automl-text-classification-batch-prediction.ipynb

