#!/bin/bash

# GitKeeper - GitHub Repository Management Tool
# This script activates the virtual environment and starts the TUI application

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}🛡️  Starting GitKeeper...${NC}"

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ Virtual environment not found. Please run 'python -m venv .venv' first.${NC}"
    exit 1
fi

# Check if requirements are installed
if [ ! -f ".venv/lib/python*/site-packages/textual/__init__.py" ]; then
    echo -e "${BLUE}📦 Installing requirements...${NC}"
    .venv/bin/pip install -r requirements.txt
fi

# Activate virtual environment and start the application
echo -e "${GREEN}🎯 Launching TUI application...${NC}"
echo ""

# Run the TUI application
.venv/bin/python tui_app.py

echo ""
echo -e "${BLUE}👋 GitKeeper closed.${NC}"