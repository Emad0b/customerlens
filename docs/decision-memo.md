# Decision memo

Use repeat-purchase scores as a hypothesis for prioritising customer research. The validation-selected logistic model achieves test AUC 0.696 and Brier 0.201. The top 20% have observed repeat rate 92.7%, compared with the cohort base rate of 69.0%.

Do not interpret ranking lift as incremental marketing impact. Customers already likely to return may not benefit most from an intervention. A randomised, profit-measured experiment is required before choosing a contact policy.

Do not promote the revenue estimator on this evidence. Gradient boosting wins validation MAE (GBP 530.74 versus GBP 545.42 for trailing spend) but loses on test (GBP 869.46 versus GBP 841.54). Preserve the simpler baseline while investigating temporal stability and the long-tailed outcome distribution with a new evaluation protocol.

This portfolio demonstrates reproducibility and honest model comparison rather than claiming production readiness. Suitable next work includes rolling-origin validation, interval estimates and monitored calibration with clearly defined acceptance criteria.
