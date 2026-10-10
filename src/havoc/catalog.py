"""Fault catalog: the single source of truth for the synthetic world.

Each Fault describes (a) how it shows up in metrics, (b) what it writes to logs, and
(c) the runbook and past-postmortem text about it. The data generator turns this into files.

Effect kinds understood by the generator (see datagen.apply_effect):
  step_x     multiply the baseline by a factor from onset onward
  ramp_x     ramp from baseline to baseline*factor between onset and the end
  step_to    jump to an absolute level at onset
  ramp_to    ramp to an absolute level between onset and the end
  jitter_x   noisy multiple of baseline (erratic, high variance)
  saw_to     sawtooth up to an absolute level, dropping back (restart loop)
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Fault:
    id: str
    rb: str
    name: str
    alert_kind: str  # latency | errors | cpu | memory | disk
    effects: dict[str, tuple[str, float]]
    error_logs: tuple[str, ...]
    context_logs: tuple[str, ...]
    symptoms: tuple[str, ...]
    diagnosis: tuple[str, ...]
    remediation: tuple[str, ...]
    pm_root: str
    pm_fix: str


FAULTS: tuple[Fault, ...] = (
    Fault(
        id="db_conn_pool_exhausted",
        rb="RB-01",
        name="Database connection pool exhausted",
        alert_kind="latency",
        effects={
            "db_pool_pct": ("step_to", 100),
            "latency_p95_ms": ("step_x", 9),
            "error_rate_pct": ("step_x", 25),
        },
        error_logs=(
            "ERROR HikariPool-1 - Connection is not available, request timed out after {ms}ms",
            "ERROR Timeout waiting for connection from pool (active={n}, idle=0, waiting={n})",
            "WARN Pool saturation: all {n} connections in use",
            "ERROR Failed to acquire database connection for request",
        ),
        context_logs=("WARN Connection leak detection triggered, connection held for {ms}ms",),
        symptoms=(
            "Requests hang and then fail with connection acquisition timeouts",
            "DB pool utilisation is pinned near 100% while the database is not CPU-bound",
            "Latency and 5xx errors rise together",
        ),
        diagnosis=(
            "Check active versus max pool size and the number of waiting threads",
            "Look for connection leaks: connections not closed on error paths",
            "Check for long-running queries or locks holding connections",
        ),
        remediation=(
            "Restart or recycle the affected pods to release leaked connections",
            "Temporarily raise the max pool size if the database has headroom",
            "Fix the leak and add pool-saturation alerts",
        ),
        pm_root="A code path opened a transaction and did not release the connection on the "
        "error branch, so the pool filled up under normal traffic.",
        pm_fix="Restarted pods to free the pool, then shipped a fix that closes connections "
        "in a finally block.",
    ),
    Fault(
        id="jvm_memory_leak",
        rb="RB-02",
        name="Memory leak causing heap exhaustion",
        alert_kind="memory",
        effects={
            "mem_pct": ("ramp_to", 96),
            "latency_p95_ms": ("ramp_x", 3),
            "error_rate_pct": ("ramp_x", 8),
            "cpu_pct": ("ramp_x", 1.4),
        },
        error_logs=(
            "ERROR java.lang.OutOfMemoryError: Java heap space",
            "WARN Full GC pause {ms}ms, heap usage 97%",
            "WARN GC overhead: spending {n}% of time in garbage collection",
            "ERROR Request failed: unable to allocate buffer, insufficient memory",
        ),
        context_logs=("WARN Heap usage above 85% after full GC",),
        symptoms=(
            "Memory climbs steadily and never returns to baseline after garbage collection",
            "Latency creeps up as GC pauses lengthen",
            "Eventually out-of-memory errors or restarts appear",
        ),
        diagnosis=(
            "Compare heap usage after GC over several hours; a rising floor indicates a leak",
            "Take a heap dump and look for the largest retained objects",
            "Correlate the start of growth with recent deployments or new caches",
        ),
        remediation=(
            "Restart the service to recover immediately and buy time",
            "Roll back the release that introduced the growth",
            "Fix unbounded caches or listeners holding references and add a heap-growth alert",
        ),
        pm_root="An unbounded in-memory cache kept every response object alive, so heap usage "
        "rose steadily until garbage collection could not keep up.",
        pm_fix="Restarted pods on a schedule as a stopgap and replaced the cache with a "
        "size-bounded one with expiry.",
    ),
    Fault(
        id="traffic_spike_cpu_saturation",
        rb="RB-03",
        name="Traffic surge saturating CPU",
        alert_kind="cpu",
        effects={
            "rps": ("step_x", 3.2),
            "cpu_pct": ("step_to", 96),
            "latency_p95_ms": ("step_x", 5),
            "error_rate_pct": ("step_x", 6),
        },
        error_logs=(
            "WARN Autoscaler reached maximum replicas ({n}), cannot scale further",
            "ERROR Request queue depth {n} exceeds limit, shedding load",
            "WARN CPU throttling detected: container throttled in {n}% of periods",
            "ERROR Request rejected: server overloaded",
        ),
        context_logs=("INFO Autoscaler scaling up from {n} to {n} replicas",),
        symptoms=(
            "Request rate jumps well above normal while CPU approaches 100%",
            "Latency rises because requests queue for CPU",
            "The autoscaler is at its replica ceiling",
        ),
        diagnosis=(
            "Compare request rate to the weekly baseline and check for a campaign or retry storm",
            "Check autoscaler events and the replica ceiling",
            "Look at the top client IPs or tenants for abnormal volume",
        ),
        remediation=(
            "Raise the autoscaler maximum or add capacity",
            "Enable rate limiting or block abusive clients",
            "Shed non-critical traffic and plan capacity for the new peak",
        ),
        pm_root="A marketing campaign tripled inbound traffic and the autoscaler hit its "
        "maximum replica count, leaving the pods CPU-bound.",
        pm_fix="Raised the replica ceiling, added rate limits for anonymous clients, and set a "
        "capacity review for planned campaigns.",
    ),
    Fault(
        id="bad_deployment_regression",
        rb="RB-04",
        name="Bad deployment / code regression",
        alert_kind="errors",
        effects={
            "error_rate_pct": ("step_x", 30),
            "latency_p95_ms": ("step_x", 2.2),
            "cpu_pct": ("step_x", 1.25),
        },
        error_logs=(
            "ERROR NullPointerException at OrderMapper.toDto(OrderMapper.java:{n})",
            "ERROR Unhandled exception in request handler: unexpected null field",
            "WARN Deserialization failed for payload schema v{n}",
            "ERROR Request failed with 500 after new release",
        ),
        context_logs=("INFO Deployment of release v2.{n}.0 completed, rolling update finished",),
        symptoms=(
            "Error rate steps up sharply right after a release",
            "New exceptions appear that were not present before",
            "Infrastructure metrics such as CPU and memory stay roughly normal",
        ),
        diagnosis=(
            "Compare the onset time with the deployment timeline",
            "Group new error signatures by release version",
            "Check whether the failing endpoints were touched by the change",
        ),
        remediation=(
            "Roll back to the previous release",
            "Disable the new feature flag if one gates the change",
            "Add a regression test and canary checks before re-releasing",
        ),
        pm_root="A refactor introduced a null dereference on an optional field that production "
        "payloads frequently omit.",
        pm_fix="Rolled back to the previous version within minutes and re-released with a null "
        "check and a test for the missing-field case.",
    ),
    Fault(
        id="disk_full",
        rb="RB-05",
        name="Disk full",
        alert_kind="disk",
        effects={
            "disk_pct": ("ramp_to", 100),
            "error_rate_pct": ("step_x", 20),
            "latency_p95_ms": ("step_x", 1.6),
        },
        error_logs=(
            "ERROR No space left on device",
            "ERROR Failed to write WAL segment: disk quota exceeded",
            "WARN Log rotation failed: cannot create file",
            "ERROR IOException: write failed, filesystem is full",
        ),
        context_logs=("WARN Disk usage above 85% on /var/lib/data",),
        symptoms=(
            "Disk usage climbs toward 100% and writes begin to fail",
            "Errors mention no space left on device",
            "Services that write logs, temp files or WAL segments fail first",
        ),
        diagnosis=(
            "Find the largest directories with du and check log and temp folders",
            "Check whether log rotation or cleanup jobs stopped running",
            "Look for runaway debug logging or an unbounded temp file",
        ),
        remediation=(
            "Delete or archive old logs and temp files to free space immediately",
            "Expand the volume if the growth is legitimate",
            "Fix log rotation and add a disk-usage alert at 80%",
        ),
        pm_root="Debug logging was left enabled after an investigation and the log volume "
        "filled the disk because rotation was misconfigured.",
        pm_fix="Purged old logs, disabled debug logging, fixed the rotation policy and added "
        "an 80% disk alert.",
    ),
    Fault(
        id="dns_resolution_failure",
        rb="RB-06",
        name="DNS resolution failure",
        alert_kind="errors",
        effects={
            "error_rate_pct": ("step_x", 18),
            "latency_p95_ms": ("jitter_x", 6),
            "rps": ("step_x", 0.7),
        },
        error_logs=(
            "ERROR UnknownHostException: {dep}.internal",
            "ERROR Temporary failure in name resolution for {dep}.internal",
            "WARN DNS lookup timed out after {ms}ms",
            "ERROR Failed to connect to {dep}: no such host",
        ),
        context_logs=("WARN Resolver retry {n} for {dep}.internal",),
        symptoms=(
            "Calls to internal hostnames fail while the target services are healthy",
            "Errors mention unknown host or name resolution",
            "Failures are intermittent and latency is erratic",
        ),
        diagnosis=(
            "Run nslookup or dig from an affected pod against the cluster resolver",
            "Check CoreDNS pods for restarts, load and errors",
            "Check for recent changes to DNS records, search domains or network policies",
        ),
        remediation=(
            "Restart or scale CoreDNS",
            "Correct the broken record or search-domain setting",
            "Add node-local DNS caching and DNS error-rate alerts",
        ),
        pm_root="CoreDNS pods were overloaded after a node pool upgrade and began timing out "
        "lookups for internal hostnames.",
        pm_fix="Scaled CoreDNS replicas, enabled node-local DNS caching, and added alerts on "
        "resolver latency.",
    ),
    Fault(
        id="expired_tls_certificate",
        rb="RB-07",
        name="Expired TLS certificate",
        alert_kind="errors",
        effects={
            "error_rate_pct": ("step_to", 45),
            "latency_p95_ms": ("step_x", 0.5),
        },
        error_logs=(
            "ERROR SSLHandshakeException: PKIX path validation failed: certificate expired",
            "ERROR TLS handshake failed with {dep}: certificate has expired",
            "WARN Peer certificate not valid after date in the past",
            "ERROR Outbound call failed: javax.net.ssl.SSLException",
        ),
        context_logs=("WARN Certificate for {dep}.internal expires in 2 hours",),
        symptoms=(
            "A large share of calls fail instantly with TLS or certificate errors",
            "Latency drops because calls fail fast",
            "Started abruptly at a round timestamp with no deployment",
        ),
        diagnosis=(
            "Inspect the certificate with openssl s_client and read the not-after date",
            "Check whether the renewal job or cert-manager issuer is failing",
            "Verify the full chain and the trust store on the client",
        ),
        remediation=(
            "Issue and install a renewed certificate, then reload the affected services",
            "Fix the automation that should have renewed it",
            "Add expiry monitoring with alerts at 30, 14 and 7 days",
        ),
        pm_root="The certificate for an internal API expired because the renewal job had been "
        "failing silently for weeks.",
        pm_fix="Issued a new certificate manually, repaired the renewal job, and added alerts "
        "for upcoming expiry.",
    ),
    Fault(
        id="downstream_dependency_timeout",
        rb="RB-08",
        name="Downstream dependency timeout",
        alert_kind="latency",
        effects={
            "latency_p95_ms": ("step_x", 12),
            "error_rate_pct": ("step_x", 10),
            "rps": ("step_x", 0.85),
        },
        error_logs=(
            "ERROR Upstream {dep} timed out after {ms}ms",
            "WARN Circuit breaker OPEN for {dep}",
            "ERROR Fallback triggered: {dep} unavailable",
            "ERROR Read timeout calling {dep}",
        ),
        context_logs=("WARN {dep} response time p99 {ms}ms",),
        symptoms=(
            "Latency rises sharply while our own CPU and memory stay normal",
            "Logs show timeouts and open circuit breakers for one specific dependency",
            "Error rate rises moderately as requests exceed their timeout budgets",
        ),
        diagnosis=(
            "Check the dependency's own dashboards and status",
            "Compare outbound call latency per dependency",
            "Verify timeout and retry settings are not amplifying load",
        ),
        remediation=(
            "Engage the team that owns the dependency",
            "Enable degraded mode or fallback responses",
            "Tune timeouts, retries and circuit breaker thresholds",
        ),
        pm_root="The inventory dependency slowed down after its own database failover and our "
        "calls exceeded their timeout budget.",
        pm_fix="Opened the circuit breaker with cached fallbacks while the inventory team "
        "finished recovery, then shortened retry budgets.",
    ),
    Fault(
        id="slow_query_missing_index",
        rb="RB-09",
        name="Slow database queries (missing index)",
        alert_kind="latency",
        effects={
            "latency_p95_ms": ("ramp_x", 6),
            "db_pool_pct": ("ramp_to", 78),
            "error_rate_pct": ("step_x", 3),
        },
        error_logs=(
            "WARN Slow query took {ms}ms: SELECT * FROM orders WHERE customer_id = ?",
            "WARN Sequential scan on table orders ({n} rows)",
            "ERROR Statement timeout exceeded for query on orders",
            "WARN Query plan changed, estimated cost {n}",
        ),
        context_logs=("INFO Nightly data load finished, table orders grew by {n} rows",),
        symptoms=(
            "Latency grows gradually as the table grows or after a schema change",
            "Database load and pool use rise moderately without being fully exhausted",
            "The slow query log shows full scans of one table",
        ),
        diagnosis=(
            "Review the slow query log and run EXPLAIN on the top query",
            "Check whether an index was dropped or never created",
            "Check recent migrations or data growth on the table",
        ),
        remediation=(
            "Create the missing index concurrently",
            "Rewrite the query or add pagination",
            "Add slow-query alerts and review plans for new queries before release",
        ),
        pm_root="A migration dropped a composite index and the orders query fell back to "
        "sequential scans as the table grew.",
        pm_fix="Recreated the index concurrently, which restored latency, and added a "
        "migration check for dropped indexes.",
    ),
    Fault(
        id="thread_pool_exhaustion",
        rb="RB-10",
        name="Thread pool exhaustion",
        alert_kind="latency",
        effects={
            "latency_p95_ms": ("step_x", 10),
            "error_rate_pct": ("step_x", 12),
            "cpu_pct": ("step_x", 0.55),
            "rps": ("step_x", 0.8),
        },
        error_logs=(
            "ERROR RejectedExecutionException: worker pool exhausted",
            "WARN All {n} worker threads busy, queue full",
            "ERROR Request rejected: executor queue capacity reached",
            "WARN Thread dump shows {n} threads blocked on I/O",
        ),
        context_logs=("WARN Blocking call detected on request thread ({ms}ms)",),
        symptoms=(
            "Latency and errors rise while CPU stays low",
            "Logs show rejected tasks and busy worker threads",
            "Threads are blocked waiting on I/O rather than computing",
        ),
        diagnosis=(
            "Take thread dumps and see what the blocked threads are waiting on",
            "Check pool and queue sizes against concurrency",
            "Look for a slow downstream call or a lock held by many threads",
        ),
        remediation=(
            "Restart pods to clear the blocked threads",
            "Increase the pool or add timeouts to the blocking call",
            "Move blocking work off request threads and add bulkheads",
        ),
        pm_root="A synchronous call to a slow service blocked request threads until the worker "
        "pool was fully occupied while CPU stayed idle.",
        pm_fix="Added timeouts to the blocking call, isolated it in its own pool, and "
        "restarted pods to recover.",
    ),
    Fault(
        id="cache_outage_redis",
        rb="RB-11",
        name="Cache (Redis) outage",
        alert_kind="latency",
        effects={
            "latency_p95_ms": ("step_x", 5),
            "db_pool_pct": ("step_to", 85),
            "error_rate_pct": ("step_x", 5),
            "cpu_pct": ("step_x", 1.2),
        },
        error_logs=(
            "ERROR Redis connection refused: {host}:6379",
            "WARN Cache miss ratio 100%, falling back to database",
            "ERROR JedisConnectionException: could not get a resource from the pool",
            "WARN Cache stampede: {n} concurrent loads for the same key",
        ),
        context_logs=("WARN Redis latency spike {ms}ms",),
        symptoms=(
            "Cache hit ratio collapses and database load rises sharply",
            "Latency increases because every request goes to the database",
            "Logs show Redis connection errors",
        ),
        diagnosis=(
            "Check Redis pod or instance health, memory and evictions",
            "Verify network reachability and credentials",
            "Check for a failover in progress or an eviction storm after hitting maxmemory",
        ),
        remediation=(
            "Restore or fail over Redis",
            "Protect the database with request coalescing and rate limits while the cache is cold",
            "Pre-warm hot keys after recovery",
        ),
        pm_root="The Redis primary ran out of memory and crashed, so all reads fell through to "
        "the database and overloaded its connection pool.",
        pm_fix="Failed over to the replica, throttled expensive endpoints during warm-up, and "
        "raised the memory limit.",
    ),
    Fault(
        id="bad_config_change",
        rb="RB-12",
        name="Bad configuration change",
        alert_kind="errors",
        effects={
            "error_rate_pct": ("step_x", 22),
            "latency_p95_ms": ("step_x", 0.4),
        },
        error_logs=(
            "ERROR Request timed out after 50ms (configured timeout_ms=50)",
            "WARN Config reload applied: timeout_ms changed from 5000 to 50",
            "ERROR Invalid configuration value for rate_limit.max=0, rejecting requests",
            "ERROR Feature flag payments.v2 enabled without required settings",
        ),
        context_logs=("INFO Configuration reloaded from config service, version {n}",),
        symptoms=(
            "Errors begin at the exact time of a configuration push",
            "Failures are fast, so latency does not rise and may even fall",
            "No code deployment happened, but a config version changed",
        ),
        diagnosis=(
            "Check the config change audit log around the onset",
            "Diff the active config against the previous version",
            "Verify values and units such as timeouts, limits and flags",
        ),
        remediation=(
            "Revert the configuration to the last known good version",
            "Add validation and staged rollout for configuration changes",
            "Alert on config version changes correlated with error spikes",
        ),
        pm_root="A configuration push set a request timeout to 50 milliseconds instead of 5 "
        "seconds, so most calls timed out immediately.",
        pm_fix="Reverted the config version and added schema validation with minimum bounds "
        "for timeout values.",
    ),
    Fault(
        id="network_packet_loss",
        rb="RB-13",
        name="Network partition / packet loss",
        alert_kind="latency",
        effects={
            "latency_p95_ms": ("jitter_x", 8),
            "error_rate_pct": ("step_x", 8),
            "rps": ("step_x", 0.6),
        },
        error_logs=(
            "ERROR Connection reset by peer",
            "WARN TCP retransmits elevated: {n} per second",
            "ERROR i/o timeout while reading from {dep}",
            "WARN Packet loss {n}% on path to {host}",
        ),
        context_logs=("WARN Connection to {dep} re-established after {n} retries",),
        symptoms=(
            "Latency is erratic with large swings rather than a steady rise",
            "Throughput drops and errors rise across several dependencies at once",
            "Logs show connection resets and retransmits",
        ),
        diagnosis=(
            "Run ping and mtr between affected nodes to measure loss",
            "Check cloud provider network events and node health",
            "Check whether the issue is limited to one availability zone or node pool",
        ),
        remediation=(
            "Drain traffic away from the affected zone or node",
            "Cordon and replace the faulty nodes",
            "Engage the network or cloud provider and add loss and retransmit alerts",
        ),
        pm_root="A faulty switch in one availability zone caused packet loss between nodes, "
        "which showed up as resets and erratic latency.",
        pm_fix="Shifted traffic out of the zone and replaced the affected nodes while the "
        "provider repaired the switch.",
    ),
    Fault(
        id="vendor_rate_limit_429",
        rb="RB-14",
        name="Third-party API rate limiting (429)",
        alert_kind="errors",
        effects={
            "error_rate_pct": ("step_x", 15),
            "rps": ("step_x", 1.5),
        },
        error_logs=(
            "ERROR 429 Too Many Requests from api.{dep}.com",
            "WARN Retry-After header received: {n} seconds",
            "ERROR Quota exceeded for API key ending {n}",
            "WARN Backing off outbound calls to api.{dep}.com",
        ),
        context_logs=("WARN Outbound call volume to api.{dep}.com {n}% above usual",),
        symptoms=(
            "Errors rise while latency stays normal because rejections are immediate",
            "Request volume to a third-party API grew",
            "Logs show 429 responses and Retry-After headers",
        ),
        diagnosis=(
            "Check outbound call volume against the vendor's quota",
            "Look for retry loops or a new feature making extra calls",
            "Confirm which API key or plan limit was hit",
        ),
        remediation=(
            "Throttle and batch outbound calls and honour Retry-After",
            "Request a higher quota from the vendor",
            "Cache vendor responses and add quota-consumption alerts",
        ),
        pm_root="A retry loop without backoff multiplied calls to a payment vendor until the "
        "account quota was exceeded.",
        pm_fix="Added exponential backoff with jitter, requested a quota increase, and cached "
        "idempotent lookups.",
    ),
    Fault(
        id="container_oom_kill_loop",
        rb="RB-15",
        name="Container OOMKilled / restart loop",
        alert_kind="memory",
        effects={
            "mem_pct": ("saw_to", 99),
            "error_rate_pct": ("step_x", 9),
            "rps": ("step_x", 0.6),
            "latency_p95_ms": ("jitter_x", 4),
        },
        error_logs=(
            "ERROR Container killed: OOMKilled (exit code 137)",
            "WARN Back-off restarting failed container {svc}",
            "WARN Pod status CrashLoopBackOff, restart count {n}",
            "ERROR Readiness probe failed: connection refused",
        ),
        context_logs=("WARN Memory usage {n}% of container limit",),
        symptoms=(
            "Memory repeatedly climbs to the container limit then drops when the container restarts",
            "Capacity and throughput dip during each restart",
            "Pods show OOMKilled and CrashLoopBackOff",
        ),
        diagnosis=(
            "Inspect pod events and last state for OOMKilled and exit code 137",
            "Compare the memory limit with the working set during peak",
            "Check recent changes to limits, heap settings or batch sizes",
        ),
        remediation=(
            "Raise the container memory limit to stop the loop",
            "Align JVM or runtime heap settings with the limit",
            "Reduce batch sizes and add working-set alerts",
        ),
        pm_root="The container memory limit was lowered during a cost review, so the working "
        "set exceeded it at peak and the kernel killed the process repeatedly.",
        pm_fix="Restored the previous limit, aligned heap settings to 75% of the limit, and "
        "added restart-count alerts.",
    ),
)

FAULT_BY_ID: dict[str, Fault] = {f.id: f for f in FAULTS}
FAULT_IDS: tuple[str, ...] = tuple(f.id for f in FAULTS)

GENERIC_ERRORS: tuple[str, ...] = (
    "ERROR Request failed with status 500",
    "WARN Health check slow: {ms}ms",
    "ERROR Unexpected error handling request",
)

# Benign noise that appears before incidents, so log search is not trivially clean.
DECOY_LOGS: tuple[str, ...] = (
    "WARN Certificate for api.internal expires in 24 days",
    "WARN Deprecated endpoint /v1/orders/legacy called",
    "WARN Minor GC pause 120ms",
    "WARN Retry succeeded on attempt 2 for {dep}",
    "WARN Slow request 640ms for GET /api/v1/items",
)

SERVICES: tuple[str, ...] = (
    "checkout-service",
    "payment-gateway",
    "inventory-service",
    "auth-service",
    "search-api",
    "notification-worker",
    "user-profile-service",
    "order-service",
)

DEPENDENCIES: tuple[str, ...] = (
    "inventory-service",
    "payment-gateway",
    "auth-service",
    "pricing-service",
    "stripe",
    "twilio",
)


def taxonomy_text() -> str:
    """Root-cause label list shown to the LLM (names only, no runbook content)."""
    return "\n".join(f"- {f.id}: {f.name}" for f in FAULTS)
