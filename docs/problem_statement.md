# Problem Statement: Mutual Fund FAQ Assistant (Facts-Only Q&A)

## Overview

The objective of this project is to build a **facts-only FAQ assistant** for mutual fund schemes, using Groww as the reference product context. The assistant will answer objective, verifiable queries related to mutual funds by retrieving information exclusively from official public sources, such as AMC (Asset Management Company) websites, AMFI, and SEBI.

The system must strictly avoid providing investment advice, opinions, or recommendations. Every response must include a single, clear source link and adhere to defined constraints around clarity, accuracy, and compliance.

## Objective

Design and implement a lightweight Retrieval-Augmented Generation (RAG)-based assistant that:

- Answers factual queries about mutual fund schemes
- Uses a curated corpus of official documents
- Provides concise, source-backed responses

## Target Users

- Retail investors comparing mutual fund schemes
- Customer support and content teams handling repetitive mutual fund queries

## Scope of Work

### 1. Corpus Definition

- Select one Asset Management Company (AMC)
- Choose 3–5 mutual fund schemes, ensuring category diversity (e.g., large-cap, flexi-cap, ELSS)

**Selected schemes (HDFC AMC — Groww reference links):**

| Scheme | Category | Reference |
|--------|----------|-----------|
| HDFC Mid Cap Fund - Direct Growth | Mid Cap | [groww.in](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |
| HDFC Silver ETF FoF - Direct Growth | Commodity / FoF | [groww.in](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth) |
| HDFC BSE Sensex Index Fund - Direct Growth | Index | [groww.in](https://groww.in/mutual-funds/hdfc-bse-sensex-index-fund-direct-growth) |
| HDFC Large Cap Fund - Direct Growth | Large Cap | [groww.in](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| HDFC ELSS Tax Saver Fund - Direct Plan Growth | ELSS | [groww.in](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) |

### 2. FAQ Assistant Requirements

The assistant must answer facts-only queries, such as:

- Expense ratio of a scheme
- Exit load details
- Minimum SIP amount
- ELSS lock-in period
- Riskometer classification
- Benchmark index
- Process to download statements or capital gains reports

**Response format requirements:**

- Each response is limited to a maximum of **3 sentences**
- Each response includes **exactly one citation link**
- Each response includes a footer: `Last updated from sources: <date>`

### 3. Refusal Handling

The assistant must refuse non-factual or advisory queries, such as:

- “Should I invest in this fund?”
- “Which fund is better?”

Refusal responses should:

- Be polite and clearly worded
- Reinforce the facts-only limitation
- Provide a relevant educational link (e.g., AMFI or SEBI resource)

### 4. User Interface (Minimal)

The solution should include a simple interface with:

- A welcome message
- Three example questions
- A visible disclaimer: **“Facts-only. No investment advice.”**

## Constraints

### Data and Sources

- Use only official public sources (AMC, AMFI, SEBI)
- Do not use third-party blogs or aggregator websites

### Privacy and Security

Do not collect, store, or process:

- PAN or Aadhaar numbers
- Account numbers
- OTPs
- Email addresses or phone numbers

### Content Restrictions

- No investment advice or recommendations
- No performance comparisons or return calculations
- For performance-related queries, provide a link to the official factsheet only

### Transparency

- Responses must be short, factual, and verifiable
- Every answer must include a source link and last updated date

## Expected Deliverables

### README Document

- Setup instructions
- Selected AMC and schemes
- Architecture overview (RAG approach)
- Known limitations

### Disclaimer Snippet

> Facts-only. No investment advice.

## Success Criteria

- Accurate retrieval of factual mutual fund information
- Strict adherence to facts-only responses
- Consistent inclusion of valid source citations
- Proper refusal of advisory queries
- Clean, minimal, and user-friendly interface

## Summary

The goal is to build a trustworthy, transparent, and compliant mutual fund FAQ assistant that prioritizes **accuracy over intelligence**. The system should ensure that users receive only verified, source-backed financial information, without any advisory bias or speculative content.
