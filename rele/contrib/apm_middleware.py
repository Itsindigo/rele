import json

import elasticapm
from elasticapm import Client
from elasticapm.contrib.opentracing import Tracer
from opentracing import Format

from rele.middleware import BaseMiddleware

ELASTIC_APM_TRACE_PARENT = 'elastic-apm-traceparent'


class Carrier(dict):
    def get_trace_parent(self):
        return str(self.get(ELASTIC_APM_TRACE_PARENT), "utf-8")


class APMMiddleware(BaseMiddleware):
    _tracer = None
    _carrier = None

    def setup(self, config):
        apm_client = Client({'SERVICE_NAME': config.gc_project_id})
        self._tracer = Tracer(apm_client)
        self._carrier = Carrier()

    def pre_publish(self, topic, data, attrs):
        elasticapm.instrument()
        scope = self._tracer.start_active_span(topic, finish_on_close=False)
        self._tracer.inject(span_context=scope.span.context,
                            format=Format.TEXT_MAP,
                            carrier=self._carrier)
        trace_parent = {
            ELASTIC_APM_TRACE_PARENT: self._carrier.get_trace_parent()
        }

        return {**attrs, **trace_parent}

    def post_publish(self, topic):
        self._tracer.active_span.finish()

    def pre_process_message(self, subscription, message):
        elasticapm.instrument()
        trace_parent = {
            ELASTIC_APM_TRACE_PARENT: message.attributes.get(ELASTIC_APM_TRACE_PARENT)
        }
        parent_span_context = self._tracer.extract(
            Format.TEXT_MAP,
            trace_parent
        )
        data = json.loads(message.data.decode('utf-8'))
        span_context = self._tracer.start_active_span(
            str(subscription),
            child_of=parent_span_context,
            finish_on_close=False
        )
        if type(data) is dict:
            for key, value in data.items():
                span_context.span.set_tag(f'data-{key}', value)

        for key, value in message.attributes.items():
            span_context.span.set_tag(key, value)

    def post_process_message(self):
        self._tracer.active_span.finish()