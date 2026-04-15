# Narrative taxonomy

User-editable list of narrative tags Gold Digger uses to categorise projects and filter scout results. Edit freely — add new narratives as they emerge.

## ai-crypto

Umbrella tag for any crypto project with a meaningful AI component.

**Keywords:** ai, artificial intelligence, ml, machine learning, neural, llm
**Seeds:** openserv, ai16z, virtuals, fetch-ai

## ai-agents

Autonomous agent platforms and agent frameworks on-chain.

**Keywords:** agent, agentic, autonomous, agent swarm, agent framework, agent platform
**Seeds:** ai16z, virtuals, openserv, reppo

## ai-infra

Compute, data, inference infrastructure for AI.

**Keywords:** gpu, compute, inference, training, decentralized compute, data availability
**Seeds:** bittensor, io-net, akash-network, render-token

## ai-data

Decentralized data markets and data-for-AI.

**Keywords:** data market, data availability, training data, labeled data
**Seeds:** ocean-protocol, grass, vana

## depin

Decentralized physical infrastructure networks.

**Keywords:** depin, decentralized physical infrastructure, device mining, physical network
**Seeds:** helium, hivemapper, iotex, dimo

## restaking

Liquid restaking and AVS ecosystems.

**Keywords:** restaking, liquid restaking, avs, eigen
**Seeds:** eigenlayer, ether-fi, puffer-finance, kelp-dao

## intents

Intent-based protocols and solvers.

**Keywords:** intent, solver, cowswap-style, declarative
**Seeds:** anoma, across, 1inch-fusion

## rwa

Real-world assets and tokenized securities.

**Keywords:** rwa, real world asset, tokenized treasury, tokenized equity
**Seeds:** ondo, maker, centrifuge

## prediction-markets

Decentralized prediction / forecasting.

**Keywords:** prediction market, forecast, oracle, polymarket-style
**Seeds:** polymarket, kalshi, augur

---

## Adding a narrative

Append a new section with:
1. A short lowercase-kebab tag name
2. **Keywords:** comma-separated list used for fuzzy matching in scout output
3. **Seeds:** list of slugs that canonically embody the narrative (used to find similar projects via Exa semantic search)

Gold Digger reads this file at runtime — no code changes needed.
