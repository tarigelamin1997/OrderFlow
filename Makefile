.PHONY: ec2-apply ec2-destroy pause resume apply destroy seed diagram verify-phase1

# ── AWS Layer (run from laptop) ───────────────────────────────────────────────
# Set TF_VAR_allowed_ssh_cidr=x.x.x.x/32 before running.

ec2-apply:
	cd terraform/aws && terraform init && terraform apply -auto-approve

ec2-destroy:
	cd terraform/aws && terraform destroy -auto-approve

# ── Cost control ──────────────────────────────────────────────────────────────

pause:
	aws ec2 stop-instances --instance-ids $$(terraform -chdir=terraform/aws output -raw instance_id)
	@echo "Instance stopped. Compute billing paused."

resume:
	aws ec2 start-instances --instance-ids $$(terraform -chdir=terraform/aws output -raw instance_id)
	aws ec2 wait instance-running --instance-ids $$(terraform -chdir=terraform/aws output -raw instance_id)
	@echo "Instance running. SSH tunnel: ssh orderflow"

# ── Platform Layer (run inside EC2) ──────────────────────────────────────────
# Two-step apply: Kind cluster first, then workloads.
# Reason: Kubernetes provider needs the cluster to exist before it can connect.

apply:
	cd terraform && terraform init && \
	terraform apply -target=module.kind_cluster \
	  -var-file=environments/dev.tfvars -auto-approve && \
	terraform apply -var-file=environments/dev.tfvars -auto-approve

destroy:
	cd terraform && terraform destroy -var-file=environments/dev.tfvars -auto-approve

# ── Seed data (run inside EC2 after `make apply`) ─────────────────────────────

seed:
	cd seed && pip install -r requirements.txt -q && \
	python3 postgres/02_users.py && \
	python3 postgres/03_restaurants.py && \
	python3 postgres/04_drivers.py && \
	python3 postgres/05_orders.py && \
	python3 mongo/user_events.py && \
	python3 mongo/delivery_updates.py

# ── Architecture diagram ──────────────────────────────────────────────────────
# Requires Docker. Regenerates .drawio from spec, then exports .svg.

diagram:
	python3 scripts/generate_diagram.py
	docker run --rm -v $(PWD)/docs/architecture:/data \
	  rlespinasse/drawio-export \
	  --format svg --output /data \
	  /data/orderflow_architecture.drawio
	@echo "Diagram regenerated: docs/architecture/orderflow_architecture.svg"

# ── Verification ──────────────────────────────────────────────────────────────

verify-phase1:
	bash scripts/verify_phase1.sh

# ── Phase 2 — CDC Pipeline ───────────────────────────────────────────────────

CONNECT_IMAGE = orderflow-connect:latest

.PHONY: download-plugins build-connect-image deploy-connect deploy-connectors apply-bronze deploy-s3-sink verify-phase2

