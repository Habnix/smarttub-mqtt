#!/bin/bash
# Docker Hub Publishing Script for smarttub-mqtt v0.1.0
# Docker Hub Username: willnix

set -e

echo "🐳 Building Docker image..."
docker build -t willnix/smarttub-mqtt:0.1.0 -t willnix/smarttub-mqtt:latest .

echo ""
echo "✅ Image built successfully!"
echo ""
echo "📊 Image size:"
docker images willnix/smarttub-mqtt:0.1.0

echo ""
echo "🔐 Logging in to Docker Hub..."
echo "Please enter your Docker Hub credentials:"
docker login

echo ""
echo "⬆️  Pushing images to Docker Hub..."
docker push willnix/smarttub-mqtt:0.1.0
docker push willnix/smarttub-mqtt:latest

echo ""
echo "🎉 SUCCESS! Images published to Docker Hub:"
echo "  - https://hub.docker.com/r/willnix/smarttub-mqtt"
echo ""
echo "📦 Available tags:"
echo "  - willnix/smarttub-mqtt:0.1.0"
echo "  - willnix/smarttub-mqtt:latest"
echo ""
echo "🚀 Users can now run:"
echo "  docker pull willnix/smarttub-mqtt:latest"
