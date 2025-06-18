import itertools
import os
from contextlib import contextmanager

"""
This module contains two classes with the same interface. An instance of one of
them is available as `tracing`. Which class is instantiated is selected
depending on whether environment variables configuring OTel are configured.
"""


class DummyTracing:
    """A dummy tracing module that doesn't actually do anything."""

    def setup(self):
        pass

    @contextmanager
    def span(self, *args, **kwargs):
        yield

    def set_attribute(self, name, value):
        pass

    def force_flush(self):
        pass

    def instrument_xmlrpc_proxy(self, proxy):
        return proxy

    def get_traceparent(self):
        return None

    def set_context(self, traceparent):
        pass

    def record_exception(self, exc, set_error_status=True):
        pass


class OtelTracing:
    """This class implements the actual integration with opentelemetry."""

    def setup(self):
        """Configure opentelemetry tracing based on environment variables. This
        setup is optional as it may not be desirable when pungi is used as a
        library.
        """
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import (
            BatchSpanProcessor,
            ConsoleSpanExporter,
        )
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )

        otel_endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"]
        provider = TracerProvider(
            resource=Resource(attributes={"service.name": "pungi"})
        )
        if "console" == otel_endpoint:
            # This is for debugging the tracing locally.
            self.processor = BatchSpanProcessor(ConsoleSpanExporter())
        else:
            self.processor = BatchSpanProcessor(OTLPSpanExporter())
        provider.add_span_processor(self.processor)
        trace.set_tracer_provider(provider)

        traceparent = os.environ.get("TRACEPARENT")
        if traceparent:
            self.set_context(traceparent)

        try:
            from opentelemetry.instrumentation.requests import RequestsInstrumentor

            RequestsInstrumentor().instrument()
        except ImportError:
            pass

    @property
    def tracer(self):
        from opentelemetry import trace

        return trace.get_tracer(__name__)

    @contextmanager
    def span(self, name, **attributes):
        """Create a new span as a child of the current one. Attributes can be
        passed via kwargs."""
        with self.tracer.start_as_current_span(name, attributes=attributes) as span:
            yield span

    def get_traceparent(self):
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        carrier = {}
        TraceContextTextMapPropagator().inject(carrier)
        return carrier["traceparent"]

    def set_attribute(self, name, value):
        """Set an attribute on the current span."""
        from opentelemetry import trace

        span = trace.get_current_span()
        span.set_attribute(name, value)

    def force_flush(self):
        """Ensure all spans and traces are sent out. Call this before the
        process exits."""
        self.processor.force_flush()

    def instrument_xmlrpc_proxy(self, proxy):
        return InstrumentedClientSession(proxy)

    def set_context(self, traceparent):
        """Configure current context to match the given traceparent."""
        from opentelemetry import context
        from opentelemetry.trace.propagation.tracecontext import (
            TraceContextTextMapPropagator,
        )

        ctx = TraceContextTextMapPropagator().extract(
            carrier={"traceparent": traceparent}
        )
        context.attach(ctx)

    def record_exception(self, exc, set_error_status=True):
        """Records an exception for the current span and optionally marks the
        span as failed."""
        from opentelemetry import trace

        span = trace.get_current_span()
        span.record_exception(exc)

        if set_error_status:
            span.set_status(trace.status.StatusCode.ERROR)


class InstrumentedClientSession:
    """Wrapper around koji.ClientSession that creates spans for each API call.
    RequestsInstrumentor can create spans at the HTTP requests level, but since
    those all go the same XML-RPC endpoint, they are not very informative.

    Multicall is not handled very well here. The spans will only have a
    `multicall` boolean attribute, but they don't carry any additional data
    that could group them.

    Koji ClientSession supports three ways of making multicalls, but Pungi only
    uses one, and that one is supported here.

    Supported:

        c.multicall = True
        c.getBuild(1)
        c.getBuild(2)
        results = c.multiCall()

    Not supported:

        with c.multicall() as m:
            r1 = m.getBuild(1)
            r2 = m.getBuild(2)

    Also not supported:

        m = c.multicall()
        r1 = m.getBuild(1)
        r2 = m.getBuild(2)
        m.call_all()

    """

    def __init__(self, session):
        self.session = session

    def _name(self, name):
        """Helper for generating span names."""
        return "%s.%s" % (self.session.__class__.__name__, name)

    @property
    def system(self):
        """This is only ever used to get list of available API calls. It is
        rather awkward though. Ideally we wouldn't really trace this at all,
        but there's the underlying POST request to the hub, which is quite
        confusing in the trace if there is no additional context."""
        return self.session.system

    @property
    def multicall(self):
        return self.session.multicall

    @multicall.setter
    def multicall(self, value):
        self.session.multicall = value

    def __getattr__(self, name):
        return self._instrument_method(name, getattr(self.session, name))

    def _instrument_method(self, name, callable):
        def wrapper(*args, **kwargs):
            with tracing.span(self._name(name)) as span:
                span.set_attribute("arguments", _format_args(args, kwargs))
                if self.session.multicall:
                    tracing.set_attribute("multicall", True)
                return callable(*args, **kwargs)

        return wrapper


def _format_args(args, kwargs):
    """Turn args+kwargs into a single string. OTel could choke on more
    complicated data."""
    return ", ".join(
        itertools.chain(
            (repr(arg) for arg in args),
            (f"{key}={value!r}" for key, value in kwargs.items()),
        )
    )


if "OTEL_EXPORTER_OTLP_ENDPOINT" in os.environ:
    tracing = OtelTracing()
else:
    tracing = DummyTracing()
