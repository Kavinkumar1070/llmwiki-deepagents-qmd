---
type: concept
title: Semantic Search
tags: [semantic-search, vector-search, embeddings, nlp, retrieval]
sources: [raw/4 Types of Vector Search in RAG.pdf]
updated: 2026-07-13
---

Semantic search retrieves information by understanding the meaning and context of a query instead of matching only literal keywords. The source explains that it uses natural language processing and machine learning to infer intent and semantic relationships.

## How it works
1. Convert queries and documents into dense embedding vectors that capture meaning and context.
2. Compare query and document vectors using similarity metrics such as cosine similarity.
3. Identify relevant content from underlying semantic relationships, even when exact keywords differ.
4. Rank and return the most semantically similar results.

In the source taxonomy, semantic search is one form of [vector-search.md](vector-search.md) and is particularly relevant to RAG because it improves retrieval flexibility when users and documents use different wording for similar ideas.
