"use client";

import { useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/page-header";
import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/store/auth";

interface TerminalLine {
  kind: "input" | "output" | "error";
  text: string;
}

export default function TerminalPage() {
  const user = useAuth((s) => s.user);
  const [lines, setLines] = useState<TerminalLine[]>([
    { kind: "output", text: "Ubuntu Server Manager Terminal" },
    { kind: "output", text: "Type 'help' for available commands." },
  ]);
  const [command, setCommand] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  const exec = useMutation({
    mutationFn: (cmd: string) =>
      api<{ output: string }>("/terminal/exec", {
        method: "POST",
        body: JSON.stringify({ command: cmd }),
      }),
    onSuccess: (res) => {
      setLines((prev) => [...prev, { kind: "output", text: res.output }]);
      scrollBottom();
    },
    onError: (err) => {
      setLines((prev) => [
        ...prev,
        {
          kind: "error",
          text:
            err instanceof ApiError ? err.message : "Command execution failed",
        },
      ]);
      scrollBottom();
    },
  });

  function scrollBottom() {
    requestAnimationFrame(() => {
      if (bodyRef.current) bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    });
  }

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key !== "Enter") return;
    const cmd = command.trim();
    setCommand("");
    if (!cmd) return;

    if (cmd === "clear") {
      setLines([]);
      return;
    }

    setLines((prev) => [
      ...prev,
      { kind: "input", text: `${user?.username ?? "admin"}@server:~$ ${cmd}` },
    ]);
    scrollBottom();
    exec.mutate(cmd);
  }

  return (
    <>
      <PageHeader
        title="Web Terminal"
        subtitle="Restricted command interface — arbitrary shell is not allowed"
      />

      <div className="overflow-hidden rounded-xl border border-[#202a35] bg-[#060a0d] shadow-[0_15px_40px_rgba(0,0,0,.25)]">
        <div className="flex h-[35px] items-center gap-2 border-b border-[#202a35] bg-[#11171d] px-3">
          <span className="h-2 w-2 rounded-full bg-[#ff5f56]" />
          <span className="h-2 w-2 rounded-full bg-[#ffbd2e]" />
          <span className="h-2 w-2 rounded-full bg-[#27c93f]" />
        </div>

        <div
          ref={bodyRef}
          className="min-h-[390px] max-h-[60vh] overflow-y-auto p-[18px] font-mono text-[11px] leading-relaxed"
          onClick={() => inputRef.current?.focus()}
        >
          {lines.map((line, i) => (
            <div
              key={i}
              className={
                line.kind === "input"
                  ? "text-[#6ee28a]"
                  : line.kind === "error"
                    ? "text-[#ff8f8f] whitespace-pre-wrap"
                    : "text-[#aab6c3] whitespace-pre-wrap"
              }
            >
              {line.text}
            </div>
          ))}

          <div className="mt-1 flex items-center gap-2">
            <span className="shrink-0 text-[#6ee28a]">
              {user?.username ?? "admin"}@server:~$
            </span>
            <input
              ref={inputRef}
              className="w-full border-0 bg-transparent font-mono text-[11px] text-white outline-none"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              onKeyDown={handleKey}
              autoFocus
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </div>
      </div>

      <p className="mt-3 text-[10px] text-muted2">
        Allowed commands: uptime · free -h · df -h · ping &lt;host&gt; [n] (via
        LAN) · docker ps · systemctl status · ps · help. The backend never
        executes arbitrary shell input (see Rencana.md security notes).
      </p>
    </>
  );
}
