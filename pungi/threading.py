from kobo.threads import WorkerThread

from .otel import tracing


class TelemetryWorkerThread(WorkerThread):
    """
    Subclass of WorkerThread that captures current context when the thread is
    created, and restores the context in the new thread.

    A regular WorkerThread would start from an empty context, leading to any
    spans created in the thread disconnected from the overall trace.
    """

    def __init__(self, *args, **kwargs):
        self.traceparent = tracing.get_traceparent()
        super(TelemetryWorkerThread, self).__init__(*args, **kwargs)

    def run(self, *args, **kwargs):
        tracing.set_context(self.traceparent)
        super(TelemetryWorkerThread, self).run(*args, **kwargs)
