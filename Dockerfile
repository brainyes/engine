# Use Ubuntu 22.04 for FreeSurfer compatibility
# Force amd64 platform as FreeSurfer only supports x86_64
FROM --platform=linux/amd64 ubuntu:22.04

# Build argument for S3 bucket name
ARG BUILD_ASSETS_BUCKET=brainyes-build-assets

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install software-properties-common for add-apt-repository
RUN apt-get update && apt-get install -y \
    software-properties-common \
    && rm -rf /var/lib/apt/lists/*

# Add deadsnakes PPA for Python 3.12
RUN add-apt-repository ppa:deadsnakes/ppa -y

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    wget \
    libgomp1 \
    libglu1-mesa \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxt6 \
    libxcomposite1 \
    libfreetype6 \
    libjpeg62 \
    libtiff5 \
    libpng16-16 \
    libxcursor1 \
    libxinerama1 \
    libxrandr2 \
    libxss1 \
    libxv1 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Copy FreeSurfer .deb file if it exists (downloaded by buildspec or provided locally)
# Wildcard prevents failure if missing
COPY freesurfer_ubuntu22-8.1.0_amd64.deb* .

# Download from Harvard server if not present locally (fallback)
RUN if [ ! -f freesurfer_ubuntu22-8.1.0_amd64.deb ]; then \
      echo "FreeSurfer package not found locally, downloading from Harvard server..."; \
      wget -q https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/8.1.0/freesurfer_ubuntu22-8.1.0_amd64.deb; \
    else \
      echo "Using local FreeSurfer package"; \
    fi

# Set FreeSurfer environment variables
ENV FREESURFER_HOME=/usr/local/freesurfer
ENV PATH=$FREESURFER_HOME/bin:$PATH

# Install FreeSurfer
RUN apt-get update && \
    apt-get install -y ./freesurfer_ubuntu22-8.1.0_amd64.deb && \
    rm freesurfer_ubuntu22-8.1.0_amd64.deb && \
    rm -rf /var/lib/apt/lists/*

# Copy FreeSurfer license file
ENV FS_LICENSE=$FREESURFER_HOME/license.txt
COPY freesurfer_license.txt $FREESURFER_HOME/license.txt

# Create app directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Create virtual environment and install Python dependencies
RUN python3.12 -m venv /app/venv
ENV PATH="/app/venv/bin:$PATH"
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY functions/ ./functions/
COPY utilities/ ./utilities/
COPY insights/ ./insights/
COPY handlers/ ./handlers/
COPY research/input/ ./research/input/

# Create a non-root user
RUN useradd -m -s /bin/bash brainyes
USER brainyes

# Set the entrypoint
ENTRYPOINT ["python3.12", "handlers/ecs_handler.py"]