# browser-render-service/Dockerfile
# Uses official Playwright image with all Chromium dependencies pre-installed

FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium browser
RUN playwright install chromium

# Copy application code
COPY main.py .

# Expose port
EXPOSE 8080

# Run the service
CMD ["python", "main.py"]
