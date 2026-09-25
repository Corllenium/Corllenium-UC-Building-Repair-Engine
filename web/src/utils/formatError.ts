export function formatErrorMessage(err: any): string {
  if (err && err.status === 409) {
    const sec = err.retryAfter ?? 5
    return `Export folder is being rebuilt, try again in ${sec} s`
  }
  return (err && err.message) || 'Operation failed'
}
