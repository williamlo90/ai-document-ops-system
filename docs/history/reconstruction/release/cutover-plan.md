# Cutover Plan

## Preconditions

1. Confirm the original all-refs bundle hash.
2. Confirm `reconstruction-m01` through `reconstruction-m15` resolve locally.
3. Confirm the staging working tree is clean.
4. Review the final acceptance record and source snapshots.
5. Confirm no `.env`, private invoice pack, runtime database, or provider credential is tracked.

## Remote Change

Perform one push only after approval. Preserve the existing remote before changing its default branch history. Push the reconstructed branch and tags as a new reviewable branch first; do not force-update `main` as the first remote action.

## Rollback

If review fails, leave the existing remote default branch unchanged. The original clone and verified all-refs bundle remain the recovery sources.

## Current State

Prepared only. No GitHub push was performed during reconstruction.
