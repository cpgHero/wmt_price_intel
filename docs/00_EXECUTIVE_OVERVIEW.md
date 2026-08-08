# Executive Overview

## Product decision

Build a standalone Retail Competitive Intelligence application, separate from CPGHero. The target workflow is retailer-side competitive price and assortment intelligence rather than supplier/broker digital-shelf intelligence.

## Product thesis

Retailer search data becomes decision-useful only after the application can answer four questions reproducibly:

1. What products actually belong to the category?
2. Which products are truly comparable?
3. What is the local price/availability position against the benchmark retailer?
4. Which gaps are broad, durable, actionable, and trustworthy enough to escalate?

## Reusable architecture

The system is composed of two independent plug-in/configuration axes:

- **Retailer Adapters:** how to collect and normalize retailer data.
- **Product Packs:** how to classify, normalize, match, compare, validate, and report a category.

A new retailer must not require changing egg logic. A new product category must not require changing Amazon logic.

## Canonical workflow

Collection Definition -> Cost Estimate -> Collection Run -> Raw Page Artifacts -> Normalized Offers -> Product Pack Classification -> Deterministic Matching/Analytics -> Validation -> Canonical AnalysisResult -> Web UI / HTML / Excel / Leadership Email / Alerts.

## V1 benchmark

Walmart is the benchmark retailer. V1 collection adapters: Walmart US, ALDI US, Amazon Same Day US. Additional retailer endpoints are catalogued for later activation.
