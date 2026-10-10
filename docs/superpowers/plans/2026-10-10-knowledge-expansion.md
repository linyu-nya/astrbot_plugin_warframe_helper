# Knowledge Corpus Expansion Implementation Plan

**Goal:** Replace shallow summaries with useful Chinese topic knowledge, preserving the approved persona RAG and administrator-maintenance workflow.

**Architecture:** Keep the existing pack ID and the original 25 titles/IDs so managed imports update in place. Expand to 40 independently written topics with mechanisms, procedures and pitfalls. Source URLs are provenance, never a substitute for embedded body text. No Huiji crawling or new retrieval service.

**Tech Stack:** JSON corpus, Markdown export, Python and pytest; existing AstrBot document upload and embedding.

## Tasks
- [x] Add corpus-depth and complete-export regression tests; observe failures on the old corpus.
- [x] Verify official guides, support FAQs and superseding update notes. Avoid outdated progression requirements; distinguish historical numeric rules from live state.
- [x] Expand all original topics and add 15 topics covering inventory, trading, clans, Focus, progression, bounties, calendar and Viral status.
- [x] Extend paraphrased retrieval evaluation to cover every topic without silently dropping cases.
- [x] Verify old managed documents upgrade, repeated import skips, and administrator edits remain intact.
- [x] Update release notes and installation guidance, run the full suite, export both ZIPs and verify archive contents.

## Acceptance
At least 40 topics, at least 12,000 body characters, at least three meaningful sections per topic; each source checked individually. This does not establish production semantic recall or latency. Existing chat/RAG behavior is unchanged. UI-uploaded documents are not automatically migrated by the plugin: managed imports and manual upload require separate instructions.
