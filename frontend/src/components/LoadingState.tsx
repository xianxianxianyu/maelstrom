export function LoadingState() {
  return (
    <div className="mt-12 text-center">
      <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-blue-600 border-t-transparent" />
      <p className="mt-4 text-slate-600 font-light">
        Processing document...
      </p>
    </div>
  )
}
