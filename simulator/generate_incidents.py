import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 24 Microservices, Infrastructure, Database, and Network Failure Scenarios (checkout-api purged)
INCIDENTS = [
    # 1. Microservices & Application Code
    {"service": "inventory-service", "version": "v1.4.0", "type": "Memory Leak", "error": "java.lang.OutOfMemoryError: Java heap space. Container restarted by OOMKiller", "impact": "Pod restart loop count: 12", "target_version": "v1.3.9"},
    {"service": "payment-service", "version": "v2.1.0", "type": "Connection Pool Exhaustion", "error": "SQLException: Unable to acquire JDBC Connection - pool size (100) exceeded", "impact": "Latency spike to 12000ms", "target_version": "v2.0.9"},
    {"service": "auth-service", "version": "v3.0.2", "type": "Expired JWT Secret", "error": "SignatureVerificationException: The Token's Signature is invalid / Key Rotation Mismatch", "impact": "Global authentication failure (100% 401 response rate)", "target_version": "v3.0.1"},
    {"service": "notification-service", "version": "v1.1.5", "type": "Deadlock", "error": "Thread Deadlock detected on pool-worker-8 waiting for lock on MailerQueue", "impact": "Background job queue backed up (>45,000 pending items)", "target_version": "v1.1.4"},
    {"service": "search-indexer", "version": "v2.5.0", "type": "High Garbage Collection Pause", "error": "GC Overhead Limit Exceeded: Stop-The-World pause > 15s", "impact": "Search queries failing with 503 Service Unavailable", "target_version": "v2.4.8"},
    {"service": "recommendation-engine", "version": "v4.0.1", "type": "Model Weights Deserialization Failure", "error": "ValueError: Tensor shape mismatch during PyTorch model download from S3", "impact": "Fallback to static recommendations, latency +800ms", "target_version": "v4.0.0"},
    {"service": "user-profile-service", "version": "v1.8.0", "type": "Infinite Loop Regression", "error": "CPU Utilization 100% on worker threads during avatar image normalization", "impact": "Node autoscaler thrashing", "target_version": "v1.7.9"},
    
    # 2. Database & Data Stores
    {"service": "postgres-primary", "version": "v15.2", "type": "Disk Space Exhaustion", "error": "PANIC: could not write to file pg_wal/xlog: No space left on device (100% utilized)", "impact": "Database switched to read-only transaction state", "target_version": "v15.1-failover"},
    {"service": "redis-cache-cluster", "version": "v7.0", "type": "OOM MaxMemory Eviction Policy Failure", "error": "OOM command not allowed when used memory > 'maxmemory' (noeviction active)", "impact": "Cache write drops across all dynamic routes", "target_version": "v6.2-stable"},
    {"service": "dynamodb-orders-table", "version": "v1.0", "type": "Provisioned Throughput Exceeded", "error": "ProvisionedThroughputExceededException: Request rate is higher than provisioned write capacity", "impact": "Order placement throttled for 15% of active users", "target_version": "v1.0-autoscale"},
    {"service": "elasticsearch-logs", "version": "v8.6", "type": "Unassigned Shards / Cluster Red State", "error": "ClusterHealthResult: RED - 14 primary shards unassigned due to disk watermark", "impact": "Search index read/write operations blocked", "target_version": "v8.5-rebalance"},
    {"service": "mongo-analytics", "version": "v5.9", "type": "Unindexed Field Scan Lock", "error": "Command failed with error 96: Operation Exceeded Time Limit (Executor error: Query plan scan > 1M docs)", "impact": "Read operations timed out on session aggregates", "target_version": "v5.8-indexes"},

    # 3. Cloud Infrastructure, Network & Mesh
    {"service": "ingress-nginx-controller", "version": "v1.8.0", "type": "SSL Certificate Expiry", "error": "SSL_ERROR_EXPIRED_CERTIFICATE: x509: certificate has expired or is not yet valid", "impact": "Browser security warnings blocking 100% of HTTPS traffic", "target_version": "v1.7.9-certfix"},
    {"service": "istio-service-mesh", "version": "v1.17", "type": "mTLS Handshake Timeout", "error": "Envoy internal error: downstream connection termination / mTLS certificate validation failure", "impact": "Inter-service pod communications dropped", "target_version": "v1.16-permissive"},
    {"service": "api-gateway", "version": "v2.4", "type": "Rate Limiter Misconfiguration", "error": "HTTP 429 Too Many Requests: Rate limit set to 10 req/min instead of 10000 req/min", "impact": "All external API consumers throttled", "target_version": "v2.3"},
    {"service": "aws-s3-asset-bucket", "version": "v1.0", "type": "IAM Access Denied Policy Drift", "error": "AccessDenied: User is not authorized to perform: s3:GetObject on resource", "impact": "Frontend static assets (CSS/JS) returning 403 Forbidden", "target_version": "v1.0-policy-restore"},
    {"service": "sqs-order-queue", "version": "v1.0", "type": "DLQ Redrive Loop", "error": "KMS Key Access Denied: Failed to decrypt SQS message payload", "impact": "120,000 messages stuck in Dead-Letter Queue", "target_version": "v1.0-kms-fix"},

    # 4. Storage, Network & Edge
    {"service": "dns-route53-resolver", "version": "v1.0", "type": "Internal DNS Resolution Failure", "error": "getaddrinfo ENOTFOUND internal.services.local", "impact": "Services unable to locate internal endpoints", "target_version": "v1.0-dns-flush"},
    {"service": "kafka-event-bus", "version": "v3.4", "type": "Broker Disk Full / Controller Failover", "error": "KafkaStorageException: Disk error on broker 3 / Partition offline", "impact": "Event streaming consumers lag behind by > 2 hours", "target_version": "v3.3-rebalance"},
    {"service": "vault-secrets-manager", "version": "v1.13", "type": "Sealed Vault Instance", "error": "VaultIsSealedException: Vault is sealed. Requests cannot be processed", "impact": "Dynamic backend database credential retrieval blocked", "target_version": "v1.12-unseal"},
    {"service": "prometheus-monitoring", "version": "v2.43", "type": "TSDB Corruption", "error": "TSDB opening failed: compaction failed: segment block corrupted", "impact": "Monitoring dashboards blank, alerting down", "target_version": "v2.42-clean-db"},
    {"service": "rabbitmq-broker", "version": "v3.11", "type": "Memory Alarm Triggered", "error": "rabbitmq_memory_high_watermark reached: blocking connections", "impact": "Publishers blocked from pushing messages", "target_version": "v3.10-flush"},
    {"service": "cdn-cloudfront", "version": "v1.0", "type": "Origin Host Header Mismatch", "error": "HTTP 502 Bad Gateway: Origin returned invalid SSL SNI host header", "impact": "Global static assets failing edge distribution", "target_version": "v1.0-origin-fix"},
    {"service": "worker-celery-async", "version": "v5.2", "type": "Unhandled Exception Loop", "error": "AttributeError: 'NoneType' object has no attribute 'stripe_id'", "impact": "Async worker pool crashing repeatedly on task consumer", "target_version": "v5.1"}
]

