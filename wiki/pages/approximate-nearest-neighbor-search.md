---
type: concept
title: Approximate Nearest Neighbor Search
tags: [vector-search, ann, nearest-neighbor, retrieval]
sources: [raw/4 Types of Vector Search in RAG.pdf]
updated: 2026-07-13
---

Approximate Nearest Neighbor (ANN) search aims to find a neighbor that is close enough to the query while reducing search time compared with exact search. In [raw/4 Types of Vector Search in RAG.pdf], it is presented as a speed-accuracy tradeoff that is especially useful for large datasets.

## How it works
1. Transform the query and dataset items into vectors in high-dimensional space.
2. Partition the dataset into smaller subsets using methods such as hashing, tree-based structures, or clustering.
3. Search within the most relevant partition instead of the full dataset.
4. Return an approximate nearest neighbor rather than guaranteeing the exact closest point.

This makes ANN a practical complement to [exact-nearest-neighbor-search.md](exact-nearest-neighbor-search.md) within [vector-search.md](vector-search.md), especially when latency or scale matter more than exactness.
