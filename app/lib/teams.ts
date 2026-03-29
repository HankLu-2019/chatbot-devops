export interface Team {
  slug: string;
  label: string;
  description: string;
  space: string;
  exampleQuestions: string[];
}

export const TEAMS: Team[] = [
  {
    slug: "cicd",
    label: "CI/CD",
    description: "Pipelines, builds, deployments, and release processes",
    space: "CI-CD",
    exampleQuestions: [
      "How do I trigger a manual deployment?",
      "Why is my pipeline failing at the build step?",
      "How do I set up a new service in CI?",
      "How do I rollback a bad deployment?",
      "How do I add environment variables to a pipeline?",
    ],
  },
  {
    slug: "infra",
    label: "Infrastructure",
    description: "Kubernetes, networking, cloud resources, and monitoring",
    space: "INFRA",
    exampleQuestions: [
      "My pod is OOMKilled, what should I do?",
      "How do I scale a deployment?",
      "How do I check logs for a specific pod?",
      "How do I set up a new namespace?",
      "Why are my pods not starting?",
    ],
  },
  {
    slug: "eng-env",
    label: "Eng Environment",
    description: "Local dev setup, tooling, onboarding, and access",
    space: "ENG-ENV",
    exampleQuestions: [
      "How do I set up my local development environment?",
      "How do I get access to the staging cluster?",
      "Why am I getting 401 errors after token rotation?",
      "How do I connect to the VPN?",
      "Where do I find the internal API keys?",
    ],
  },
];

export function getTeamBySlug(slug: string): Team | undefined {
  return TEAMS.find((t) => t.slug === slug);
}
