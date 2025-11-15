#!/bin/bash
# Run all Scene Planner tests

echo "Running Scene Planner tests..."
echo "================================"

# Run pytest with coverage
pytest project/backend/modules/scene_planner/tests/ \
    -v \
    --tb=short \
    --cov=modules.scene_planner \
    --cov-report=term-missing \
    --cov-report=html:htmlcov/scene_planner

echo ""
echo "Test coverage report generated in htmlcov/scene_planner/"

