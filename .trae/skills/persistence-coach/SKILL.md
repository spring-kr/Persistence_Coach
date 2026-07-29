---
name: "persistence-coach"
description: "AI health agent that analyzes exercise logs, detects passion decay early, and provides state-specific coaching to maintain long-term consistency. Invoke when user wants to run or deploy the persistence coach AI agent."
---

# Persistence Coach AI Agent

## What it does
This skill deploys and manages the AI persistence coach system that helps users maintain long-term exercise consistency (uptime, not 1RM). It uses a deterministic judgment core with state machine logic to:
1. Analyze weekly exercise signals (session count, duration, exercise diversity)
2. Detect early passion decay signals before users drop out
3. Provide state-specific coaching interventions based on 20 years of lifter experience
4. Handle special parallel mode exit triggers (risk signals/environmental constraints)

## Core Components Integrated
- `judgment_core.py`: 5-state FSM (ACTIVE→DECLINING→PARALLEL→DORMANT→RETURNING)
- `dialogue_layer.py`: LLM prompt builder with safe guardrails
- `persistence_coach_demo.html`: Interactive web demo for testing
- Synthetic data validation pipeline

## When to invoke
- User asks to create/build the AI health agent
- Need to run validation tests on the judgment core
- Want to start the demo server to test the agent
- Need to extend the coaching corpus with new rules
- Deploy the agent for real user usage

## Usage
1. First validate the core logic: `python validate_core.py`
2. Start the demo to interact with the agent
3. Review state transitions and coaching messages
4. Extend the corpus with new user interview data as needed