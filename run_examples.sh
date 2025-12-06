#!/bin/bash
set -e

echo "========================================"
echo "Running all ProTest examples"
echo "========================================"

EXAMPLES=(
#    "run examples.basic.demo:session"
#    "run examples.basic.demo_async:session"
#    "run examples.basic.demo_async:session -n 4"
#    "run examples.basic.demo_capture:session"
#    "run examples.basic.demo_capture:session -s"
#    "run examples.basic.caplog_demo:session"
#    "run examples.basic.factory_demo:session"
#    "run examples.basic.nested_suites:session"
#    "run examples.basic.parameterized_factory_demo:session"
#    "run examples.basic.skip_demo:session"
#    "run examples.basic.xfail_demo:session"
    "run examples.basic.timeout_demo:session"
    "run examples.basic.timeout_demo:session -n 4"
    "run examples.basic.timeout_demo:session_with_failures"
#    "run examples.basic.parametrize_demo:session"
#    "run examples.basic.parametrize_demo:session -n 10"
#    "run examples.basic.demo:session --lf"
#    "run tags_demo:session --app-dir examples"
#    "run tags_demo:session --app-dir examples --tag unit"
#    "run tags_demo:session --app-dir examples --tag database"
#    "run tags_demo:session --app-dir examples --no-tag slow"
#    "tags list tags_demo:session --app-dir examples"
#    "tags list -r tags_demo:session --app-dir examples"
#    "run parallel_demo:session --app-dir examples"
#    "run parallel_demo:session --app-dir examples -n 10"
#    "run examples.basic.factory_demo:session -x"
#    "run filtering_demo:session --app-dir examples"
#    "run filtering_demo:session::API --app-dir examples"
#    "run filtering_demo:session::API::Users --app-dir examples"
#    "run filtering_demo:session --app-dir examples -k create"
#    "run filtering_demo:session --app-dir examples -k create -k delete"
#    "run filtering_demo:session --app-dir examples -t slow"
#    "run filtering_demo:session --app-dir examples --no-tag slow"
#    "run filtering_demo:session::API --app-dir examples -k user -t slow"
)

FAILED=0

for example in "${EXAMPLES[@]}"; do
    echo ""
    echo "----------------------------------------"
    echo "Running: $example"
    echo "----------------------------------------"
    if time uv run protest $example; then
        echo "✓ $example passed"
    else
        echo "✗ $example FAILED"
        FAILED=$((FAILED + 1))
    fi
done

echo ""
echo "========================================"
if [ $FAILED -eq 0 ]; then
    echo "All examples passed!"
else
    echo "$FAILED example(s) failed"
    exit 1
fi

