# Use Ubuntu as base for FreeSurfer compatibility
FROM ubuntu:24.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.12 \
    python3-pip \
    wget \
    curl \
    libgomp1 \
    libglu1-mesa \
    libglib2.0-0 \
    libsm6 \
    libxrender1 \
    libxt6 \
    libxcomposite1 \
    libfreetype6 \
    libjpeg62-dev \
    libtiff6 \
    libpng16-16 \
    libxcursor1 \
    libxinerama1 \
    libxrandr2 \
    libxss1 \
    libxv1 \
    libgdk-pixbuf2.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

# Install python3-venv and setuptools for virtual environment support
RUN apt-get update && apt-get install -y python3.12-venv python3-setuptools && rm -rf /var/lib/apt/lists/*

# Install FreeSurfer (using a minimal version for faster builds)
# Note: In production, you should use the full FreeSurfer installation
# For now, we'll create a placeholder
RUN mkdir -p /usr/local/freesurfer && \
    echo "FreeSurfer placeholder - replace with actual installation" > /usr/local/freesurfer/README

# Set FreeSurfer environment variables
ENV FREESURFER_HOME=/usr/local/freesurfer
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=$FREESURFER_HOME/license.txt

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
COPY .env .env

# Create a non-root user
RUN useradd -m -s /bin/bash brainyes
USER brainyes

# Set the entrypoint
ENTRYPOINT ["python3.12", "handlers/ecs_handler.py"]