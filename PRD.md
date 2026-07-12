# PRD - AI Document Operations System

## Problem

Project 3 created a document operations copilot.

Project 3.5 made that copilot measurable through AgentOps.

The product asks the next operational question:

```text
Can this system move an incoming document from evidence extraction to a controlled operational outcome?
```

Small teams often lose time in repetitive administrative workflows:

- reading incoming invoices or documents
- deciding what kind of work is needed
- validating extracted business data
- asking humans for missing context
- preparing accounting notes or outbound messages
- exporting approved records
- tracking what happened and why

The system should coordinate document intake, evidence review, planning, drafting, and bounded actions while preserving human confirmation.

## Target User

Primary operating users:

- intake operator who uploads and verifies incoming invoices
- administrator or reviewer who resolves exceptions and approves bounded actions

The intake operator and administrator must receive different default screens and navigation. Technical AgentOps and governance surfaces should not dominate the intake workflow.

Secondary users:

- AI engineer evaluating autonomy guardrails
- recruiter or interviewer reviewing a senior portfolio project
- future William turning the portfolio into a deployable product or service offer

## Product Goal

Build a local-first AI Document Operations System that manages a multi-step document task from intake to resolution while preserving explicit approvals, audit trails, and technical evaluation evidence.

## Core User Questions

The system should answer:

- What work came in?
- What type of back-office task is this?
- What data was extracted or missing?
- What should happen next?
- Is this safe to execute automatically?
- Does a human need to approve or correct it?
- What outbound message or accounting note should be drafted?
- Which tool actions were executed?
- Which actions were blocked?
- What local reliability evidence exists for this run?

Every operational screen should also answer:

- What is happening now?
- Who owns the workflow now?
- Why is it waiting?
- What should the user do next?

## In Scope

- back-office work item model
- intake classifier for work type and urgency
- task planner for bounded multi-step workflows
- action policy for read-only, draft-only, confirmation-required, and blocked actions
- operator inbox for pending approvals and escalations
- drafted outbound messages or accounting notes
- controlled execution through existing Project 3 tool boundaries
- technical evidence records for document-operation runs
- Project 4 scenario fixtures for multi-step workflow evaluation
- UI updates for work items, plans, drafts, approvals, and run traces
- role-aware guided invoice flow from upload through submission
- guided reviewer flow from understanding through final decision
- workflow map, owner, waiting reason, next action, and audit-backed activity feed
- tests for policy, planning, execution, workspace boundaries, and AgentOps evaluation
- deployment readiness docs for Docker, CI, and future cloud path

## Out Of Scope

- unrestricted autonomous execution
- real email sending by default
- real payment or bank transfer execution
- billing and subscription management
- Kubernetes production deployment in the first pass
- replacing deterministic safety rules with an LLM-only judge
- claiming production SaaS before real auth, monitoring, backups, deployment, and users exist

## Success Criteria

Project 4 succeeds when:

- a user can create or ingest a back-office work item
- an intake operator can upload, verify, and submit an invoice without understanding the work-item implementation
- a reviewer Inbox contains only items that require human attention
- the system classifies the work type
- the system proposes a plan with explicit risk level per action
- safe read-only steps can run without mutation
- risky steps require confirmation
- blocked steps are refused with a clear reason
- low-confidence work escalates to a human
- drafted messages or notes are reviewable before execution
- Technical Evidence shows local reliability for document-operation runs
- tests prove execution boundaries cannot bypass existing guardrails

## Product Claim

Correct claim:

> A local-first AI Document Operations System that makes extraction evidence visible, applies deterministic validation, routes exceptions to humans, and approval-gates risky execution.

Unsafe claim:

> A fully autonomous enterprise finance operator that can replace back-office staff.
