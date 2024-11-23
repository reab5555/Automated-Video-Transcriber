#!/bin/bash

# Configuration
PROJECT_ID="python-code-running"
REGION="me-west1"
REPO_NAME="transcriberrep"
IMAGE_NAME="transcriber"
TAG="latest"

# Full image path
FULL_IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_NAME}:${TAG}"

# Create the repository if it doesn't exist
echo "Creating Artifact Registry repository if it doesn't exist..."
gcloud artifacts repositories create $REPO_NAME \
    --repository-format=docker \
    --location=$REGION \
    --description="Transcriber Repository"

# Configure Docker for Artifact Registry
echo "Configuring Docker for Artifact Registry..."
gcloud auth configure-docker ${REGION}-docker.pkg.dev

# Build the image
echo "Building Docker image..."
docker build -t $FULL_IMAGE_PATH .

# Push the image
echo "Pushing image to Artifact Registry..."
docker push $FULL_IMAGE_PATH

echo "Complete! Image is available at: $FULL_IMAGE_PATH"