-- Seed data for feedback dashboard development/testing
-- 45 rows spread across 3 teams over 7 days with realistic questions and mixed votes

INSERT INTO feedback (created_at, space, question, vote) VALUES
-- CI-CD team (15 rows)
('2026-03-28 09:12:00+00', 'CI-CD', 'How do I trigger a manual pipeline run?', 'up'),
('2026-03-28 14:33:00+00', 'CI-CD', 'What is the CI/CD pipeline?', 'up'),
('2026-03-29 08:45:00+00', 'CI-CD', 'How do I roll back a failed deployment?', 'up'),
('2026-03-29 11:22:00+00', 'CI-CD', 'Where are the Jenkins build logs stored?', 'down'),
('2026-03-29 15:05:00+00', 'CI-CD', 'How long does a typical build take?', 'up'),
('2026-03-30 09:00:00+00', 'CI-CD', 'What branch strategy do we use?', 'up'),
('2026-03-30 10:17:00+00', 'CI-CD', 'How do I set up a new CI/CD pipeline?', 'up'),
('2026-03-30 13:44:00+00', 'CI-CD', 'What happens when a build fails?', 'down'),
('2026-03-31 09:30:00+00', 'CI-CD', 'How do I configure deployment environments?', 'up'),
('2026-03-31 11:55:00+00', 'CI-CD', 'What is the staging deployment process?', 'up'),
('2026-04-01 08:10:00+00', 'CI-CD', 'How do I add a new environment variable to the pipeline?', 'up'),
('2026-04-01 14:20:00+00', 'CI-CD', 'What is the canary deployment strategy?', 'down'),
('2026-04-02 09:45:00+00', 'CI-CD', 'How do I monitor a deployment in progress?', 'up'),
('2026-04-03 10:30:00+00', 'CI-CD', 'What tests run in the CI pipeline?', 'up'),
('2026-04-03 15:15:00+00', 'CI-CD', 'How do I skip tests for a hotfix?', 'down'),

-- INFRA team (15 rows)
('2026-03-28 10:05:00+00', 'INFRA', 'How do I scale a Kubernetes deployment?', 'up'),
('2026-03-28 16:20:00+00', 'INFRA', 'What is the cluster autoscaler configuration?', 'up'),
('2026-03-29 09:15:00+00', 'INFRA', 'How do I check node resource usage?', 'up'),
('2026-03-29 12:40:00+00', 'INFRA', 'How do I debug a CrashLoopBackOff pod?', 'down'),
('2026-03-29 16:00:00+00', 'INFRA', 'What is the networking topology?', 'up'),
('2026-03-30 08:30:00+00', 'INFRA', 'How do I add a new namespace?', 'up'),
('2026-03-30 11:00:00+00', 'INFRA', 'What is the ingress controller we use?', 'up'),
('2026-03-30 14:30:00+00', 'INFRA', 'How do I configure resource limits?', 'down'),
('2026-03-31 10:00:00+00', 'INFRA', 'How do I set up a new service mesh?', 'down'),
('2026-03-31 13:20:00+00', 'INFRA', 'What monitoring stack is deployed?', 'up'),
('2026-04-01 09:00:00+00', 'INFRA', 'How do I update a Helm chart?', 'up'),
('2026-04-01 12:45:00+00', 'INFRA', 'What is the backup strategy for persistent volumes?', 'up'),
('2026-04-02 10:10:00+00', 'INFRA', 'How do I access the Kubernetes dashboard?', 'up'),
('2026-04-03 09:00:00+00', 'INFRA', 'What are the on-call escalation procedures?', 'down'),
('2026-04-03 14:00:00+00', 'INFRA', 'How do I configure HPA for a service?', 'up'),

-- ENG-ENV team (15 rows)
('2026-03-28 11:00:00+00', 'ENG-ENV', 'How do I set up my local dev environment?', 'up'),
('2026-03-28 15:10:00+00', 'ENG-ENV', 'What IDE plugins are recommended?', 'up'),
('2026-03-29 10:00:00+00', 'ENG-ENV', 'How do I connect to the dev database?', 'up'),
('2026-03-29 13:30:00+00', 'ENG-ENV', 'What version of Node.js should I use?', 'up'),
('2026-03-29 17:00:00+00', 'ENG-ENV', 'How do I run the test suite locally?', 'down'),
('2026-03-30 09:45:00+00', 'ENG-ENV', 'How do I set up pre-commit hooks?', 'up'),
('2026-03-30 12:15:00+00', 'ENG-ENV', 'What is the onboarding checklist?', 'up'),
('2026-03-30 15:45:00+00', 'ENG-ENV', 'How do I get VPN access?', 'up'),
('2026-03-31 08:00:00+00', 'ENG-ENV', 'What secrets manager do we use?', 'down'),
('2026-03-31 14:00:00+00', 'ENG-ENV', 'How do I access the internal docs site?', 'up'),
('2026-04-01 10:30:00+00', 'ENG-ENV', 'How do I configure my terminal for the toolchain?', 'up'),
('2026-04-01 15:00:00+00', 'ENG-ENV', 'What is the process for requesting new tooling?', 'up'),
('2026-04-02 11:20:00+00', 'ENG-ENV', 'How do I add a new environment to my local setup?', 'down'),
('2026-04-03 08:45:00+00', 'ENG-ENV', 'What are the coding standards?', 'up'),
('2026-04-03 12:30:00+00', 'ENG-ENV', 'How do I submit a request for new hardware?', 'up');
