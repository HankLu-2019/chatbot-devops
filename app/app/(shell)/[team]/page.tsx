import { notFound } from "next/navigation";
import { TEAMS, getTeamBySlug } from "@/lib/teams";
import ChatUI from "@/components/ChatUI";

export function generateStaticParams() {
  return TEAMS.map((t) => ({ team: t.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ team: string }> }) {
  const { team: slug } = await params;
  const team = getTeamBySlug(slug);
  if (!team) return { title: "Not Found" };
  return { title: `${team.label} Assistant — Acme Engineering` };
}

export default async function TeamPage({ params }: { params: Promise<{ team: string }> }) {
  const { team: slug } = await params;
  const team = getTeamBySlug(slug);

  if (!team) {
    notFound();
  }

  return (
    <ChatUI
      space={team.space}
      title={`${team.label} Assistant`}
      exampleQuestions={team.exampleQuestions}
    />
  );
}