def build_data():
    deployments = []
    logs = []
    metrics = {}

    for idx, inc in enumerate(INCIDENTS, start=101):
        srv = inc["service"]
        ver = inc["version"]
        
        deployments.append({
            "deployment_id": f"dep-{idx}",
            "service": srv,
            "version": ver,
            "timestamp": f"2026-10-03T0{idx % 9}:12:00Z",
            "status": "SUCCESS",
            "changes": f"Production release {ver} - updated logic for {srv}"
        })

        logs.append({
            "timestamp": f"2026-10-03T0{idx % 9}:15:00Z",
            "service": srv,
            "level": "CRITICAL" if "Exhaustion" in inc["type"] or "Memory" in inc["type"] else "ERROR",
            "message": f"[{inc['type']}] {inc['error']}"
        })

        metrics[srv] = {
            ver: {
                "error_rate": "24.5%" if "Exhaustion" in inc["type"] or "Memory" in inc["type"] else "8.2%",
                "status": "DEGRADED",
                "issue_type": inc["type"],
                "impact_summary": inc["impact"],
                "recommended_rollback": inc["target_version"]
            }
        }

    with open(DATA_DIR / "deployments.json", "w") as f:
        json.dump(deployments, f, indent=2)

    with open(DATA_DIR / "logs.json", "w") as f:
        json.dump(logs, f, indent=2)

    with open(DATA_DIR / "metrics.json", "w") as f:
        json.dump(metrics, f, indent=2)

    print(f"Successfully generated {len(INCIDENTS)} operational failure scenarios (checkout-api removed).")

if __name__ == "__main__":
    build_data()