download-plugins:
	mkdir -p connect-plugins/plugins
	curl -sL https://repo1.maven.org/maven2/io/debezium/debezium-connector-postgres/2.7.0.Final/debezium-connector-postgres-2.7.0.Final-plugin.tar.gz \
	    | tar -xz -C connect-plugins/plugins/
	curl -sL https://repo1.maven.org/maven2/io/debezium/debezium-connector-mongodb/2.7.0.Final/debezium-connector-mongodb-2.7.0.Final-plugin.tar.gz \
	    | tar -xz -C connect-plugins/plugins/
	@echo "Debezium connectors downloaded. Now downloading Confluent packages..."
	mkdir -p /tmp/confluent-hub && cd /tmp/confluent-hub && \
	curl -sL -o avro-converter.zip "https://d2p6pa21dvn84.cloudfront.net/api/plugins/confluentinc/kafka-connect-avro-converter/versions/7.6.1/confluentinc-kafka-connect-avro-converter-7.6.1.zip" && \
	curl -sL -o s3-sink.zip "https://d2p6pa21dvn84.cloudfront.net/api/plugins/confluentinc/kafka-connect-s3/versions/10.5.13/confluentinc-kafka-connect-s3-10.5.13.zip" && \
	unzip -qo avro-converter.zip -d avro-tmp && \
	unzip -qo s3-sink.zip -d s3-tmp && \
	mkdir -p $(CURDIR)/connect-plugins/plugins/confluent-avro-converter && \
	mkdir -p $(CURDIR)/connect-plugins/plugins/confluent-kafka-connect-s3 && \
	cp avro-tmp/confluentinc-kafka-connect-avro-converter-7.6.1/lib/*.jar $(CURDIR)/connect-plugins/plugins/confluent-avro-converter/ && \
	cp s3-tmp/confluentinc-kafka-connect-s3-10.5.13/lib/*.jar $(CURDIR)/connect-plugins/plugins/confluent-kafka-connect-s3/ && \
	rm -rf /tmp/confluent-hub
	@echo "All plugins downloaded"

build-connect-image:
	cd connect-plugins && mvn package -q
	docker build -t $(CONNECT_IMAGE) connect-plugins/
	kind load docker-image $(CONNECT_IMAGE) --name orderflow
	@echo "Image loaded into Kind cluster"

deploy-connect:
	kubectl apply -f debezium/strimzi/kafka-connect.yaml
	kubectl wait --for=condition=Ready kafkaconnect/orderflow-connect \
	    -n kafka --timeout=180s

deploy-connectors:
	kubectl apply -f debezium/strimzi/postgres-connector.yaml
	kubectl apply -f debezium/strimzi/mongo-connector.yaml
	@echo "Connectors deployed — snapshot starting"

apply-bronze:
	bash clickhouse/bronze/apply_bronze.sh

deploy-s3-sink:
	MINIO_ACCESS_KEY=orderflow MINIO_SECRET_KEY=orderflow_minio_pass \
	envsubst < kafka/s3-sink-avro.json | curl -s -X POST \
	    -H "Content-Type: application/json" \
	    --data @- http://localhost:30083/connectors | jq .
	MINIO_ACCESS_KEY=orderflow MINIO_SECRET_KEY=orderflow_minio_pass \
	envsubst < kafka/s3-sink-json.json | curl -s -X POST \
	    -H "Content-Type: application/json" \
	    --data @- http://localhost:30083/connectors | jq .
	@echo "Both S3 Sink connectors deployed (Avro + JSON)"

verify-phase2:
	bash scripts/verify_phase2.sh

# -- Phase 3 — ClickHouse Deep Schema ----------------------------------------

.PHONY: apply-silver backfill-silver apply-gold materialize-projections wait-projections verify-phase3

apply-silver:
	bash clickhouse/silver/apply_silver.sh

backfill-silver:
	bash clickhouse/silver/backfill_silver.sh

apply-gold:
	bash clickhouse/gold/apply_gold.sh

materialize-projections:
	clickhouse-client --host localhost --port 30900 --multiquery < clickhouse/gold/07_projections.sql
	clickhouse-client --host localhost --port 30900 --multiquery < clickhouse/gold/08_materialize_projections.sql
	@echo "Projection materialisation started — check system.mutations"

wait-projections:
	@echo "Waiting for projection materialisation..."
	@until clickhouse-client --host localhost --port 30900 	    --query "SELECT count() FROM system.mutations WHERE table='orders' 	             AND database='silver' AND NOT is_done" | grep -q "^0"; do 	    sleep 5; echo "  still running..."; done
	@echo "Projections materialised."

verify-phase3:
	bash scripts/verify_phase3.sh

# -- Phase 4 — Spark Batch Path + Delta Lake -----------------------------------

SPARK_IMAGE = orderflow/spark-orderflow:3.5.1-delta3

.PHONY: build-spark-image apply-gold-batch run-silver run-features run-gold-writer run-phase4 verify-phase4

build-spark-image:
	docker build -t $(SPARK_IMAGE) spark/
	kind load docker-image $(SPARK_IMAGE) --name orderflow
	@echo "Spark image loaded into Kind cluster"

apply-gold-batch:
	bash clickhouse/gold/apply_gold_batch.sh

run-silver:
	kubectl delete sparkapplication orderflow-silver-ingestion -n spark --ignore-not-found
	kubectl apply -f spark/manifests/silver-ingestion.yaml
	kubectl wait --for=condition=Completed sparkapplication/orderflow-silver-ingestion 	    -n spark --timeout=600s
	@echo "Silver ingestion complete"

run-features:
	kubectl delete sparkapplication orderflow-feature-eng -n spark --ignore-not-found
	kubectl apply -f spark/manifests/feature-engineering.yaml
	kubectl wait --for=condition=Completed sparkapplication/orderflow-feature-eng 	    -n spark --timeout=600s
	@echo "Feature engineering complete"

run-gold-writer:
	kubectl delete sparkapplication orderflow-gold-writer -n spark --ignore-not-found
	kubectl apply -f spark/manifests/gold-writer.yaml
	kubectl wait --for=condition=Completed sparkapplication/orderflow-gold-writer 	    -n spark --timeout=300s
	@echo "Gold writer complete"

run-phase4: apply-gold-batch run-silver run-features run-gold-writer verify-phase4

verify-phase4:
	bash spark/scripts/verify_phase4.sh

# -- Phase 5 — Advanced dbt Layer -----------------------------------------------

.PHONY: rebuild-airflow-image install-dbt-packages dbt-clickhouse-run dbt-clickhouse-snapshot dbt-clickhouse-test dbt-spark-run verify-phase5

rebuild-airflow-image:
	docker build -t orderflow/airflow:2.10.0 airflow/
	kind load docker-image orderflow/airflow:2.10.0 --name orderflow
	kubectl rollout restart statefulset/airflow -n airflow
	kubectl rollout status statefulset/airflow -n airflow --timeout=120s
	@echo "Airflow image rebuilt and pod restarted"

install-dbt-packages:
	cd dbt/orderflow_clickhouse && dbt deps --profiles-dir .
	cd dbt/orderflow_spark && dbt deps --profiles-dir .
	@echo "dbt packages installed"

dbt-clickhouse-run:
	cd dbt/orderflow_clickhouse && dbt run --profiles-dir .

dbt-clickhouse-snapshot:
	cd dbt/orderflow_clickhouse && dbt snapshot --profiles-dir .

dbt-clickhouse-test:
	cd dbt/orderflow_clickhouse && dbt test --profiles-dir .

dbt-spark-run:
	cd dbt/orderflow_spark && dbt run --profiles-dir .

verify-phase5:
	bash scripts/verify_phase5.sh

# -- Phase 6 — Airflow Orchestration -------------------------------------------

.PHONY: apply-pii-audit-log deploy-dags verify-phase6

apply-pii-audit-log:
	clickhouse-client --host localhost --port 30900 --multiquery < clickhouse/gold/12_pii_audit_log.sql
	@echo "pii_audit_log created"

deploy-dags:
	kubectl exec -n airflow airflow-0 -- mkdir -p /opt/airflow/schema_snapshots /opt/airflow/spark-manifests
	kubectl cp airflow/dags airflow/airflow-0:/opt/airflow/dags -n airflow
	kubectl cp airflow/schema_snapshots airflow/airflow-0:/opt/airflow/schema_snapshots -n airflow
	kubectl cp spark/manifests airflow/airflow-0:/opt/airflow/spark-manifests -n airflow
	kubectl cp dbt airflow/airflow-0:/opt/airflow/dbt -n airflow
	@echo "DAGs and configs deployed to Airflow pod"

verify-phase6:
	bash scripts/verify_phase6.sh

# -- Phase 7 — Observability + FinOps + Lineage --------------------------------

.PHONY: apply-phase7-ddl verify-phase7

apply-phase7-ddl:
	clickhouse-client --host localhost --port 30900 --multiquery < clickhouse/gold/13_dag_run_log.sql
	clickhouse-client --host localhost --port 30900 --multiquery < clickhouse/gold/14_schema_drift_log.sql
	@echo "Phase 7 Gold tables created"

verify-phase7:
	bash scripts/verify_phase7.sh

# -- Phase 8 — Multi-Env + Stress Test + Documentation -------------------------

.PHONY: stress-wave stress-measure stress-full secret-audit fresh-cluster-build run-phase8 verify-phase8

stress-wave:
	python3 stress/generate_load.py --wave $(WAVE)
	@echo "Wave $(WAVE) data generated"

stress-measure:
	python3 stress/measure_slos.py --wave $(WAVE)
	@echo "Wave $(WAVE) SLOs measured"

stress-full:
	@for wave in 1 2 3 4 5 6 7 8 9 10 11 12; do \
	  echo "=== Wave $$wave ===" ; \
	  make stress-wave WAVE=$$wave ; \
	  sleep 30 ; \
	  make stress-measure WAVE=$$wave ; \
	done
	python3 stress/measure_slos.py --report > docs/SLO_REPORT.md
	@echo "Stress test complete. SLO report generated."

secret-audit:
	bash security/secret-audit.sh

fresh-cluster-build:
	bash scripts/fresh_cluster_build.sh

run-phase8: stress-full secret-audit
	@echo "Phase 8 complete. Run fresh-cluster-build separately (destroys cluster)."

verify-phase8:
	bash scripts/verify_phase8.sh

# -- Phase 9 — Self-Service Pipeline Factory ------------------------------------

.PHONY: generate-pipeline deploy-pipeline test-factory demo-payments run-phase9 verify-phase9

generate-pipeline:
	python3 factory/pipeline_factory.py --source $(SOURCE)
	@echo "Pipeline generated for $(SOURCE)"

deploy-pipeline:
	bash factory/output/$(ENTITY)/apply.sh
	@echo "Pipeline deployed for $(ENTITY)"

test-factory:
	python3 -m pytest factory/tests/ -v
	@echo "Factory tests passed"

demo-payments:
	PGPASSWORD=orderflow_pg_pass psql -h localhost -p 30432 -U orderflow -d orderflow < factory/sources/payments_seed.sql
	make generate-pipeline SOURCE=factory/sources/payments.yaml
	bash factory/output/payments/apply.sh
	@echo "Payments demo pipeline deployed"

run-phase9: test-factory demo-payments verify-phase9

verify-phase9:
	bash scripts/verify_phase9.sh
