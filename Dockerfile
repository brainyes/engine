# ============================================
# Stage 1: System base with dependencies
# ============================================
FROM --platform=linux/amd64 ubuntu:22.04 AS system-base

# Build argument for S3 bucket name
ARG BUILD_ASSETS_BUCKET=brainyes-build-assets

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install software-properties-common for add-apt-repository
RUN apt-get update && apt-get install -y \
    software-properties-common \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Add deadsnakes PPA for Python 3.12
RUN add-apt-repository ppa:deadsnakes/ppa -y

# Install system dependencies needed for FreeSurfer installation and runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    dcm2niix \
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


# ============================================
# Stage 2a: FreeSurfer 8 installation (buildable base)
# ============================================
FROM system-base AS freesurfer-8-build

ARG FS8_DEB_URL="https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/8.1.0/freesurfer_ubuntu22-8.1.0_amd64.deb"

# Download and install FreeSurfer 8 in a single layer to avoid shipping the .deb as a separate layer
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    set -eux; \
    apt-get update; \
    apt-get install -y wget ca-certificates; \
    wget --timeout=600 --tries=5 --retry-connrefused --waitretry=5 --progress=dot:giga \
      -O /tmp/freesurfer_ubuntu22-8.1.0_amd64.deb "${FS8_DEB_URL}"; \
    apt-get install -y /tmp/freesurfer_ubuntu22-8.1.0_amd64.deb; \
    rm -f /tmp/freesurfer_ubuntu22-8.1.0_amd64.deb; \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Install FreeSurfer 8
RUN apt-get update && \
    apt-get install -y ./freesurfer_ubuntu22-8.1.0_amd64.deb && \
    rm freesurfer_ubuntu22-8.1.0_amd64.deb && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set FreeSurfer 8 environment variables
ENV FREESURFER_HOME=/usr/local/freesurfer/8.1.0
ENV FREESURFER=$FREESURFER_HOME
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=$FREESURFER_HOME/license.txt

# Copy FreeSurfer license file
COPY freesurfer_license.txt $FREESURFER_HOME/license.txt

# Clean up FreeSurfer installation - remove unnecessary files
RUN cd $FREESURFER_HOME && \
    # Remove example subjects (keep fsaverage which is needed as template)
    find subjects -mindepth 1 -maxdepth 1 -type d ! -name 'fsaverage*' -exec rm -rf {} + 2>/dev/null || true && \
    # Remove tractography training data
    rm -rf trctrain 2>/dev/null || true && \
    # Remove documentation
    rm -rf docs 2>/dev/null || true && \
    # Remove source code if present
    rm -rf src 2>/dev/null || true && \
# Remove language packs except English
find . -type d -name 'locale' -exec sh -c 'cd {} && ls -1 | grep -v en | xargs rm -rf' \; 2>/dev/null || true && \
# Remove man pages
rm -rf man 2>/dev/null || true

# ============================================
# Stage 2a (prebuilt base): FreeSurfer 8 pulled from ECR
# Built/pushed as: <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:8
# ============================================
FROM <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:8 AS freesurfer-8

# Ensure license is present for downstream stages
ENV FREESURFER_HOME=/usr/local/freesurfer/8.1.0
ENV FREESURFER=$FREESURFER_HOME
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=$FREESURFER_HOME/license.txt
COPY freesurfer_license.txt $FREESURFER_HOME/license.txt


# ============================================
# Stage 2b: FreeSurfer 7 installation (for FastSurfer)
# Buildable base + prebuilt base option
# ============================================
FROM system-base AS freesurfer-7-build

ARG FS7_DEB_URL="https://surfer.nmr.mgh.harvard.edu/pub/dist/freesurfer/7.4.1/freesurfer_ubuntu22-7.4.1_amd64.deb"

# Download and install FreeSurfer 7 in a single layer to avoid shipping the .deb as a separate layer
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt/lists \
    set -eux; \
    apt-get update; \
    apt-get install -y wget ca-certificates; \
    wget --timeout=300 --tries=5 --retry-connrefused --waitretry=5 --progress=dot:giga \
      -O /tmp/freesurfer_ubuntu22-7.4.1_amd64.deb "${FS7_DEB_URL}"; \
    apt-get install -y /tmp/freesurfer_ubuntu22-7.4.1_amd64.deb; \
    rm -f /tmp/freesurfer_ubuntu22-7.4.1_amd64.deb; \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Set FreeSurfer 7 environment variables
