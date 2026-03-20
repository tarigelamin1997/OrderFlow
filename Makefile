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
