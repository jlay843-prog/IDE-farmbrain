from forge.probe import compact_ray_jobs, farm_hosts_from_dials, ontology_from_payloads, ray_from_payloads


def test_farm_hosts_from_live_dials_not_invented():
    dials = {
        "ok": True,
        "body": {
            "hosts": {
                "bc250": {
                    "gpu_name": "BC-250 GFX1013",
                    "nodes": [
                        {
                            "id": "bc250-01",
                            "label": "BC-250 Node-01 (Gemma chat)",
                            "lan_ip": "192.168.68.125",
                            "online": True,
                            "model": "gemma4:12b",
                            "model_warm": True,
                            "ollama": True,
                            "ray": False,
                            "posture": "warm",
                        },
                        {
                            "id": "bc250-04",
                            "label": "BC-250 Node-04",
                            "lan_ip": "192.168.68.123",
                            "online": True,
                            "model": "qwen3.8:27b-gsq-iq3s",
                            "ollama": True,
                            "ray": True,
                            "posture": "overnight_offload",
                        },
                        {"id": "tower", "lan_ip": "192.168.68.106", "online": True},
                    ],
                }
            }
        },
    }
    rows = farm_hosts_from_dials(dials)
    assert [r["id"] for r in rows] == ["bc250-01", "bc250-04"]
    assert rows[0]["base"] == "http://192.168.68.125:11434"
    assert rows[0]["kind"] == "bc250"
    assert rows[0]["role"] == "farm"
    assert rows[0]["running"][0]["name"] == "gemma4:12b"
    assert rows[1]["ray"] is True


def test_farm_hosts_empty_when_inventory_missing():
    assert farm_hosts_from_dials(None) == []
    assert farm_hosts_from_dials({"ok": False}) == []
    assert farm_hosts_from_dials({"body": {"hosts": {}}}) == []


def test_compact_ray_jobs_from_dashboard_shape():
    payload = {
        "result": True,
        "data": {
            "result": {
                "total": 2,
                "result": [
                    {
                        "job_id": "01000000",
                        "status": "SUCCEEDED",
                        "entrypoint": "/home/jeff/src/Farm-Ontology/.venv/bin/python /mnt/rag-storage/rmbrain_exports/ray_bc250_overnight_smoke.py",
                    },
                    {
                        "job_id": "02000000",
                        "status": "RUNNING",
                        "entrypoint": "import ray\n@ray.remote(resources={'bc250_gpu': 1})\ndef embed_ping",
                    },
                ],
            }
        },
    }
    jobs = compact_ray_jobs(payload)
    assert jobs[0]["name"] == "bc250 overnight smoke"
    assert jobs[1]["name"] == "bc250 embed ping"
    ray = ray_from_payloads(jobs_body=payload, jobs_ok=True, dash_ok=True, modes={"ray_head_ok": True})
    assert ray["running"] == 1
    assert ray["head_ok"] is True
    assert ray["job_count"] == 2
    assert ray["dashboard"].endswith(":8265")


def test_ontology_counts_ray_actor_handles():
    health = {"status": "ok", "total_entities": 1715, "store_backend": "sqlite", "schema_version": "0.3"}
    agents = [
        {"id": "agent_record:farm-dashboard", "name": "Farm Brain Dashboard", "ray_actor_handle": None},
        {"id": "agent_record:critic", "name": "Ontology critic", "ray_actor_handle": "OntologyCritic"},
    ]
    ont = ontology_from_payloads(health, agents)
    assert ont["ok"] is True
    assert ont["entities"] == 1715
    assert ont["ray_actors"] == 1
    assert ont["ray_handles"][0]["handle"] == "OntologyCritic"
