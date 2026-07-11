---
type: concept
title: Agentic RAG
tags: [rag, agents, tool-use, multi-hop-retrieval, langgraph, llamaindex]
sources: [raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf]
updated: 2026-07-11
---

# Agentic RAG

Agentic RAG is a retrieval-augmented generation pattern in which retrieval is treated as a tool the model can choose to call, rather than as a mandatory fixed step before every answer. The sources frame this as a shift toward more adaptive systems that decide whether retrieval is needed, when to repeat it, and how to use retrieved results across multi-step tasks.

## Core idea

- In standard RAG, retrieval is usually a fixed stage in the query → retrieve → augment → generate pipeline. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- In agentic RAG, the model or agent decides if retrieval is necessary for a given query. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- The agent can re-query when the first retrieval pass leaves gaps, enabling multi-hop retrieval for more complex questions. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- Tool-calling loops can replace a rigid retrieve-then-generate pipeline. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*

## Why it matters

- This approach can reduce unnecessary retrieval calls on simple queries that do not need outside knowledge. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- It is better suited to multi-part or multi-hop questions that single-pass RAG may miss. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*
- It connects retrieval quality with broader agent behaviors such as planning, tool use, reflection, and iterative correction. *(Source: raw/GenAI_RAG_Agents_Multiagent.pdf)*

## Relationship to agent systems

- The agent loop described in the source includes planning, tool use, memory, and reflection. Retrieval becomes one tool among others such as APIs, search, or code execution. *(Source: raw/GenAI_RAG_Agents_Multiagent.pdf)*
- ReAct-style behavior is one relevant template: reason, act via a tool, observe, and loop until the task is complete. *(Source: raw/GenAI_RAG_Agents_Multiagent.pdf)*
- Agentic RAG therefore sits between conventional RAG and broader tool-using agent architectures. See [genai-rag-agents-multi-agent-systems.md](genai-rag-agents-multi-agent-systems.md).

## Supporting frameworks

- Frameworks named for this pattern include LangGraph, LlamaIndex Agents, and custom agent loops. *(Sources: raw/GenAI_RAG_Agents_Multiagent.pdf, raw/RAG complete guide.pdf)*

## Related implementation considerations

- Retrieval type choices such as dense, sparse, hybrid, and multi-vector search still matter in agentic RAG. See [vector-search-techniques.md](vector-search-techniques.md).
- The broader operational concerns of chunking, embeddings, reranking, compression, caching, and evaluation still apply. See [rag-implementation-patterns.md](rag-implementation-patterns.md).
