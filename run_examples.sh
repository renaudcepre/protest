#!/bin/bash
set -e

echo "========================================"
echo "Yorkshire Terrier Test Suite"
echo "========================================"

EXAMPLES=(
    "run examples.yorkshire.session:session"
    "run examples.yorkshire.session:session -n 4"
    "run examples.yorkshire.session:session --tag puppy"
    "run examples.yorkshire.session:session --tag legacy"
    "run examples.yorkshire.session:session --no-tag slow"
    "run examples.yorkshire.session:session::Seniors"
    "run examples.yorkshire.session:session::Adults::Workers"
    "run examples.yorkshire.session:session::Legacy -n 4"
    "run examples.yorkshire.session:session -k fax"
    "run examples.yorkshire.session:session -k nap"
    "run examples.yorkshire.session:session --collect-only"
    "tags list examples.yorkshire.session:session"
)

FAILED=0

for example in "${EXAMPLES[@]}"; do
    echo ""
    echo "----------------------------------------"
    echo "protest $example"
    echo "----------------------------------------"
    if uv run protest $example; then
        echo "  OK"
    else
        echo "  FAILED (expected)"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "========================================"
echo "Done ($FAILED expected failures)"
echo "========================================"
