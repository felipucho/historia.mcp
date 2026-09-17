export default function Reader({ docs, error }) {
  return (
    <main className="thin-scrollbar flex-1 overflow-y-auto px-6 py-12 md:px-12 md:py-20">
      <div className="mx-auto max-w-3xl">
        <header className="mb-14 border-b border-white/10 pb-10">
          <h2 className="font-display text-4xl font-black tracking-tight text-white md:text-5xl">
            Debate sobre la fundación de Las Varillas
          </h2>
          <p className="mt-4 text-xs font-medium uppercase tracking-[0.4em] text-slate-500">Investigación histórica</p>
        </header>

        {error && (
          <p role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-red-200">
            No se pudo cargar el archivo histórico: {error}
          </p>
        )}
        {!error && docs.length === 0 && <p className="text-slate-500">Cargando documentos…</p>}

        <div className="space-y-16">
          {docs.map((doc) => (
            // id = ancla del índice. tabIndex permite mover el foco al documento tras el scroll.
            // min-h en el último: sin espacio debajo, el scroll no puede alinearlo arriba.
            <article key={doc.id} id={doc.id} tabIndex={-1} className="scroll-mt-8 outline-none last:min-h-[calc(100dvh-7rem)]">
              <p className="mb-2 text-xs font-bold uppercase tracking-widest text-blue-400">
                {doc.metadata.fecha_clave} · {doc.metadata.criterio_historiografico}
              </p>
              <h3 className="font-display mb-4 text-2xl font-bold text-slate-100">{doc.titulo}</h3>
              <p className="text-lg font-light leading-[1.8] text-slate-300">{doc.contenido}</p>
              <footer className="mt-5 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                <span className="mr-2">Fuente: {doc.metadata.fuente}</span>
                {doc.tags.map((tag) => (
                  <span key={tag} className="rounded-full border border-white/10 px-2 py-0.5">
                    {tag}
                  </span>
                ))}
              </footer>
            </article>
          ))}
        </div>
      </div>
    </main>
  )
}
