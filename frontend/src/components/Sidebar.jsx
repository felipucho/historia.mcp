import { History } from 'lucide-react'

export default function Sidebar({ docs, open, onNavigate }) {
  return (
    <aside
      aria-label="Índice histórico"
      inert={!open}
      className={`${open ? 'w-72' : 'w-0'} shrink-0 overflow-hidden border-r border-white/5 bg-slate-900/80 backdrop-blur-xl transition-[width] duration-300 max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:z-30`}
    >
      <div className="flex h-full w-72 flex-col p-6">
        <div className="mb-8 flex items-center gap-3">
          <div className="rounded-xl bg-linear-to-br from-blue-500 to-indigo-600 p-2.5 shadow-lg shadow-blue-500/20">
            <History className="size-5 text-white" aria-hidden />
          </div>
          <h2 className="text-lg font-bold tracking-tight">Índice histórico</h2>
        </div>

        <nav className="thin-scrollbar -mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
          {docs.map((doc) => (
            <button
              key={doc.id}
              type="button"
              onClick={() => onNavigate(doc.id)}
              className="glass group flex w-full gap-3 rounded-xl p-4 text-left transition hover:bg-slate-700/60 focus-visible:outline-2 focus-visible:outline-blue-400"
            >
              <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-blue-500 transition group-hover:scale-150" aria-hidden />
              <span>
                <span className="block text-[10px] font-black uppercase tracking-widest text-blue-400">
                  {doc.metadata.fecha_clave}
                </span>
                <span className="block text-sm font-semibold text-slate-300 group-hover:text-white">{doc.titulo}</span>
              </span>
            </button>
          ))}
        </nav>
      </div>
    </aside>
  )
}
