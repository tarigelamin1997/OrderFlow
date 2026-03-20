# ── Namespace ─────────────────────────────────────────────────────────────────
resource "kubernetes_namespace" "kafka" {
  metadata { name = "kafka" }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Strimzi Operator 0.40.0                                                   ║
# ║  Manages the Kafka KRaft cluster lifecycle via CRDs.                       ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "helm_release" "strimzi" {
  name             = "strimzi"
  repository       = "https://strimzi.io/charts/"
  chart            = "strimzi-kafka-operator"
  version          = "0.40.0"
  namespace        = kubernetes_namespace.kafka.metadata[0].name
  create_namespace = false
  wait             = true
  timeout          = 300

  set {
    name  = "watchAnyNamespace"
    value = "false"
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Kafka 3.7.0 — KRaft mode, single combined node (controller + broker)     ║
# ║  KafkaNodePool CRD defines storage; Kafka CR holds cluster config.        ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "null_resource" "kafka_kraft" {
  depends_on = [helm_release.strimzi]

  triggers = {
    config = sha256(jsonencode({
      kafka_version = "3.7.0"
      replicas      = 1
    }))
  }

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail

      # Wait for Strimzi CRDs to be established
      kubectl wait --namespace kafka \
        --for=condition=established \
        crd/kafkas.kafka.strimzi.io \
        --timeout=120s

      kubectl apply -f - <<'YAML'
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaNodePool
metadata:
  name: combined
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  replicas: 1
  roles:
    - controller
    - broker
  storage:
    type: persistent-claim
    size: 10Gi
    deleteClaim: false
    class: standard
  resources:
    requests:
      memory: 1Gi
      cpu: 500m
    limits:
      memory: 2Gi
      cpu: 1000m
---
apiVersion: kafka.strimzi.io/v1beta2
kind: Kafka
metadata:
  name: orderflow-kafka
  namespace: kafka
  annotations:
    strimzi.io/node-pools: enabled
    strimzi.io/kraft: enabled
spec:
  kafka:
    version: 3.7.0
    listeners:
      - name: plain
        port: 9092
        type: internal
        tls: false
      - name: external
        port: 9093
        type: nodeport
        tls: false
        configuration:
          externalTrafficPolicy: Local
          brokers:
            - broker: 0
              advertisedHost: localhost
              advertisedPort: 30092
              nodePort: 30092
    config:
      # Single-broker KRaft: these must be 1 or the cluster won't start
      offsets.topic.replication.factor: 1
      transaction.state.log.replication.factor: 1
      transaction.state.log.min.isr: 1
      default.replication.factor: 1
      min.insync.replicas: 1
  entityOperator:
    topicOperator: {}
    userOperator: {}
YAML
      echo "KafkaNodePool + Kafka CR applied"
    EOF
  }
}

# Wait for Kafka broker to be Ready before topics are created.
resource "null_resource" "wait_for_kafka" {
  depends_on = [null_resource.kafka_kraft]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail
      echo "Waiting for Kafka cluster to be Ready (up to 5 min)..."
      kubectl wait kafka/orderflow-kafka \
        --namespace kafka \
        --for=condition=Ready \
        --timeout=300s
      echo "Kafka cluster Ready"
    EOF
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Kafka Topics — 6 source topics + 1 DLQ                                   ║
# ║  Created via KafkaTopic CRDs (Strimzi Entity Operator manages them).      ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "null_resource" "kafka_topics" {
  depends_on = [null_resource.wait_for_kafka]

  provisioner "local-exec" {
    interpreter = ["/bin/bash", "-c"]
    command = <<-EOF
      set -euo pipefail
      kubectl apply -f - <<'YAML'
# PostgreSQL CDC topics (Debezium topic.prefix=orderflow)
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orderflow.public.orders
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orderflow.public.users
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orderflow.public.restaurants
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orderflow.public.drivers
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
# MongoDB CDC topics (Debezium topic.prefix=mongo)
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: mongo.foodtech.user-events
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  topicName: mongo.foodtech.user_events
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: mongo.foodtech.delivery-updates
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  topicName: mongo.foodtech.delivery_updates
  partitions: 3
  replicas: 1
  config:
    retention.ms: "${var.kafka_retention_ms}"
---
# Dead-letter queue for failed order events
apiVersion: kafka.strimzi.io/v1beta2
kind: KafkaTopic
metadata:
  name: orderflow.public.orders.dlq
  namespace: kafka
  labels:
    strimzi.io/cluster: orderflow-kafka
spec:
  partitions: 1
  replicas: 1
  config:
    retention.ms: "604800000"
YAML
      echo "7 Kafka topics created"
    EOF
  }
}

# ╔══════════════════════════════════════════════════════════════════════════════╗
# ║  Confluent Schema Registry 7.6.1                                           ║
# ║  Tracks Avro schemas for the 4 PostgreSQL CDC topics.                     ║
# ╚══════════════════════════════════════════════════════════════════════════════╝

resource "kubernetes_deployment" "schema_registry" {
  depends_on = [null_resource.wait_for_kafka]

  metadata {
    name      = "schema-registry"
    namespace = kubernetes_namespace.kafka.metadata[0].name
    labels    = { app = "schema-registry" }
  }

  spec {
    replicas = 1
    selector { match_labels = { app = "schema-registry" } }

    template {
      metadata { labels = { app = "schema-registry" } }

      spec {
        enable_service_links = false

        container {
          name  = "schema-registry"
          image = "confluentinc/cp-schema-registry:7.6.1"

          env {
            name  = "SCHEMA_REGISTRY_HOST_NAME"
            value = "schema-registry"
          }
          env {
            name  = "SCHEMA_REGISTRY_KAFKASTORE_BOOTSTRAP_SERVERS"
            value = "orderflow-kafka-kafka-bootstrap.kafka.svc.cluster.local:9092"
          }
          env {
            name  = "SCHEMA_REGISTRY_LISTENERS"
            value = "http://0.0.0.0:8081"
          }

          port {
            container_port = 8081
          }

          resources {
            requests = { cpu = "200m", memory = "256Mi" }
            limits   = { cpu = "400m", memory = "512Mi" }
          }

          readiness_probe {
            http_get {
              path = "/subjects"
              port = 8081
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service" "schema_registry" {
  metadata {
    name      = "schema-registry"
    namespace = kubernetes_namespace.kafka.metadata[0].name
  }
  spec {
    selector = { app = "schema-registry" }
    port {
      port        = 8081
      target_port = 8081
      node_port   = 30081
    }
    type = "NodePort"
  }
}
