#!/bin/bash
# Seed Hindsight with EUR-Lex corpus if needed
# Usage: ./scripts/seed-hindsight-if-needed.sh

set -e

echo "=== HINDSIGHT SEEDING SCRIPT ==="
echo ""

# Check if Hindsight data directory has content
if [ -d "~/.hindsight-data" ] && [ "$(ls -A ~/.hindsight-data 2>/dev/null | wc -l)" -gt 0 ]; then
    echo "✓ Hindsight data directory has content"
    
    # Try to test if Hindsight is running and has data
    if curl -s http://localhost:8600/health >/dev/null 2>&1; then
        echo "✓ Hindsight is running"
        
        # Test recall query using the correct v1 API endpoint
        REPLY=$(curl -s -X POST http://localhost:8600/v1/default/banks/evidence-eu-docs/memories/recall \
            -H "Content-Type: application/json" \
            -d '{"query": "What is Article 6 GDPR?"}' 2>/dev/null)
        
        if echo "$REPLY" | grep -q '"results"'; then
            echo "✓ Hindsight already has data (recall returned results)"
            echo "✗ No seeding needed"
            exit 0
        fi
        echo "✗ Hindsight running but no data found"
    else
        echo "✗ Hindsight is not running"
        echo "Please start Hindsight first: cd deploy/local && docker compose up -d hindsight"
        exit 1
    fi
else
    echo "✗ Hindsight data directory is empty"
fi

echo ""
echo "=== SEEDING HINDSIGHT ==="
echo ""

# Check if Mistral API key is set
if [ -z "$MISTRAL_API_KEY" ]; then
    echo "✗ MISTRAL_API_KEY not set"
    echo "Please set MISTRAL_API_KEY in your environment or .env file"
    exit 1
fi

# Check if Hindsight auth token is needed
# For local self-hosted Hindsight, auth is typically disabled
HINDSIGHT_AUTH_TOKEN=""

# Run the seed script
python3 backend/scripts/seed_hindsight.py \
    --base-url http://localhost:8600 \
    --auth-token "$HINDSIGHT_AUTH_TOKEN"

echo ""
echo "=== SEEDING COMPLETE ==="
echo ""
echo "✓ Hindsight seeded with EUR-Lex documents"
echo "✓ Mistral API tokens were used for RETAIN operations"
echo "✓ Data stored in ~/.hindsight-data (persistent)"
echo ""
echo "Next steps:"
echo "1. Verify: curl -X POST http://localhost:8600/v1/default/banks/evidence-eu-docs/memories/recall -H 'Content-Type: application/json' -d '{\"query\": \"What is Article 6 GDPR?\"}'"
echo "2. Start Cloudflare Tunnel if needed"
echo "3. Test external access via Tunnel URLs"
