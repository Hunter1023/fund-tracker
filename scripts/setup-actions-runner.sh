#!/bin/bash

set -e

echo "🔧 Setting up GitHub Actions Self-Hosted Runner in WSL..."

echo "📦 Checking dependencies..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

if ! command -v jq &> /dev/null; then
    echo "❌ jq is not installed. Installing jq..."
    sudo apt-get update
    sudo apt-get install -y jq
fi

echo "✅ Docker, Docker Compose and jq are installed."

echo "📥 Downloading GitHub Actions Runner v2.318.0..."
# 使用固定版本 2.318.0（当前最稳定版本）
RUNNER_VERSION="2.318.0"
RUNNER_DIR="$HOME/actions-runner"

if [ -d "$RUNNER_DIR" ]; then
    echo "⚠️  Runner directory already exists at $RUNNER_DIR"
    read -p "Do you want to remove it and reinstall? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf "$RUNNER_DIR"
    else
        echo "❌ Installation cancelled."
        exit 1
    fi
fi

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

curl -o actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz -L https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

echo "📦 Extracting runner..."
tar xzf ./actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz
rm actions-runner-linux-x64-${RUNNER_VERSION}.tar.gz

echo "✅ Setup completed!"
echo ""
echo "📋 Next steps:"
echo "1. Go to your GitHub repository"
echo "2. Navigate to Settings > Actions > Runners"
echo "3. Click 'New self-hosted runner'"
echo "4. Copy the configuration command and run it:"
echo "   cd $RUNNER_DIR"
echo "   ./config.sh --url <your-repo-url> --token <your-token>"
echo ""
echo "5. Install and start the service:"
echo "   sudo ./svc.sh install"
echo "   sudo ./svc.sh start"
