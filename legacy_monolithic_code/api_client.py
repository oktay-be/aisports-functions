import asyncio
import json
import aiohttp
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Configuration
SERVER_BASE_URL = "http://localhost:5000/api"
ANALYSIS_START_JOB_ENDPOINT = f"{SERVER_BASE_URL}/analysis/start_job" # New endpoint
PARAMETERS_FILE = "search_parameters.json"

async def fetch_data(session, url, payload):
    """Helper function to make a POST request and return JSON data."""
    try:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = await response.json()
            logging.info(f"Successfully fetched data from {url} with payload {payload}")
            return data
    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error fetching {url}: {e.status} {e.message} - Server response: {await response.text()}")
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error fetching {url}: {e}")
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON response from {url}")
    except Exception as e:
        logging.error(f"An unexpected error occurred fetching {url}: {e}")
    return None

async def start_analysis_job(session, url, payload):
    """Helper function to make a POST request to start an analysis job and return JSON data."""
    try:
        async with session.post(url, json=payload) as response:
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = await response.json()
            logging.info(f"Successfully started analysis job via {url} with payload {payload}")
            logging.info(f"Server response: {data}")
            return data
    except aiohttp.ClientResponseError as e:
        logging.error(f"HTTP error starting job {url}: {e.status} {e.message} - Server response: {await response.text()}")
    except aiohttp.ClientConnectionError as e:
        logging.error(f"Connection error starting job {url}: {e}")
    except json.JSONDecodeError:
        logging.error(f"Failed to decode JSON response from {url} when starting job")
    except Exception as e:
        logging.error(f"An unexpected error occurred starting job {url}: {e}")
    return None

async def main():
    """Main function to load parameters, call the analysis job endpoint, and print results."""
    # Define client-specific keywords and URLs directly
    client_keywords_direct = ["Galatasaray"]
    client_scrape_urls_direct = ["https://www.skorgazetesi.com/"]
    # This parameter's relevance is reduced with the new orchestrator logic,
    # but we can keep it for now or decide to remove it from the API contract later.
    # For this client, let's set it to False, as we are providing specific inputs.
    use_server_defaults = False
    client_time_range_direct = "last_week" # Client wants to see news from the last week

    async with aiohttp.ClientSession() as session:
        # Prepare payload for the analysis job
        analysis_payload = {}
        if client_keywords_direct: # Use direct values
            analysis_payload["client_keywords"] = client_keywords_direct
        if client_scrape_urls_direct: # Use direct values
            analysis_payload["client_scrape_urls"] = client_scrape_urls_direct
        analysis_payload["use_default_urls_keywords"] = use_server_defaults
        if client_time_range_direct: # Add time_range if specified
            analysis_payload["time_range"] = client_time_range_direct
        # Custom dates are not specified in this example, so they won't be sent.
        # analysis_payload["custom_start_date"] = "YYYY-MM-DD" 
        # analysis_payload["custom_end_date"] = "YYYY-MM-DD"

        logging.info(f"Preparing to call {ANALYSIS_START_JOB_ENDPOINT} with payload: {analysis_payload}")
        
        job_initiation_response = await start_analysis_job(session, ANALYSIS_START_JOB_ENDPOINT, analysis_payload)

        if job_initiation_response and job_initiation_response.get("session_id"):
            logging.info(f"Analysis job started successfully. Session ID: {job_initiation_response.get('session_id')}")
            logging.info(f"Check status at: {job_initiation_response.get('status_endpoint')}")
            # Here you would typically store the session_id and implement polling or another mechanism
            # to check the job status and retrieve results when completed.
            # For this client, we'll just log the initial response.
            
            # Save the initial response to a file for reference
            output_filename = f"analysis_job_{job_initiation_response.get('session_id')}_init_response.json"
            with open(output_filename, 'w', encoding='utf-8') as outfile:
                json.dump(job_initiation_response, outfile, ensure_ascii=False, indent=2)
            logging.info(f"Job initiation response saved to {output_filename}")
        else:
            logging.error("Failed to start analysis job or received an unexpected response.")
            if job_initiation_response:
                logging.error(f"Response received: {job_initiation_response}")

if __name__ == "__main__":
    asyncio.run(main())

