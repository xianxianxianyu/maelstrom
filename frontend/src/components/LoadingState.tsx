interface Props {
  onCancel?: () => void
}

export function LoadingState({ onCancel }: Props) {
  return (
    <div className="mt-12 text-center">
      <div className="inline-block animate-spin rounded-full h-8 w-8 border-2 border-indigo-500 border-t-transparent" />
      <p className="mt-4 text-gray-500 font-light">
        正在处理文档...
      </p>
      {onCancel && (
        <button
          onClick={onCancel}
          className="mt-4 px-4 py-1.5 text-xs font-medium text-red-600 bg-red-50 border border-red-200 rounded-lg hover:bg-red-100 transition-colors"
        >
          停止任务
        </button>
      )}
    </div>
  )
}
