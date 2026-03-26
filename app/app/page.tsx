import ChatUI from "@/components/ChatUI";

export default function Home() {
  return (
    <main className="flex flex-col h-screen">
      <header className="flex-shrink-0 bg-white border-b border-gray-200 px-6 py-4 shadow-sm">
        <div className="max-w-4xl mx-auto flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-indigo-600 flex items-center justify-center text-white font-bold text-sm select-none">
            A
          </div>
          <div>
            <h1 className="text-lg font-semibold text-gray-900">
              Acme Engineering Assistant
            </h1>
            <p className="text-xs text-gray-500">
              Ask questions about internal docs, runbooks, and Jira tickets
            </p>
          </div>
        </div>
      </header>

      <div className="flex-1 overflow-hidden max-w-4xl w-full mx-auto">
        <ChatUI />
      </div>
    </main>
  );
}
