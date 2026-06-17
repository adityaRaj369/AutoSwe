import { useState } from "react";
import { Link } from "react-router-dom";
import { useRuns } from "../api/client";
import { StatusBadge } from "../components/StatusBadge";
import type { RunStatus } from "../types";

const STATUSES: (RunStatus | "")[] = ["", "QUEUED", "RUNNING", "SOLVED", "FAILED", "TIMEOUT"];

export function RunsList() {
  const [status, setStatus] = useState<string>("");
  const [page, setPage] = useState(1);
  const { data, isLoading } = useRuns({ status: status || undefined, page });

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-slate-100">Runs</h1>
          <p className="mt-1 text-sm text-slate-500">
            Latest agent attempts, provider status, and PR results.
          </p>
        </div>
        <select
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
          className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm text-slate-300"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {s || "All statuses"}
            </option>
          ))}
        </select>
      </div>

      <div className="overflow-hidden rounded-xl border border-line bg-panel">
        <div className="overflow-x-auto">
        <table className="min-w-[760px] w-full text-sm">
          <thead className="border-b border-line text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-5 py-3">Issue</th>
              <th className="px-5 py-3">Status</th>
              <th className="px-5 py-3">Steps</th>
              <th className="px-5 py-3">Duration</th>
              <th className="px-5 py-3">PR</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {data?.items.map((r) => (
              <tr key={r.id} className="hover:bg-panel2">
                <td className="max-w-[360px] px-5 py-3">
                  <Link
                    to={`/runs/${r.id}`}
                    className="block truncate text-slate-200 hover:text-blue-300"
                    title={`#${r.issue_number} · ${r.issue_title}`}
                  >
                    #{r.issue_number} · {r.issue_title || "Untitled issue"}
                  </Link>
                  <div className="mt-1 truncate text-xs text-slate-600">{r.model || "No model recorded"}</div>
                </td>
                <td className="px-5 py-3">
                  <StatusBadge status={r.status} />
                </td>
                <td className="px-5 py-3 text-slate-400">{r.total_steps}</td>
                <td className="px-5 py-3 text-slate-400">
                  {r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "—"}
                </td>
                <td className="px-5 py-3 text-slate-400">
                  {r.pr_url ? (
                    <a href={r.pr_url} target="_blank" className="text-blue-300">
                      #{r.pr_number}
                    </a>
                  ) : (
                    "—"
                  )}
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={5} className="px-5 py-8 text-center text-slate-500">
                  No runs found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
        </div>
      </div>

      {data && data.total > data.page_size && (
        <div className="flex items-center justify-center gap-3 text-sm">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="text-slate-500">
            Page {data.page} of {Math.ceil(data.total / data.page_size)}
          </span>
          <button
            disabled={page >= Math.ceil(data.total / data.page_size)}
            onClick={() => setPage((p) => p + 1)}
            className="rounded-lg border border-line px-3 py-1.5 text-slate-300 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
