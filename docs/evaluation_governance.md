# Evaluation Governance

Status: implemented local evaluation governance.

The benchmark engine provides a quality-control layer for provider decisions.

## Purpose

Evaluation governance answers:

- Did extraction quality improve, stay stable, or regress?
- Did provider error rate increase?
- Did latency or estimated cost increase too much?
- Is the dataset large enough to support the claim being made?

## Golden Dataset Strategy

Use small, curated datasets first:

```text
examples/benchmark/datasets/simple_two
examples/benchmark/datasets/pdf_sample
```

Evidence labels:

- `bootstrap`: fewer than 5 documents; architecture and smoke evidence only.
- `small_golden_set`: 5-29 documents; useful for regression checks, still limited.
- `expanded_golden_set`: 30+ documents; stronger evidence, still not universal accuracy.

## Regression Checks

The governance report compares a current benchmark report against an optional baseline report.

Default regression thresholds:

- field accuracy drop greater than 2 percentage points
- document success drop greater than 5 percentage points
- provider error rate increase greater than 5 percentage points
- average latency increase greater than 25 percent
- estimated cost increase greater than 25 percent

## Decision Evidence

The governance report carries:

- field accuracy
- document success rate
- provider error rate
- average latency
- estimated total cost
- evidence limitations

This keeps provider decisions business-readable without claiming production accuracy from a tiny dataset.

## Boundaries

This is not full MLOps.

Deferred:

- model registry
- scheduled benchmark jobs
- production drift monitoring
- statistically large benchmark claims
