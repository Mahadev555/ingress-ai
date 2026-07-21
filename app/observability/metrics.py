from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("ingress_ai_requests_total", "Total requests")
REQUEST_LATENCY = Histogram("ingress_ai_request_latency_seconds", "Request latency")
