---
type: concept
title: Exact Nearest Neighbor Search
tags: [vector-search, nearest-neighbor, retrieval]
sources: [raw/4 Types of Vector Search in RAG.pdf]
updated: 2026-07-13
---

Exact Nearest Neighbor (ENN) search finds the closest data points to a query in high-dimensional space by computing distances against the full dataset and returning the point or points with the smallest distance. The source describes this as an exact method rather than an approximation.

## How it works
1. Represent the query and data points as vectors.
2. Compute the distance from the query vector to each data point using a metric such as Euclidean or Manhattan distance.
3. Compare those distances across the dataset.
4. Return the closest point or points as the exact nearest neighbors.

Within the taxonomy in [vector-search.md](vector-search.md), ENN is the most precise of the techniques described in [raw/4 Types of Vector Search in RAG.pdf], but the source also implies that exhaustive comparison can be less practical at large scale than [approximate-nearest-neighbor-search.md](approximate-nearest-neighbor-search.md).
