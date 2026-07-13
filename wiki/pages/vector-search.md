---
type: concept
title: Vector Search
tags: [vector-search, embeddings, retrieval, rag]
sources: [raw/4 Types of Vector Search in RAG.pdf]
updated: 2026-07-13
---

Vector search retrieves relevant information by representing text as vectors in a high-dimensional space and comparing semantic similarity rather than exact keyword overlap. According to [raw/4 Types of Vector Search in RAG.pdf], it relies on embeddings that convert words, sentences, or documents into dense numerical representations and then measures proximity with metrics such as cosine similarity.

The source frames vector search as important in Retrieval-Augmented Generation (RAG) because it improves context understanding, handles synonyms, supports efficient retrieval across large datasets, and often yields more accurate and relevant results than keyword search alone. It also notes applications in document retrieval, recommendation systems, and question answering.

## Related techniques
- [exact-nearest-neighbor-search.md](exact-nearest-neighbor-search.md) describes exhaustive nearest-neighbor retrieval for exact results.
- [approximate-nearest-neighbor-search.md](approximate-nearest-neighbor-search.md) describes faster but inexact retrieval optimized for scale.
- [semantic-search.md](semantic-search.md) focuses on meaning and intent rather than literal keyword matching.
- [sparse-vector-search.md](sparse-vector-search.md) covers retrieval over sparse high-dimensional representations with many zero values.

## Future directions
The source predicts future vector search systems will improve in accuracy, scalability, multimodal support, personalization, real-time responsiveness, and adoption across industries for knowledge management and decision-making. These expectations are summarized from [raw/4 Types of Vector Search in RAG.pdf].