ENV FREESURFER_HOME=/usr/local/freesurfer/7.4.1
ENV FREESURFER=$FREESURFER_HOME
ENV FREESURFER7_HOME=$FREESURFER_HOME
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=$FREESURFER_HOME/license.txt

# Copy FreeSurfer license file
COPY freesurfer_license.txt $FREESURFER_HOME/license.txt

# Clean up FreeSurfer installation - remove unnecessary files
RUN cd $FREESURFER_HOME && \
    # Remove example subjects (keep fsaverage which is needed as template)
    find subjects -mindepth 1 -maxdepth 1 -type d ! -name 'fsaverage*' -exec rm -rf {} + 2>/dev/null || true && \
    # Remove tractography training data
    rm -rf trctrain 2>/dev/null || true && \
    # Remove documentation
    rm -rf docs 2>/dev/null || true && \
    # Remove source code if present
    rm -rf src 2>/dev/null || true && \
    # Remove language packs except English
    find . -type d -name 'locale' -exec sh -c 'cd {} && ls -1 | grep -v en | xargs rm -rf' \; 2>/dev/null || true && \
    # Remove man pages
    rm -rf man 2>/dev/null || true

# Prebuilt base that already contains FreeSurfer 7.4.1.
# Built and pushed as: <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:7
FROM <AWS_ACCOUNT_ID>.dkr.ecr.us-east-2.amazonaws.com/freesurfer:7 AS freesurfer-7-base

# Set FreeSurfer 7 environment variables
ENV FREESURFER_HOME=/usr/local/freesurfer/7.4.1
ENV FREESURFER=$FREESURFER_HOME
ENV FREESURFER7_HOME=$FREESURFER_HOME
ENV PATH=$FREESURFER_HOME/bin:$PATH
ENV FS_LICENSE=$FREESURFER_HOME/license.txt

# Copy FreeSurfer license file
COPY freesurfer_license.txt $FREESURFER_HOME/license.txt


# ============================================
# Stage 3a: Python builder (FreeSurfer 8)
# ============================================
FROM freesurfer-8 AS python-builder-8

# Install Python and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    gcc \
    g++ \
    make \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create virtual environment and install Python dependencies
WORKDIR /tmp
COPY requirements.txt .
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/* && \
    find /opt/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f -name '*.pyc' -delete 2>/dev/null || true


# ============================================
# Stage 3b: Python builder (FreeSurfer 7)
# ============================================
FROM freesurfer-7-base AS python-builder-7

# Install Python and build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    gcc \
    g++ \
    make \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Create virtual environment and install Python dependencies
WORKDIR /tmp
COPY requirements.txt .
RUN python3.12 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip /tmp/* /var/tmp/* && \
    find /opt/venv -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
    find /opt/venv -type f -name '*.pyc' -delete 2>/dev/null || true


# ============================================
# Stage 4a: Final runtime (FreeSurfer 8, default)
# ============================================
FROM freesurfer-8 AS runtime

# Install only Python runtime (no dev tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy Python virtual environment from builder
COPY --from=python-builder-8 /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app directory
WORKDIR /app

# Copy application code
COPY functions/ ./functions/
COPY utilities/ ./utilities/
COPY insights/ ./insights/
COPY handlers/ ./handlers/
COPY research/input/ ./research/input/

# Copy FastSurfer submodule
COPY FastSurfer/ ./FastSurfer/

# Set FastSurfer environment variable
ENV FASTSURFER_HOME=/app/FastSurfer

# Create a non-root user
RUN useradd -m -s /bin/bash brainyes && \
    chown -R brainyes:brainyes /app
USER brainyes

# Set the entrypoint
ENTRYPOINT ["python3.12", "handlers/ecs_handler.py"]


# ============================================
# Stage 4b: Final runtime (FreeSurfer 7)
# ============================================
FROM freesurfer-7-base AS runtime-7

# Install only Python runtime (no dev tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-venv \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy Python virtual environment from builder
COPY --from=python-builder-7 /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Create app directory
WORKDIR /app

# Copy application code
COPY functions/ ./functions/
COPY utilities/ ./utilities/
COPY insights/ ./insights/
COPY handlers/ ./handlers/
COPY research/input/ ./research/input/

# Copy FastSurfer submodule
COPY FastSurfer/ ./FastSurfer/

# Set FastSurfer environment variable
ENV FASTSURFER_HOME=/app/FastSurfer

# Create a non-root user
RUN useradd -m -s /bin/bash brainyes && \
    chown -R brainyes:brainyes /app
USER brainyes

# Set the entrypoint
ENTRYPOINT ["python3.12", "handlers/ecs_handler.py"]
