---
type: concept
title: Sparse Vector Search
tags: [vector-search, sparse-vectors, retrieval, indexing]
sources: [raw/4 Types of Vector Search in RAG.pdf]
updated: 2026-07-13
---

Sparse vector search works with high-dimensional vectors that contain many zero-valued features and is useful when only a small subset of features is relevant. [raw/4 Types of Vector Search in RAG.pdf] gives text representations such as TF-IDF as an example context for this approach.

## How it works
1. Represent queries and data points as sparse vectors.
2. Use distance or similarity metrics that focus on non-zero elements, such as cosine similarity or Jaccard index.
3. Index vectors using structures such as inverted indexes or locality-sensitive hashing.
4. Retrieve the closest data points while efficiently filtering out irrelevant ones.
5. Rank and return results according to similarity.

This is another technique grouped under [vector-search.md](vector-search.md), distinguished by its emphasis on sparse rather than dense representations.
