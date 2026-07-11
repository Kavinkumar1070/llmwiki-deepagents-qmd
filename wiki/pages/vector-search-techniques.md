---
type: concept
title: Vector Search Techniques
tags: [rag, retrieval, vector-search, semantic-search, sparse-search, hybrid-search, multi-vector-search]
sources: [raw/4 Types of Vector Search in RAG.pdf, raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf]
updated: 2026-07-11
---

# Vector Search Techniques

Vector search in RAG retrieves relevant information by representing queries and documents as vectors in a high-dimensional space, then ranking results by similarity rather than exact keyword overlap. Across the sources, the main families discussed are dense semantic search, sparse lexical search, hybrid retrieval, and multi-vector retrieval.

## Core role in RAG

- Vector search improves contextual retrieval by matching semantic meaning, not just exact words, which helps RAG systems answer with better grounding. *(Source: raw/4 Types of Vector Search in RAG.pdf)*
- It is especially useful for large-scale retrieval, recommendation, and question-answering workflows where context and intent matter. *(Source: raw/4 Types of Vector Search in RAG.pdf)*
- In production RAG pipelines, vector search sits between embedding generation/vector storage and the final LLM prompt construction stage. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*

## Retrieval types

### Dense / semantic search

- Dense search embeds both query and documents and compares them with similarity metrics such as cosine similarity. *(Sources: raw/4 Types of Vector Search in RAG.pdf, raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- It is strong for paraphrase and meaning-based matches, even when the same keywords are not present. *(Sources: raw/4 Types of Vector Search in RAG.pdf, raw/GenAI_RAG_Agents_Multiagent.pdf)*
- Its weakness is exact keyword, identifier, or code matching. *(Source: raw/GenAI_RAG_Agents_Multiagent.pdf)*

### Sparse / lexical search

- Sparse vector search focuses on representations with many zero values and is well suited to term-focused retrieval methods such as TF-IDF or BM25-style matching. *(Sources: raw/4 Types of Vector Search in RAG.pdf, raw/GenAI_RAG_Agents_Multiagent.pdf)*
- It emphasizes non-zero features and can use indexing structures such as inverted indexes or locality-sensitive hashing for speed. *(Source: raw/4 Types of Vector Search in RAG.pdf)*
- Sparse retrieval has no semantic understanding, but it works well for exact terms, product names, and codes. *(Source: raw/GenAI_RAG_Agents_Multiagent.pdf)*

### Hybrid search

- Hybrid search combines dense semantic retrieval with sparse keyword retrieval and merges their scores to improve recall and robustness. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- One source frames hybrid search as a major optimization strategy and claims about a 30% retrieval accuracy improvement in practice. *(Source: raw/RAG complete guide.pdf)*

### Multi-vector search

- Multi-vector retrieval uses more than one vector per document chunk, with one source specifically citing ColBERT-style token-level representations. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- The tradeoff described is higher retrieval accuracy at the cost of greater storage and compute requirements, making it better for high-value queries than for every request. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*

### Exact and approximate nearest-neighbor search

- Exact nearest-neighbor search computes distances against the full dataset and returns the true closest vectors, but can be expensive at scale. *(Source: raw/4 Types of Vector Search in RAG.pdf)*
- Approximate nearest-neighbor search speeds retrieval by partitioning or indexing the dataset and returning a close-enough result instead of the mathematically exact nearest neighbor. *(Source: raw/4 Types of Vector Search in RAG.pdf)*

## Operational considerations

- Retrieval quality strongly affects final answer quality in RAG, so search type choice is an architectural decision rather than a minor tuning detail. *(Source: raw/RAG complete guide.pdf)*
- Related optimization strategies include reranking, query rewriting, contextual compression, caching, and metadata filtering. See [rag-implementation-patterns.md](rag-implementation-patterns.md).
- Agent-based systems may treat retrieval as a callable tool rather than a fixed pipeline step. See [agentic-rag.md](agentic-rag.md).
- A broader layer-by-layer framing of GenAI, RAG, agents, and multi-agent systems is captured in [genai-rag-agents-multi-agent-systems.md](genai-rag-agents-multi-agent-systems.md).
