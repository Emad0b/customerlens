# Methodology

## Temporal protocol

Each snapshot includes customers with a positive purchase in the previous 90 days. Features use only that lookback window. Labels measure a positive repeat purchase and signed net revenue in the next 90 days.

Training cutoff: 2011-03-14 (1,585 customers). Validation: 2011-06-12 (1,983). Test: 2011-09-10 (1,907). Outcome windows are disjoint; the final outcome ends exclusively at 2011-12-09. Customers may recur across snapshots, as they would in repeated scoring of an existing customer base. This does not establish performance for unseen customers.

Models and scaling fit the training cohort only. Validation Brier score chooses the classifier; validation MAE chooses the revenue estimator. Test results are reported once without selecting the winner on test performance. This experiment does not estimate uncertainty across multiple temporal folds.

## Cleaning and predictors

Exact duplicates, missing customer identifiers and invalid/nonpositive price rows are removed. Credits remain negative net revenue, but never count as positive repeat purchases. The source's final partial day is excluded. Of 541,909 original rows, 400,947 remain; 135,037 missing-customer rows are excluded after deduplication, a material selection bias.

Predictors: recency, invoice frequency, net spend, gross spend, basket value, product breadth, credit share and active purchase days. Customer identity, country and future outcomes are not predictors. Raw customer IDs are replaced with truncated SHA-256 labels in the browser artifact; these are pseudonymous and potentially linkable to public source data.

RFM segments are interpretable rules rather than fitted clusters. The high-spend threshold is the training-only 75th percentile (GBP 756.81). Champions require recent, repeated purchases and that spend threshold; Cooling customers have over 60 days' recency. Other rules are explicit in the pipeline.

## Evaluation

Classification includes ROC AUC, average precision, Brier score, calibration bins, top-20% precision and ranking lift. Revenue includes absolute error against constant and trailing-spend baselines. Sales revenue is not profit or lifetime value. Top-audience comparisons are observed historical outcomes, not causal treatment effects.

Cohorts use the first observed purchase month; existing customers are left-censored at the dataset start. Observable months with no repeat purchases are zero; future/unobserved months are blank. The final incomplete month is excluded from retention.

## Limits and next experiments

One retailer and one final temporal window limit generalisation. Seasonal demand and the changing repeat-purchase base rate can affect calibration. Missing identifiers disproportionately exclude anonymous transactions. Revenue's heavy tail is difficult for the selected estimator. Before operational use, evaluate rolling temporal folds, bootstrap customer-level uncertainty, subgroup calibration, profit-aware objectives and a randomised campaign trial. Do not tune against this final test repeatedly.

The dashboard serves a committed benchmark, not live inference. Rebuilding requires the raw source download, Python dependencies and the pipeline command. A local SQLite copy provides a transaction audit; it is not deployed as a multi-user service.
