# Use the official Microsoft Playwright image for Python (much more stable for production)
FROM mcr.microsoft.com/playwright/python:v1.49.1-jammy

# Set the working directory in the container
WORKDIR /app

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies (needed for playwright and sqlite)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Ensure chromium is available for the robot
RUN playwright install chromium

# Copy the rest of the application code
COPY . .

# Expose port 8001
EXPOSE 8001

# Command to run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"]
