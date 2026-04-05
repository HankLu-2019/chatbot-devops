import ChatUI from "@/components/ChatUI";

export const metadata = {
  title: "Search All Teams — Acme Engineering",
};

const CROSS_TEAM_QUESTIONS = [
  "Why is my deploy slow?",
  "How does a change go from PR to production?",
  "What should I check when something is broken in staging?",
  "Who handles VPN access versus Kubernetes access?",
];

export default function SearchPage() {
  return (
    <ChatUI
      title="Search All Teams"
      exampleQuestions={CROSS_TEAM_QUESTIONS}
    />
  );
}
