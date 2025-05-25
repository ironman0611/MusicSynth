FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libgl1-mesa-glx \
    libglib2.0-0 \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create necessary directories
RUN mkdir -p /app/temp /app/xml_files

# Create startup script with enhanced logging
RUN echo '#!/bin/bash\necho "=== Starting Streamlit application ==="\npwd\nls -la\necho "Environment variables:"\nenv\necho "Starting Streamlit..."\nstreamlit run app.py --server.port=8501 --server.address=0.0.0.0 --logger.level=debug > /tmp/streamlit.log 2>&1 &\nSTREAMLIT_PID=$!\necho "Streamlit started with PID: $STREAMLIT_PID"\necho "Waiting for Streamlit to start..."\nsleep 15\necho "Checking Streamlit process:"\nps aux | grep streamlit\necho "Checking Streamlit logs:"\ncat /tmp/streamlit.log\necho "Checking if Streamlit is running..."\ncurl -v http://localhost:8501/ || echo "Streamlit not ready yet"\necho "=== Startup complete ==="\nwait $STREAMLIT_PID\n' > /app/start.sh && chmod +x /app/start.sh

# Expose the port Streamlit runs on
EXPOSE 8501

# Set environment variables
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_LOG_LEVEL=debug
ENV PYTHONUNBUFFERED=1

# Add healthcheck with more lenient parameters
HEALTHCHECK --interval=15s --timeout=10s --start-period=60s --retries=5 \
    CMD curl -f http://localhost:8501/ || exit 1

# Use the startup script
CMD ["/app/start.sh"] 