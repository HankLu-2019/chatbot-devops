import ChatUI from "@/components/ChatUI";

export default function Home() {
  return (
    <main style={{ height: "100vh", display: "flex", flexDirection: "column" }}>
      <div style={{ flex: 1, overflow: "hidden", maxWidth: "860px", width: "100%", margin: "0 auto" }}>
        <ChatUI />
      </div>
    </main>
  );
}
